#!/usr/bin/env python3
"""Run real JVM negative controls against the built, first-party A1 fixture."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from capture import ROOT, capture


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--alternate-java", type=Path)
    args = parser.parse_args(argv)
    output, build = args.output.absolute(), args.build.absolute()
    output.mkdir(parents=True, exist_ok=False)
    java = args.java_home.resolve() / "bin/java"
    classes = build / "classes"
    library = build / "liba1probe.dylib"
    results = {}

    def check(name, command, expected):
        result = capture([str(x) for x in command], output / name)
        error = (output / name / "stderr.log").read_text()
        result["expectedDiagnostic"] = expected
        result["negativeControlPass"] = result["exitCode"] != 0 and not result["timedOut"] and expected in error
        results[name] = result

    prefix = [java, "--enable-native-access=ALL-UNNAMED", "-cp"]
    check("missing-native-library", prefix + [classes, "fabricaot.probe.A1Probe", output / "missing.dylib", output / "scratch-a"], "UnsatisfiedLinkError")
    stripped = output / "without-resource/fabricaot/probe"
    stripped.mkdir(parents=True)
    shutil.copy2(classes / "fabricaot/probe/A1Probe.class", stripped / "A1Probe.class")
    check("missing-resource", prefix + [output / "without-resource", "fabricaot.probe.A1Probe", library, output / "scratch-b"], "embedded-resource")
    if args.alternate_java:
        check("wrong-java-major", [args.alternate_java, "-cp", classes, "fabricaot.probe.A1Probe", library, output / "scratch-c"], "exact-java-25")
    result = {"status": "PASS" if all(r["negativeControlPass"] for r in results.values()) else "FAIL", "controls": results}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "controls": {k: v["negativeControlPass"] for k, v in results.items()}}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
