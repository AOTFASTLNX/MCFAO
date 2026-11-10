"""Poll the device for a new C0Harness run log.

The device can be locked at any time, and devicectl refuses to launch a foreground app while it is.
Rather than block on that, this watcher keeps copying the app container until a run log appears that
the recorded baseline does not contain, then prints it. Nothing is launched and nothing on the
device is modified, so it cannot disturb a run the user starts by tapping the icon.

Usage: await_c0_log.py --device <UDID> --baseline <dir> --output <dir> [--minutes 12]
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

BUNDLE = "org.fabricaot.research.c0.kexin"


def copy_documents(device: str, destination: Path) -> bool:
    shutil.rmtree(destination, ignore_errors=True)
    completed = subprocess.run(
        ["xcrun", "devicectl", "device", "copy", "from", "--device", device,
         "--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
         "--source", "Documents", "--destination", str(destination)],
        capture_output=True, text=True)
    return completed.returncode == 0 and (destination / "c0-logs").is_dir()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--baseline", type=Path, required=True, help="logs already collected")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minutes", type=int, default=12)
    args = parser.parse_args()

    known = {p.name for p in (args.baseline / "c0-logs").glob("*.log")}
    staging = args.output.parent / ".poll"
    deadline = time.time() + args.minutes * 60
    print(f"watching for a log newer than {len(known)} collected baseline file(s)")

    while time.time() < deadline:
        time.sleep(5)
        if not copy_documents(args.device, staging):
            continue  # locked, unplugged, or the container is busy - just retry
        fresh = sorted({p.name for p in (staging / "c0-logs").glob("*.log")} - known)
        if not fresh:
            continue
        args.output.mkdir(parents=True, exist_ok=True)
        for name in fresh:
            shutil.copy2(staging / "c0-logs" / name, args.output / name)
        newest = args.output / fresh[-1]
        print(json.dumps({"newLogs": fresh, "newest": str(newest)}, indent=2))
        print(newest.read_text(errors="replace"))
        return 0

    print("no new run log within the watch window")
    return 1


if __name__ == "__main__":
    sys.exit(main())
