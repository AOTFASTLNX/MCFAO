#!/usr/bin/env python3
"""Select repository-owned mechanism tests from a Builder compatibility report."""

import argparse
import json
from pathlib import Path
import sys

from capture import ROOT, capture


SUITES = {
    "fabric-loader-contract": ("test_mod_catalog.py", "test_runtime_lowering.py"),
    "mixin-bytecode": ("test_runtime_lowering.py", "test_verify_aot_classpath.py"),
    "entrypoint-dispatch": ("test_runtime_lowering.py",),
    "runtime-resource-read": ("test_resource_closure.py",),
    "configuration-round-trip": ("test_config_reflection.py", "test_mdaf.py"),
    "initialization-timing": ("test_aot_compatibility.py",),
    "dynamic-class-contract": ("test_aot_compatibility.py", "test_runtime_lowering.py"),
    "image-pixel-contract": ("test_runtime_lowering.py",),
}
# Suite success verifies the fixture. Mod and device statuses are inferred from separate runs.
DEVICE_DEPENDENT = {"ios-sandbox-filesystem", "native-library-contract", "openal-object-lifecycle"}


def select(report):
    checks = {check for row in report.get("mods", ()) for check in row.get("relevantChecks", ())}
    return (sorted({suite for check in checks for suite in SUITES.get(check, ())}),
            sorted(checks - SUITES.keys() - DEVICE_DEPENDENT),
            sorted(checks & DEVICE_DEPENDENT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text())
    suites, uncovered, device = select(report)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = {}
    for suite in suites:
        record = capture([sys.executable, "-B", "-m", "unittest", "discover", "-s", str(ROOT / "tests"),
                          "-p", suite, "-v"], output / Path(suite).stem, 180, cwd=ROOT)
        results[suite] = {"exitCode": record["exitCode"], "timedOut": record["timedOut"]}
    summary = {
        "scope": "first-party mechanism fixtures",
        "suites": results,
        "missingFixtures": uncovered,
        "deviceNotRun": device,
    }
    (output / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(output / "result.json")
    return int(any(row["exitCode"] != 0 or row["timedOut"] for row in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
