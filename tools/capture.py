#!/usr/bin/env python3
"""Capture one explicit argv, its exit status, timeout, and output without a shell."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def capture(argv: list[str], directory: Path, timeout: int = 180, cwd: Path = ROOT) -> dict:
    directory = directory.absolute()
    directory.mkdir(parents=True, exist_ok=False)
    start = datetime.now(timezone.utc).isoformat()
    # Preserve PATH/SDK lookup, but prevent inherited Java agents/classpaths.
    env = dict(os.environ)
    for name in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH"):
        env.pop(name, None)
    temporary = directory / "tmp"
    temporary.mkdir()
    env["TMPDIR"] = str(temporary)
    timed_out = False
    with (directory / "stdout.log").open("wb") as out, (directory / "stderr.log").open("wb") as err:
        try:
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=err,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                if os.environ.get("MCFAO_STREAM_LOGS") == "1":
                    deadline = time.monotonic() + timeout
                    readers = [(directory / name).open("rb") for name in ("stdout.log", "stderr.log")]
                    try:
                        while child.poll() is None:
                            for reader in readers:
                                chunk = reader.read(65536)
                                if chunk:
                                    print(chunk.decode("utf-8", errors="replace"), end="", flush=True)
                            if time.monotonic() >= deadline:
                                raise subprocess.TimeoutExpired(argv, timeout)
                            time.sleep(0.2)
                        for reader in readers:
                            print(reader.read().decode("utf-8", errors="replace"), end="", flush=True)
                        code = child.wait()
                    finally:
                        for reader in readers:
                            reader.close()
                else:
                    code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    code = child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    code = child.wait()
        except OSError as exc:
            err.write(f"{type(exc).__name__}: {exc}\n".encode())
            code = 127
    result = {"argv": argv, "cwd": str(cwd.absolute()), "startedUTC": start,
              "temporaryDirectory": str(temporary),
              "finishedUTC": datetime.now(timezone.utc).isoformat(),
              "exitCode": code, "timedOut": timed_out,
              "logs": {}}
    for name in ("stdout.log", "stderr.log"):
        path = directory / name
        result["logs"][name] = {"bytes": path.stat().st_size,
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (directory / "command.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--cwd", type=Path, default=ROOT)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.timeout < 1:
        parser.error("Provide a command after -- and a positive timeout")
    result = capture(command, args.output, args.timeout, args.cwd)
    print(json.dumps(result, indent=2))
    return 124 if result["timedOut"] else result["exitCode"] if result["exitCode"] >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
