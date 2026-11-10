#!/usr/bin/env python3
"""Run the first-party method splitter over a jar and record what changed.

`compiler/splitter` rewrites oversized static void methods (`<clinit>` and `()V` statics) into a
chain of smaller methods at boundaries that are statically proven safe: empty operand stack, no jump
or switch crossing the cut, no exception-table entry straddling it, and local variables carried
across through typed synthetic static fields. This driver only orchestrates that tool and records
the outcome; it does not decide whether the transformed client behaves identically.

Output is an experiment record: the transformation is a build-time step, and nothing here analyses,
compiles or executes Minecraft.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT, capture

SPLITTER = ROOT / "artifacts/compiler/method-splitter-01"

# Fields copied verbatim from the splitter report into the experiment record.
REPORT_FIELDS = ("classesRead", "classesWritten", "classesRejected", "methodsSplit", "partsCreated")


def classpath_from_file(path: Path) -> list:
    """Split a colon separated classpath file into paths (the argv list cannot hold spaces safely)."""
    return [Path(piece) for piece in path.read_text().strip().split(":") if piece]


def splitter_classpath(directory: Path) -> str:
    """Return the java -cp value: compiled splitter classes plus the recorded ASM jars."""
    record_path = directory / "result.json"
    if not record_path.exists():
        raise SystemExit("splitter build record missing: " + str(record_path))
    record = json.loads(record_path.read_text())
    if record.get("status") != "BUILT":
        raise SystemExit("splitter is not built: " + str(record_path))
    entries = record.get("asmJars") or []
    if not entries:
        raise SystemExit("splitter build record has no ASM libraries: " + str(record_path))
    for entry in entries:
        if sha256(Path(entry["path"])) != entry["sha256"]:
            raise SystemExit("ASM library changed: " + entry["path"])
    return ":".join([record["classesDirectory"]] + [entry["path"] for entry in entries])


def report_counts(report: dict) -> dict:
    """Pick the counters that describe what the splitter did, ignoring per-class detail."""
    return {field: report.get(field) for field in REPORT_FIELDS}


def run(jar: Path, output_jar: Path, report: Path, classpath: list, trigger_cost: int, min_sites: int,
        target_sites: int, max_parts: int, class_filter, dry_run: bool,
        tool: Path = SPLITTER, timeout: int = 1800) -> dict:
    record = json.loads((tool / "result.json").read_text())
    home = Path(record["javaHome"])
    command = [str(home / "bin/java"), "-Xmx6g", "-cp", splitter_classpath(tool),
               "fabricaot.split.MethodSplitter",
               "--in", str(jar), "--out", str(output_jar), "--report", str(report),
               "--trigger-cost", str(trigger_cost), "--min-sites", str(min_sites),
               "--target-sites", str(target_sites), "--max-parts", str(max_parts)]
    if classpath:
        command += ["--classpath", ":".join(str(path) for path in classpath)]
    if class_filter:
        command += ["--class", class_filter]
    if dry_run:
        command += ["--dry-run"]
    transform = report.parent / "transform"
    if transform.exists():
        import shutil
        shutil.rmtree(transform)
    run_record = capture(command, transform, timeout)
    summary = {"status": "FAILED", "exitCode": run_record["exitCode"],
               "jar": str(jar), "jarSHA256": sha256(jar),
               "outputJar": str(output_jar), "outputJarSHA256": None,
               "report": str(report), "splitter": str(tool),
               "splitterSourceSHA256": record["sourceSHA256"],
               "asmJars": record["asmJars"],
               "scope": "build-time bytecode transformation only; semantic equivalence for the real "
                        "client is unproven until the transformed jar is analysed and executed"}
    if report.exists():
        data = json.loads(report.read_text())
        summary.update(report_counts(data))
        summary["classes"] = data.get("classes", [])
        if run_record["exitCode"] == 0:
            summary["status"] = "DRY_RUN" if dry_run else "SPLIT"
    if output_jar.exists() and not dry_run:
        summary["outputJarSHA256"] = sha256(output_jar)
    (report.parent / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--output-jar", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--classpath", nargs="*", type=Path, default=[])
    parser.add_argument("--classpath-file", type=Path,
                        help="File holding a colon separated classpath (needed for paths with spaces)")
    parser.add_argument("--trigger-cost", type=int, default=1_000_000)
    parser.add_argument("--min-sites", type=int, default=200)
    parser.add_argument("--target-sites", type=int, default=64)
    parser.add_argument("--max-parts", type=int, default=64)
    parser.add_argument("--class", dest="class_filter", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tool", type=Path, default=SPLITTER)
    args = parser.parse_args(argv)
    report = args.report if args.report.is_absolute() else ROOT / args.report
    report.parent.mkdir(parents=True, exist_ok=True)
    classpath = list(args.classpath)
    if args.classpath_file:
        classpath.extend(classpath_from_file(args.classpath_file))
    summary = run(args.jar, args.output_jar, report, classpath, args.trigger_cost, args.min_sites,
                  args.target_sites, args.max_parts, args.class_filter, args.dry_run, args.tool)
    print(json.dumps({key: summary.get(key) for key in REPORT_FIELDS}, indent=2))
    return 0 if summary["status"] in ("SPLIT", "DRY_RUN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
