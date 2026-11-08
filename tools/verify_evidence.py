#!/usr/bin/env python3
"""Verify captured log/binary hashes; this cannot certify game or device behavior."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from bootstrap_toolchain import ROOT, sha256


def verify(root: Path) -> dict:
    failures = []
    command_count = 0
    binary_count = 0
    report_file_count = 0
    for manifest in sorted(root.rglob("command.json")):
        data = json.loads(manifest.read_text())
        command_count += 1
        for name, expected in data["logs"].items():
            path = manifest.parent / name
            if not path.is_file() or path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
                failures.append(str(path))
    for manifest in sorted(root.rglob("result.json")):
        data = json.loads(manifest.read_text())
        for name, expected in data.get("filesSHA256", {}).items():
            path = manifest.parent / name
            report_file_count += 1
            if not path.is_file() or sha256(path) != expected:
                failures.append(str(path))
        for entry in data.get("archives", {}).values():
            path = Path(entry["path"])
            binary_count += 1
            if not path.is_file() or sha256(path) != entry["sha256"]:
                failures.append(str(path))
        if data.get("framework") and data.get("sha256"):
            path = Path(data["framework"]) / "FabricAOTProbe"
            binary_count += 1
            if not path.is_file() or sha256(path) != data["sha256"]:
                failures.append(str(path))
        for name, expected in data.get("binaries", {}).items():
            path = manifest.parent / name
            binary_count += 1
            if not path.is_file() or path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
                failures.append(str(path))
        if data.get("mode") in ("jvm", "desktop-aot") and data["status"] == "PASS":
            stage = "run-jvm" if data["mode"] == "jvm" else "run-desktop-aot"
            command = json.loads((manifest.parent / stage / "command.json").read_text())
            if command["exitCode"] != 0 or command["timedOut"] or "A1_SEMANTICS_PASS" not in (manifest.parent / stage / "stdout.log").read_text().splitlines():
                failures.append(str(manifest) + ": invalid semantic PASS")
        if data.get("mode", "").startswith("ios-") and data.get("iosGateA1") != "BLOCKED":
            failures.append(str(manifest) + ": unsupported iPhone gate promotion")
    return {"status": "PASS" if not failures else "FAIL", "commandsChecked": command_count,
            "binariesChecked": binary_count, "reportFilesChecked": report_file_count, "failures": failures,
            "scope": "saved evidence integrity only; device/game Gates remain independent"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify(args.root)
    sources = {}
    for directory, names, files in os.walk(ROOT):
        ignored = {".git", ".cache", "artifacts", "__pycache__", "xcuserdata"}
        if Path(directory) == ROOT:
            ignored |= {".agents", ".codex"}
        names[:] = sorted(name for name in names if name not in ignored)
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_file() and name != ".DS_Store":
                sources[str(path.relative_to(ROOT))] = sha256(path)
    result["sourceFilesSHA256"] = sources
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "sourceFilesSHA256"}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
