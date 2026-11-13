#!/usr/bin/env python3
"""Summarize local Metal telemetry without extracting saves or uploading logs."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
import zipfile

MAX_LOG_BYTES = 64 * 1024 * 1024
FIELD = re.compile(r"([a-z][a-z0-9_]*)=(-?(?:\d+(?:\.\d*)?|\.\d+))")
MARKER = re.compile(r"\[Metal(Perf|Presented)\]")


def read_log(path: Path) -> str:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            candidates = [item for item in archive.infolist()
                          if not item.is_dir()
                          and re.search(r"(?:^|/)c0-logs/run-\d+\.log$", item.filename)]
            if not candidates:
                raise ValueError("archive contains no c0-logs/run-<timestamp>.log")
            item = max(candidates, key=lambda item: int(re.search(r"run-(\d+)\.log$", item.filename).group(1)))
            if item.file_size > MAX_LOG_BYTES:
                raise ValueError("selected log exceeds 64 MiB")
            return archive.read(item).decode("utf-8", errors="replace")
    if path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("log exceeds 64 MiB")
    return path.read_text(encoding="utf-8", errors="replace")


def parse_windows(text: str) -> dict[str, list[dict[str, float]]]:
    result: dict[str, list[dict[str, float]]] = {"submitted": [], "presented": []}
    for line in text.splitlines():
        marker = MARKER.search(line)
        if not marker:
            continue
        numbers = {key: float(value) for key, value in FIELD.findall(line[marker.end():])}
        if not numbers or not all(math.isfinite(value) for value in numbers.values()):
            continue
        result["presented" if marker.group(1) == "Presented" else "submitted"].append(numbers)
    return result


def summarize(text: str, discard: int = 0, last: int = 3) -> dict:
    if discard < 0 or last < 1:
        raise ValueError("discard must be nonnegative and last must be positive")
    windows = parse_windows(text)
    selected = {kind: items[discard:][-last:] for kind, items in windows.items()}
    legacy = any("submit_wait_ms" in item for item in selected["submitted"])
    modern = any("cpu_sync_wait_ms" in item for item in selected["submitted"])
    return {
        "total_windows": {kind: len(items) for kind, items in windows.items()},
        "selected_windows": selected,
        "interpretation": {
            "legacy_wait": "submit_wait_ms combines CPU synchronization and frame-slot waits; do not separate them" if legacy else None,
            "legacy_gpu": "legacy final_command_gpu_ms is sampled before completion and cannot establish GPU time" if legacy else None,
            "modern_gpu": "gpu_command_sum_ms_per_submit is completed command-buffer time in an asynchronous window, not GPU utilization or end-to-end frame time" if modern else None,
            "percentiles": "P95/P99 are per 300-interval window; do not average them into a global percentile",
            "comparison": "compare warmed-up runs of the same scene, settings, device and thermal state; CPU and GPU times can overlap",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="c0 run log or user-provided ZIP; latest run is selected")
    parser.add_argument("--discard", type=int, default=0, help="discard this many initial windows of each type")
    parser.add_argument("--last", type=int, default=3, help="report at most this many remaining windows of each type")
    args = parser.parse_args()
    try:
        report = summarize(read_log(args.log), args.discard, args.last)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
