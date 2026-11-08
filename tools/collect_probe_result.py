#!/usr/bin/env python3
"""Collect only this project's simulator probe reports and evaluate real assertions."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from bootstrap_toolchain import sha256


def evaluate(report: dict, log: str) -> dict:
    native_ok = all(report.get(name) == 0 for name in ("createIsolate", "runResult", "tearDownIsolate"))
    java_ok = "A1_SEMANTICS_PASS" in log.splitlines()
    passed = report.get("status") == "PASS" and native_ok and java_ok
    return {"status": "PASS" if passed else "BLOCKED", "target": "iOS Simulator arm64",
            "nativeLifecyclePass": native_ok, "javaAssertionsPass": java_ok,
            "deviceRun": "NOT RUN", "iosGateA1": "BLOCKED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-file", type=Path, required=True)
    parser.add_argument("--simulator", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    container = Path(args.container_file.read_text().strip()).resolve()
    expected = Path.home() / "Library/Developer/CoreSimulator/Devices" / args.simulator / "data/Containers/Data/Application"
    if container.parent != expected or not re.fullmatch(r"[0-9A-Fa-f-]{36}", args.simulator):
        parser.error("Container is not inside the explicitly selected simulator")
    documents = container / "Documents"
    report_path = documents / "latest.json"
    if report_path.stat().st_size > 64 * 1024:
        raise ValueError("Probe report too large")
    report = json.loads(report_path.read_text())
    if report.get("bundleID") != "org.fabricaot.research.a1probe.kexin":
        raise ValueError("Wrong app report")
    log_name = report.get("log", "")
    if not re.fullmatch(r"a1-[0-9]+\.log", log_name):
        raise ValueError("Unsafe probe log name")
    log_path = documents / log_name
    if log_path.stat().st_size > 16 * 1024**2:
        raise ValueError("Probe log too large")
    log = log_path.read_text(errors="replace")
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(report_path, args.output / "native-report.json")
    shutil.copy2(log_path, args.output / "runtime.log")
    result = evaluate(report, log)
    result["simulator"] = args.simulator
    result["nativeReport"] = report
    result["filesSHA256"] = {name: sha256(args.output / name) for name in ("native-report.json", "runtime.log")}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
