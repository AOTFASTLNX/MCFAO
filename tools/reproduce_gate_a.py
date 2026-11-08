#!/usr/bin/env python3
"""Re-run available research checks in a fresh directory; do not promote iOS Gates."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from capture import ROOT


def main():
    home = ROOT / ".cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home"
    if not (home / "bin/native-image").is_file():
        print("Run tools/bootstrap_toolchain.py first.", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = ROOT / "artifacts/a1" / ("rerun-" + stamp)
    output.mkdir(parents=True, exist_ok=False)
    results = {}
    for mode in ("jvm", "desktop-aot", "ios-compile", "ios-relocatable"):
        command = [sys.executable, "-B", "tools/run_a1_probe.py", "--graalvm-home", str(home),
                   "--output", str(output / mode), "--mode", mode]
        result = subprocess.run(command, cwd=ROOT)
        results[mode] = result.returncode
    (output / "rerun.json").write_text(json.dumps({"exitCodes": results, "iosGateA1": "BLOCKED"}, indent=2) + "\n")
    print(f"New evidence: {output}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
