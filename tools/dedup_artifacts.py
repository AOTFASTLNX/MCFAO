#!/usr/bin/env python3
"""Collapse byte-identical build artefacts into APFS clones.

Why clones and never hard links: `ios/C0Harness/embed_graphics_libraries.sh`
runs `codesign --force` against `*.app/Frameworks/*.dylib` **in place**. A hard
link would re-sign every experiment that shares the inode; a clonefile splits on
first write (copy-on-write), so each artefact keeps its own bytes, inode and
signature.

Why this is needed at all: `tools/smoke_mcfao_simulator.py` and the Xcode
"Embed Native Runtime" phase copy `client-graph.dylib` (~222 MB) into every
build product. `shutil.copy2` and plain `cp` allocate fresh blocks, so N builds
cost N x 222 MB. `ditto` clones on APFS, `cp -c` clones explicitly.

Measurement caveat: `du` does not see clone extents, so `du -sh artifacts`
keeps reporting the logical total after deduplication. Only `df` (or APFS
container stats) reflects the reclaimed blocks. Verified on macOS 15 arm64:
400 MB regular copy -> `cp -c` + replace == +401 MB free.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys
import time

DEFAULT_ROOT = "artifacts"
DEFAULT_MIN_AGE = 900  # skip anything a build may still be writing
STATE_NAME = ".dedup-state.json"
CHUNK = 8 << 20


def load_state(root: str) -> dict[str, dict]:
    """Remember which paths are already clones so a re-run reports honestly.

    APFS exposes no userland "are these extents shared" query, so content hashes
    alone cannot distinguish a clone from an independent copy. Without this
    ledger every run would re-report the same logical gigabytes it already
    collapsed (harmless for disk, misleading in the summary).
    """
    path = os.path.join(root, STATE_NAME)
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle).get("files", {})
    except (OSError, ValueError):
        return {}


def save_state(root: str, files: dict[str, dict]) -> None:
    path = os.path.join(root, STATE_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "files": files}, handle, indent=1, ensure_ascii=False)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def free_mb(path: str) -> int:
    out = subprocess.run(
        ["df", "-m", path], capture_output=True, text=True, check=True
    ).stdout.strip().splitlines()[-1]
    return int(out.split()[3])


def collect(root: str, suffix: str, min_bytes: int) -> dict[int, list[tuple[str, float]]]:
    by_size: dict[int, list[tuple[str, float]]] = collections.defaultdict(list)
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(suffix):
                continue
            path = os.path.join(dirpath, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            if stat.st_size < min_bytes:
                continue
            by_size[stat.st_size].append((path, stat.st_mtime))
    return by_size


def duplicate_groups(
    by_size: dict[int, list[tuple[str, float]]]
) -> list[tuple[int, list[tuple[str, float]]]]:
    groups: list[tuple[int, list[tuple[str, float]]]] = []
    for size, entries in by_size.items():
        if len(entries) < 2:
            continue
        by_hash: dict[str, list[tuple[str, float]]] = collections.defaultdict(list)
        for path, mtime in entries:
            by_hash[sha256(path)].append((path, mtime))
        for members in by_hash.values():
            if len(members) > 1:
                # oldest file is the canonical copy; ties broken by shortest path
                members.sort(key=lambda item: (item[1], len(item[0])))
                groups.append((size, members))
    groups.sort(key=lambda group: -group[0] * (len(group[1]) - 1))
    return groups


def replace_with_clone(canonical: str, target: str, expected: str) -> bool:
    """Rewrite `target` as an APFS clone of `canonical`, verified by sha256."""
    staging = target + ".dedup-clone"
    try:
        result = subprocess.run(
            ["cp", "-c", "-p", canonical, staging], capture_output=True, text=True
        )
        if result.returncode != 0:
            sys.stderr.write(f"cp -c failed for {target}: {result.stderr.strip()}\n")
            return False
        if sha256(staging) != expected:
            sys.stderr.write(f"clone verify failed for {target}\n")
            os.remove(staging)
            return False
        os.remove(target)
        os.rename(staging, target)
        return True
    except OSError as exc:
        sys.stderr.write(f"clone failed for {target}: {exc}\n")
        if os.path.exists(staging):
            os.remove(staging)
        return False


def run(
    root: str = DEFAULT_ROOT,
    suffix: str = ".dylib",
    min_age: int = DEFAULT_MIN_AGE,
    min_bytes: int = 1 << 20,
    dry: bool = False,
    log_path: str | None = None,
) -> dict:
    now = time.time()
    groups = duplicate_groups(collect(root, suffix, min_bytes))
    logical = sum(size * (len(members) - 1) for size, members in groups)
    state = load_state(root)

    print(f"{len(groups)} duplicate group(s), {logical / 2**30:.2f} GiB logical")
    before = free_mb(root)

    done, skipped, saved, records = 0, 0, 0, []
    for size, members in groups:
        canonical, canonical_mtime = members[0]
        if now - canonical_mtime < min_age:
            skipped += len(members) - 1
            continue
        expected = sha256(canonical)
        for path, mtime in members[1:]:
            if now - mtime < min_age:
                skipped += 1
                continue
            known = state.get(path)
            if known and known.get("size") == size and known.get("mtime") == mtime:
                continue  # already a verified clone from an earlier run
            if dry:
                done += 1
                saved += size
                records.append({"dup": path, "canonical": canonical, "bytes": size})
                continue
            if replace_with_clone(canonical, path, expected):
                done += 1
                saved += size
                records.append({"dup": path, "canonical": canonical, "bytes": size})
                stat = os.stat(path)
                state[path] = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "sha256": expected,
                    "canonical": canonical,
                }

    after = free_mb(root)
    summary = {
        "root": root,
        "suffix": suffix,
        "dryRun": dry,
        "replaced": done,
        "skipped": skipped,
        "logicalBytes": saved,
        "freeBeforeMb": before,
        "freeAfterMb": after,
        "files": records,
    }
    print(
        f"replaced {done} file(s), skipped {skipped}, "
        f"{saved / 2**30:.2f} GiB logical; df free {before} -> {after} MB"
    )
    if log_path and not dry:
        summary["runAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(log_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=1, ensure_ascii=False)
    if not dry:
        save_state(root, state)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--suffix", default=".dylib")
    parser.add_argument("--min-age", type=int, default=DEFAULT_MIN_AGE)
    parser.add_argument("--min-bytes", type=int, default=1 << 20)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--log", default=None)
    args = parser.parse_args(argv)
    run(
        root=args.root,
        suffix=args.suffix,
        min_age=args.min_age,
        min_bytes=args.min_bytes,
        dry=args.dry,
        log_path=args.log,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
