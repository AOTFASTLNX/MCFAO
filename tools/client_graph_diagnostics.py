"""Read-only Native Image metadata audit and bounded experiment summaries."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path


def audit_metadata(libraries: list[Path], arguments: list[str]) -> dict:
    entries, total = [], 0
    for library in libraries:
        with zipfile.ZipFile(library) as archive:
            members = archive.infolist()
            original_count = sum(not item.filename.startswith("mcfao/mod-files/") for item in members)
            if len(members) > 200_000 or original_count > 100_000:
                raise ValueError("Too many JAR entries")
            seen = set()
            for info in archive.infolist():
                name = info.filename
                if not name.startswith("META-INF/native-image/") or not name.endswith((".json", ".properties")):
                    continue
                if name in seen or info.file_size > 2 * 1024**2:
                    raise ValueError("Duplicate or oversized native metadata: " + name)
                seen.add(name)
                total += info.file_size
                if total > 16 * 1024**2:
                    raise ValueError("Native metadata audit budget exceeded")
                data = archive.read(info)
                item = {"jar": str(library), "entry": name, "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()}
                if name.endswith(".properties"):
                    text = data.decode("utf-8").replace("\\\n", " ")
                    item["properties"] = [line for line in text.splitlines()
                                          if line.strip() and not line.lstrip().startswith(("#", "!"))]
                else:
                    config = json.loads(data)
                    groups = {"reflection": config} if isinstance(config, list) and name.endswith("reflect-config.json") else {}
                    if isinstance(config, list) and name.endswith("jni-config.json"):
                        groups = {"jni": config}
                    if isinstance(config, dict):
                        groups = {k: v for k, v in config.items() if k in ("reflection", "jni", "resources", "bundles")}
                        # Legacy resource configuration has a nested includes list.
                        if isinstance(groups.get("resources"), dict):
                            groups["resources"] = groups["resources"].get("includes", [])
                    item["groups"] = {}
                    for kind, records in groups.items():
                        if not isinstance(records, list):
                            raise ValueError("Unexpected metadata group: " + name)
                        item["groups"][kind] = {
                            "entries": len(records),
                            "unconditionalEntries": sum(isinstance(x, dict) and not x.get("condition") for x in records),
                            "bulkMemberFlags": [
                                {"type": x.get("type", x.get("name")), "flag": key,
                                 "conditional": bool(x.get("condition"))}
                                for x in records if isinstance(x, dict) for key, value in x.items()
                                if value is True and key.startswith(("allDeclared", "allPublic", "queryAll"))],
                            "allResourcePatterns": [x for x in records if isinstance(x, dict)
                                                    and (x.get("pattern") in (".*", "^.*$", "(.*)")
                                                         or x.get("glob") in ("**", "**/*"))]}
                entries.append(item)
    texts = arguments + [line for item in entries for line in item.get("properties", [])]
    return {"scope": "explicit classpath META-INF/native-image metadata and command options only; "
                     "does not enumerate SDK defaults, Feature registrations or inferred reflection",
            "metadataFiles": entries, "metadataBytes": total,
            "preserveAllOccurrences": [x for x in texts if re.search(r"(?:^|\s)-H:Preserve=all(?:\s|$)", x)],
            "explicitConfigurationArguments": [x for x in arguments if "Configuration" in x or "Preserve" in x]}


def parse_time_rss(stderr: str) -> int | None:
    matches = re.findall(r"^\s*(\d+)\s+maximum resident set size\s*$", stderr, re.MULTILINE)
    return int(matches[-1]) if matches else None


def summarize_gc_logs(text: str) -> dict:
    # Parse the pinned HotSpot unified GC log, not Native Image's human progress output.
    pauses = []
    for line in text.splitlines():
        match = re.search(r"GC\((\d+)\) Pause (.*?) (\d+)([KMG])->(\d+)([KMG])\((\d+)([KMG])\) ([\d.]+)ms$", line)
        if match:
            number, kind, before, bu, after, au, capacity, cu, millis = match.groups()
            scale = {"K":1024, "M":1024**2, "G":1024**3}
            pauses.append({"gcID":int(number), "kind":kind,
                "beforeBytes":int(before)*scale[bu], "afterBytes":int(after)*scale[au],
                "capacityBytes":int(capacity)*scale[cu], "pauseSeconds":float(millis)/1000})
    threads = [int(x) for x in re.findall(r"Threads: \d+ runnable, (\d+) total", text)]
    workers = re.findall(r"Parallel Workers: (\d+)", text)
    return {"completedPauseEvents":len(pauses), "pauseSumSeconds":sum(x["pauseSeconds"] for x in pauses),
            "fullGCPauseEvents":sum(x["kind"].startswith("Full") for x in pauses),
            "peakHeapBeforePauseBytes":max((x["beforeBytes"] for x in pauses), default=None),
            "lastHeapAfterPauseBytes":pauses[-1]["afterBytes"] if pauses else None,
            "peakThreadsAtSafepoint":max(threads, default=None),
            "parallelGCWorkers":int(workers[-1]) if workers else None,
            "lastCompletedPauses":pauses[-10:],
            "scope":"completed HotSpot GC pauses in retained logs; values rounded by logger; "
                    "thread samples are safepoints only; no target-iOS metrics or retained-object census"}


def duration_seconds(value: str) -> float:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value)
    if not match:
        raise ValueError("Unexpected JFR duration")
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0)


def summarize_jfr(document: dict) -> dict:
    events = document["recording"]["events"]
    heap = [e["values"] for e in events if e["type"] == "jdk.GCHeapSummary"]
    gc = [e["values"] for e in events if e["type"] == "jdk.GarbageCollection"]
    threads = [e["values"].get("activeCount") for e in events if e["type"] == "jdk.JavaThreadStatistics"]
    after = [x["heapUsed"] for x in heap if x["when"] == "After GC"]
    return {"events": len(events), "gcEvents": len(gc),
            "gcDurationSumSeconds": sum(duration_seconds(x["duration"]) for x in gc),
            "gcPauseSumSeconds": sum(duration_seconds(x["sumOfPauses"]) for x in gc if "sumOfPauses" in x),
            "peakObservedHeapUsedBytes": max((x["heapUsed"] for x in heap), default=None),
            "lastObservedHeapAfterGCBytes": after[-1] if after else None,
            "peakObservedJavaThreads": max((x for x in threads if x is not None), default=None),
            "scope": "recorded GC events and periodic Java thread samples; not retained-object analysis or target-iOS memory"}


def read_analysis_statistics(work: Path) -> list[dict]:
    result = []
    for path in sorted(work.rglob("analysis_stats_*.json")):
        if path.stat().st_size > 2 * 1024**2:
            raise ValueError("Oversized analysis statistics")
        result.append({"path": str(path.relative_to(work)), "statistics": json.loads(path.read_text())})
    return result
