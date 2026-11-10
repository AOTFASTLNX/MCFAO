#!/usr/bin/env python3
"""Supervise one client-graph analysis run and take scheduled thread dumps of the build JVM.

Observation only: no analysis option is changed here. The dump targets the child HotSpot JVM
that runs the image builder (the `java @.../vminvocation.args` child), because the native-image
driver and the builder are separate processes. Thread dumps land in the run's analysis/stdout.log
because SIGQUIT output goes to the process stdout.

This does not create evidence for any Gate and does not establish retained memory.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_schedule(text: str) -> list[float]:
    values = []
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            continue
        value = float(piece)
        if value <= 0:
            raise ValueError("thread-dump offsets must be positive")
        values.append(value)
    if not values:
        raise ValueError("empty thread-dump schedule")
    return sorted(values)


def find_builder_pid(ps_output: str, marker: str) -> int | None:
    """Return the pid of the `java @...` builder child whose command mentions marker."""
    candidates = []
    for line in ps_output.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_text, _, command = line.partition(" ")
        command = command.strip()
        if marker not in command:
            continue
        if not pid_text.isdigit():
            continue
        parts = command.split()
        if not parts:
            continue
        if not parts[0].endswith("/bin/java") or len(parts) < 2 or not parts[1].startswith("@"):
            continue
        candidates.append(int(pid_text))
    if not candidates:
        return None
    return max(candidates)


def snapshot_ps() -> str:
    return subprocess.run(["/bin/ps", "-Ao", "pid=,command="], capture_output=True, text=True, check=False).stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="fresh directory for the probe run")
    parser.add_argument("--at", default="20,40,70", help="comma separated offsets in seconds")
    parser.add_argument("--probe-args", default="", help="extra arguments passed to probe_client_graph.py")
    args = parser.parse_args(argv)
    schedule = parse_schedule(args.at)
    if args.output.exists():
        parser.error("--output must not exist")
    command = [sys.executable, "-B", str(ROOT / "tools/probe_client_graph.py"),
               "--output", str(args.output.absolute())]
    if args.probe_args:
        command.extend(args.probe_args.split())
    started = time.time()
    log = args.output.parent / (args.output.name + "-supervisor.log")
    with open(log, "w") as stream:
        stream.write(json.dumps({"argv": command}) + "\n")
        stream.flush()
        probe = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        records = []
        pending = list(schedule)
        while probe.poll() is None and pending:
            offset = pending[0]
            remaining = offset - (time.time() - started)
            if remaining > 0:
                time.sleep(min(remaining, 1.0))
                continue
            pending.pop(0)
            pid = find_builder_pid(snapshot_ps(), str(args.output.absolute()))
            record = {"atOffsetSeconds": offset, "elapsedSeconds": round(time.time() - started, 2), "builderPid": pid}
            if pid is None:
                record["result"] = "builder-not-found"
            else:
                try:
                    os.kill(pid, signal.SIGQUIT)
                    record["result"] = "sigquit-sent"
                except OSError as error:
                    record["result"] = "signal-failed: " + str(error)
            stream.write(json.dumps(record) + "\n")
            stream.flush()
            records.append(record)
        rest, _ = probe.communicate()
        stream.write("probeExitCode=" + str(probe.returncode) + "\n")
        stream.write(rest or "")
    summary = {"status": "OBSERVED" if records and all(r["result"] == "sigquit-sent" for r in records) else "INCOMPLETE",
               "scope": "thread dumps only; no Gate promotion, no retained-memory measurement",
               "scheduleSeconds": schedule, "records": records,
               "probeExitCode": probe.returncode,
               "probeOutput": str(args.output.absolute()),
               "log": str(log)}
    (args.output.parent / (args.output.name + "-supervisor.json")).write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
