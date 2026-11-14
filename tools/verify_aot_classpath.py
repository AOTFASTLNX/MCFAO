#!/usr/bin/env python3
"""Check that every class in an AOT image's classpath can actually be loaded.

A class that names a type the classpath does not contain cannot be loaded at all. Native Image
does not fail such a build: it silently replaces every call into that class with a stub that
throws NoSuchMethodError at run time, which surfaces minutes into start-up as an unrelated
looking crash (see the ETF `ScreenAccessor` incident). Running this check right after a build
turns that silent failure into a list.

The check is deliberately the same operation the image builder performs - resolve the class,
do not initialise it - so its answer matches what native-image can see.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / ".cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home/bin"

PROBE = """
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;

public class LoadAll {
    public static void main(String[] args) throws Exception {
        List<String> names = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(System.in))) {
            for (String line; (line = reader.readLine()) != null; ) {
                if (!line.isEmpty()) names.add(line.replace('/', '.').replaceAll("\\\\.class$", ""));
            }
        }
        ClassLoader loader = LoadAll.class.getClassLoader();
        int failed = 0;
        for (String name : names) {
            try {
                Class<?> type = Class.forName(name, false, loader);
                if (args.length > 0 && args[0].equals("--verify-members")) {
                    type.getDeclaredConstructors();
                    type.getDeclaredMethods();
                    type.getDeclaredFields();
                }
            } catch (Throwable error) {
                Throwable root = error;
                while (root.getCause() != null) root = root.getCause();
                System.out.println("FAIL\\t" + name + "\\t" + root.getClass().getSimpleName()
                        + ": " + root.getMessage());
                failed++;
            }
        }
        System.out.println("SUMMARY\\t" + names.size() + "\\t" + failed);
    }
}
"""


def classpath_of(build: Path) -> tuple[list[str], Path]:
    result = json.loads((build / "result.json").read_text())
    command = json.loads(Path(result["aotCommand"]).read_text())
    argv = command["argv"]
    return argv[argv.index("-cp") + 1].split(":"), Path(result["aotCommand"])


def class_names(entries: list[str]) -> list[str]:
    names: list[str] = []
    for entry in entries:
        path = Path(entry)
        if path.suffix == ".jar":
            with __import__("zipfile").ZipFile(path) as archive:
                names.extend(n for n in archive.namelist()
                             if n.endswith(".class") and not n.startswith("META-INF/"))
        elif path.is_dir():
            names.extend(str(p.relative_to(path)) for p in path.rglob("*.class"))
    return sorted(set(names))


def parse_probe_output(completed, expected_count):
    if completed.returncode:
        raise RuntimeError(f"Classpath probe exited {completed.returncode}: {completed.stderr[-2000:]}")
    failures, total, failed = [], None, None
    for line in completed.stdout.splitlines():
        parts = line.split("\t", 2)
        if parts[0] == "FAIL" and len(parts) == 3:
            failures.append({"class": parts[1], "cause": parts[2]})
        elif parts[0] == "SUMMARY" and len(parts) == 3:
            total, failed = int(parts[1]), int(parts[2])
    if total != expected_count or failed != len(failures):
        raise RuntimeError("Incomplete classpath probe report; no verification result")
    return failures, total, failed


def verify_entries(entries: list[str | Path], java_bin: Path = JAVA, *,
                   verify_members: bool = False, timeout: int = 900) -> dict:
    """Run the classpath probe without requiring a completed mcfao build directory."""
    names = class_names([str(entry) for entry in entries])
    with tempfile.TemporaryDirectory(prefix="classpath-check-") as work:
        work_path = Path(work)
        source = work_path / "LoadAll.java"
        source.write_text(PROBE)
        subprocess.run([str(java_bin / "javac"), "-nowarn", "-d", str(work_path), str(source)],
                       check=True, capture_output=True, timeout=timeout)
        completed = subprocess.run(
            [str(java_bin / "java"), "-Xmx2g", "-XX:+UseSerialGC",
             "-cp", ":".join([*map(str, entries), str(work_path)]), "LoadAll",
             *( ["--verify-members"] if verify_members else [])],
            input="\n".join(names), text=True, capture_output=True, timeout=timeout)

    failures, total, failed = parse_probe_output(completed, len(names))
    by_cause: dict[str, int] = {}
    for failure in failures:
        by_cause[failure["cause"]] = by_cause.get(failure["cause"], 0) + 1
    return {"classes": total, "unloadable": failed, "topCauses": dict(
        sorted(by_cause.items(), key=lambda item: -item[1])[:20]), "failures": failures,
        "memberResolution": verify_members,
        "status": "REPORT_ONLY_FINDINGS" if failed else "PASS"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True, help="mcfao build output directory")
    parser.add_argument("--output", type=Path, help="Write the report here (default: <build>/classpath-check.json)")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--verify-members", action="store_true",
                        help="Also resolve constructors/methods/fields without initializing classes")
    args = parser.parse_args(argv)
    build = args.build.resolve()

    entries, source = classpath_of(build)
    output = args.output or build / ("classpath-members-check.json" if args.verify_members else "classpath-check.json")
    report = verify_entries(entries, JAVA, verify_members=args.verify_members, timeout=args.timeout)
    report.update(classpath=entries, aotCommand=str(source))
    print(f"{report['classes']} classes over {len(entries)} classpath entries ({source})")
    output.write_text(json.dumps(report, indent=1) + "\n")

    for cause, count in sorted(report["topCauses"].items(), key=lambda item: -item[1])[:10]:
        print(f"{count:6d}  {cause}")
    print(f"unloadable {report['unloadable']}/{report['classes']} -> {output}")
    return 0 if report["unloadable"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
