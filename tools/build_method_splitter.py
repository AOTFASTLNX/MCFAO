#!/usr/bin/env python3
"""Build the first-party method splitter (`compiler/splitter`) with a pinned ASM classpath.

The splitter is first-party Java source. Its only dependencies are the ASM bytecode libraries,
which are **not** vendored into this repository: they are resolved from the Gradle distribution that
is already on this machine plus two verified Maven Central downloads, and every jar is recorded with
its SHA-256 in the build record so a later run can detect a substituted library.

This tool only compiles. It does not transform any jar and it is not Gate evidence.
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT, capture
from run_b0_reference import execute  # noqa: F401  (imported for parity with other tools)

SOURCE = ROOT / "compiler/splitter/src/fabricaot/split/MethodSplitter.java"
ASM_VERSION = "9.9"

# Where the two jars that the Gradle distribution does not ship are expected. They are fetched by
# `python3 -B tools/build_method_splitter.py --fetch-missing` from Maven Central.
CACHE = ROOT / (".cache/libs/asm-" + ASM_VERSION)
MAVEN = "https://repo1.maven.org/maven2/org/ow2/asm"


def gradle_asm() -> dict:
    """Return {name: path} for the ASM jars bundled with the local Gradle distribution."""
    patterns = [
        str(Path.home() / ".gradle/wrapper/dists/gradle-*-bin/*/gradle-*/lib/asm-%s.jar") % ASM_VERSION,
        str(Path.home() / ".gradle/wrapper/dists/gradle-*-bin/*/gradle-*/lib/asm-tree-%s.jar") % ASM_VERSION,
    ]
    found = {}
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            found[Path(path).name] = Path(path)
    return found


def build(java_home: Path, output: Path, extra: list | None = None) -> dict:
    """Compile the splitter into `output/classes` and return a build record."""
    libraries = gradle_asm()
    for name in ("asm-analysis-%s.jar" % ASM_VERSION, "asm-util-%s.jar" % ASM_VERSION):
        libraries[name] = CACHE / name
    for name, path in libraries.items():
        if not path.exists():
            raise SystemExit("missing ASM library %s (%s); run with --fetch-missing" % (name, path))
    classpath = ":".join(str(path) for path in libraries.values())
    classes = output / "classes"
    if classes.exists():
        shutil.rmtree(classes)
    for stale in ("compile",):
        if (output / stale).exists():
            shutil.rmtree(output / stale)
    classes.mkdir(parents=True)
    run = capture([str(java_home / "bin/javac"), "--release", "25", "-proc:none", "-Xlint:all",
                   "-cp", classpath, "-d", str(classes), str(SOURCE)], output / "compile", 300)
    record = {
        "status": "BUILT" if run["exitCode"] == 0 else "FAILED",
        "source": str(SOURCE),
        "sourceSHA256": sha256(SOURCE),
        "javaHome": str(java_home),
        "javaVersion": "25",
        "asmVersion": ASM_VERSION,
        "asmJars": [{"name": name, "path": str(path.resolve()), "sha256": sha256(path)}
                    for name, path in sorted(libraries.items())],
        "classesDirectory": str(classes),
        "classFiles": sorted(p.name for p in classes.rglob("*.class")),
        "exitCode": run["exitCode"],
        "scope": "compile only; the splitter is not run and no artifact is transformed here",
    }
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    if run["exitCode"] != 0:
        raise SystemExit("javac failed, see " + str(output / "compile"))
    return record


def fetch_missing() -> list:
    """Download the two ASM artifacts the Gradle distribution does not bundle (pinned version)."""
    import urllib.request

    CACHE.mkdir(parents=True, exist_ok=True)
    fetched = []
    for artifact in ("asm-analysis", "asm-util"):
        target = CACHE / ("%s-%s.jar" % (artifact, ASM_VERSION))
        if target.exists():
            continue
        url = "%s/%s/%s/%s-%s.jar" % (MAVEN, artifact, ASM_VERSION, artifact, ASM_VERSION)
        with urllib.request.urlopen(url, timeout=60) as response:
            target.write_bytes(response.read())
        fetched.append({"path": str(target), "url": url, "sha256": sha256(target)})
    return fetched


def java_home() -> Path:
    manifest = json.loads((ROOT / "artifacts/b0/prepared-04/result.json").read_text())
    home = Path(manifest["javaHome"])
    if not (home / "bin/javac").exists():
        raise SystemExit("javac missing from the verified Java 25 home")
    return home


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fetch-missing", action="store_true")
    args = parser.parse_args(argv)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    if args.fetch_missing:
        fetched = fetch_missing()
        if fetched:
            (output / "fetched.json").write_text(json.dumps(fetched, indent=2) + "\n")
    record = build(java_home(), output)
    print(json.dumps({key: record[key] for key in ("status", "sourceSHA256", "classesDirectory")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
