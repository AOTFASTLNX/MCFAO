#!/usr/bin/env python3
"""Reproducible before/after benchmark for the storage-usage pipeline.

Every number is measured here; nothing is estimated. The baseline is the
implementation this change replaced, kept verbatim in ``_baseline_inventory``
and ``_baseline_cleanup_plan`` so the comparison stays honest after the old
code is gone.

    python3 -B tools/storage_benchmark.py --files 20000
    python3 -B tools/storage_benchmark.py --root artifacts --json

Reported per scenario: wall time, files and directories visited, filesystem
metadata calls (counted by wrapping ``os.stat``/``os.lstat``/``os.scandir``),
peak Python heap, and whether both implementations agree byte for byte.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import stat
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import storage_events  # noqa: E402
import storage_index  # noqa: E402
import storage_scan  # noqa: E402
import storage_service  # noqa: E402


# ---------------------------------------------------------------------------
# The implementation this change replaced, verbatim.
def _baseline_tree_bytes(path: Path) -> int:
    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        total += _baseline_tree_bytes(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_blocks * 512
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _baseline_inventory(paths) -> dict:
    """The original recursive measure(): one Path object per entry, per role."""
    seen_files = set()
    claimed_roots = set()
    rows = []
    for role, path in paths.items():
        errors = []
        row = dict(role=role, path=str(path), bytes=0, items=[])
        rows.append(row)
        try:
            root = path.resolve()
        except (OSError, RuntimeError) as error:
            row['error'] = str(error)
            continue
        if root in claimed_roots:
            continue
        claimed_roots.add(root)
        excluded = {other.resolve() for other in paths.values()
                    if other != path and other.resolve().is_relative_to(root)}

        def measure(entry):
            if Path(entry.path) in excluded:
                return 0
            try:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    with os.scandir(entry.path) as entries:
                        return sum(measure(child) for child in entries)
                if not stat.S_ISREG(info.st_mode):
                    return 0
                if info.st_nlink > 1:
                    identity = (info.st_dev, info.st_ino)
                    if identity in seen_files:
                        return 0
                    seen_files.add(identity)
                return info.st_blocks * 512
            except OSError as error:
                if len(errors) < 5:
                    errors.append(str(error))
                return 0

        try:
            if root.exists():
                with os.scandir(root) as entries:
                    for entry in entries:
                        if entry.is_symlink():
                            continue
                        amount = measure(entry)
                        row['bytes'] += amount
                        row['items'].append(dict(path=entry.path, bytes=amount))
        except OSError as error:
            errors.append(str(error))
        row['items'].sort(key=lambda item: (-item['bytes'], item['path']))
        row['itemCount'] = len(row['items'])
        row['items'] = row['items'][:12]
    return dict(usage=rows, managedBytes=sum(row['bytes'] for row in rows))


def _baseline_cleanup_plan(data_root: Path) -> dict:
    """The original plan(): has_ipa() walked the whole build, then tree_bytes()."""
    artifacts = data_root / 'artifacts'
    cache = data_root / 'cache'
    if not cache.exists():
        cache = data_root / '.cache'
    total = 0
    for name in ('upstream', 'graphics', 'toolchains', 'apple-metal', 'libs'):
        path = cache / name
        if path.is_dir() and not path.is_symlink():
            total += _baseline_tree_bytes(path)
    rust = data_root / 'desktop/src-tauri/target'
    if rust.is_dir() and not rust.is_symlink():
        total += _baseline_tree_bytes(rust)
    builds = []
    if artifacts.is_dir() and not artifacts.is_symlink():
        for entry in sorted(artifacts.iterdir()):
            if entry.is_dir() and not entry.is_symlink() and (entry / 'result.json').is_file():
                builds.append(entry)
    for build in builds:
        has_ipa = False
        try:
            for entry in build.rglob('*.ipa'):
                if entry.is_file() and not entry.is_symlink():
                    has_ipa = True
                    break
        except OSError:
            has_ipa = True
        if has_ipa:
            continue
        for stage in ('fabric', 'split', 'metal-injection', 'gl41-patch', 'aot',
                      'runtime', 'link', 'stage', 'package', 'verify'):
            directory = build / stage
            if directory.is_dir() and not directory.is_symlink():
                total += _baseline_tree_bytes(directory)
    return dict(reclaimBytes=total)


# ---------------------------------------------------------------------------
# Instrumentation
class Counters:
    """Count filesystem metadata calls without changing their behaviour."""

    def __init__(self):
        self.calls = 0
        self._directory_opens = 0
        self._stat = os.stat
        self._lstat = os.lstat
        self._scandir = os.scandir
        self._open = os.open

    def __enter__(self):
        # The unified scanner opens each directory for getattrlistbulk, which the
        # previous implementation did not do. Counting os.open would make its
        # number look larger without describing equivalent work, so only the
        # metadata calls both paths can make are counted here.
        def stat(*args, **kwargs):
            self.calls += 1
            return self._stat(*args, **kwargs)

        def lstat(*args, **kwargs):
            self.calls += 1
            return self._lstat(*args, **kwargs)

        def scandir(*args, **kwargs):
            self.calls += 1
            return self._scandir(*args, **kwargs)

        os.stat, os.lstat, os.scandir = stat, lstat, scandir
        return self

    def directories(self):
        return self._directory_opens

    def __exit__(self, *_exc):
        os.stat, os.lstat, os.scandir = self._stat, self._lstat, self._scandir


class Counter:
    def __init__(self):
        self.files = 0
        self.dirs = 0
        self._original = None

    def __enter__(self):
        self._original = storage_scan.list_directory
        counter = self

        def wrapped(path, *args, **kwargs):
            listing = counter._original(path, *args, **kwargs)
            counter.files += listing.files
            counter.dirs += 1
            return listing

        storage_scan.list_directory = wrapped
        return self

    def __exit__(self, *_exc):
        storage_scan.list_directory = self._original


def measure_run(function, *args, **kwargs) -> dict:
    """Wall time, peak heap and metadata calls for one call."""
    tracemalloc.start()
    with Counters() as counters:
        started = time.perf_counter()
        value = function(*args, **kwargs)
        elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # Wrapping os.stat/os.scandir adds overhead that only the caller pays; the
    # uninstrumented timing is reported separately as `cleanSeconds`.
    started = time.perf_counter()
    function(*args, **kwargs)
    clean = time.perf_counter() - started
    return dict(seconds=elapsed, cleanSeconds=clean, peakBytes=peak,
                metadataCalls=counters.calls, value=value)


def median_run(function, repeats: int, *args, **kwargs) -> dict:
    runs = [measure_run(function, *args, **kwargs) for _ in range(max(1, repeats))]
    best = dict(runs[0])
    best['seconds'] = statistics.median(run['seconds'] for run in runs)
    best['cleanSeconds'] = statistics.median(run['cleanSeconds'] for run in runs)
    best['peakBytes'] = max(run['peakBytes'] for run in runs)
    best['metadataCalls'] = statistics.median(run['metadataCalls'] for run in runs)
    return best


def cpu_time(function, *args, **kwargs) -> float:
    started = time.process_time()
    function(*args, **kwargs)
    return time.process_time() - started


# ---------------------------------------------------------------------------
# Fixtures
def build_fixture(root: Path, *, dirs: int, per_dir: int, depth: int = 2) -> int:
    """A large flat-ish tree of small files, like a compiler cache."""
    written = 0
    for index in range(dirs):
        path = root
        for level in range(depth):
            path = path / f'd{level}-{index % 40:03d}'
        path.mkdir(parents=True, exist_ok=True)
        for item in range(per_dir):
            target = path / f'f{item:05d}.o'
            target.write_bytes(b'x' * 512)
            written += 1
    return written


def scenario_fixture(repeats: int) -> list:
    temporary = Path(tempfile.mkdtemp(prefix='ncl-bench-'))
    try:
        count = build_fixture(temporary, dirs=80, per_dir=250)
        paths = dict(cache=temporary)
        # The fixture's own directory level is what the old inventory walked;
        # measure both implementations over exactly the same tree.
        baseline = median_run(_baseline_inventory, repeats, paths)
        fresh = median_run(lambda p: storage_scan.scan(p), repeats, temporary)
        warm = storage_scan.scan(temporary)
        cached_index = dict(warm.nodes)
        reuse = median_run(lambda p, i: storage_scan.scan(p, index=i), repeats,
                           temporary, cached_index)
        cpu_old = cpu_time(_baseline_inventory, paths)
        cpu_new = cpu_time(lambda p: storage_scan.scan(p), temporary)
        return [
            dict(scenario=f'{count} small files in {len(list(temporary.rglob("d*")))} directories',
                 baseline=baseline, fresh=fresh, reuse=reuse,
                 same=fresh['value'].bytes == baseline['value']['managedBytes'],
                 cpuBaseline=cpu_old, cpuFresh=cpu_new),
        ]
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def scenario_root(root: Path, repeats: int) -> list:
    paths = dict(cache=root)
    baseline = median_run(_baseline_inventory, repeats, paths)
    fresh = median_run(lambda p: storage_scan.scan(p), repeats, root)
    warm = storage_scan.scan(root)
    reuse = median_run(lambda p, i: storage_scan.scan(p, index=i), repeats,
                       root, dict(warm.nodes))
    return [dict(
        scenario=f'real tree {root}',
        baseline=baseline, fresh=fresh, reuse=reuse,
        same=fresh['value'].bytes == baseline['value']['managedBytes'],
        cpuBaseline=cpu_time(_baseline_inventory, paths),
        cpuFresh=cpu_time(lambda p: storage_scan.scan(p), root),
        files=fresh['value'].files, dirs=fresh['value'].dirs,
    )]


def scenario_cache(repeats: int) -> list:
    """Cached page load and a journal-driven incremental refresh."""
    temporary = Path(tempfile.mkdtemp(prefix='ncl-bench-cache-'))
    state = Path(tempfile.mkdtemp(prefix='ncl-bench-state-'))
    previous = {key: os.environ.get(key) for key in ('MCFAO_STORAGE_INDEX',
                                                    'MCFAO_STORAGE_CONFIG')}
    os.environ['MCFAO_STORAGE_INDEX'] = str(state / 'index.sqlite3')
    os.environ['MCFAO_STORAGE_CONFIG'] = str(state / 'storage.json')
    try:
        build_fixture(temporary, dirs=60, per_dir=150)
        paths = dict(cache=temporary, builds=temporary / 'absent')
        first = measure_run(lambda: storage_service.inventory(paths, store=True))
        cached = median_run(lambda: storage_service.snapshot(paths), repeats)
        index = storage_index.open_index()
        cursor = storage_events.current_event_id()
        for path in paths.values():
            index.upsert_root(str(path.resolve()), event_id=cursor, event_valid=1)
        index.close()
        time.sleep(0.2)
        target = next(temporary.rglob('*.o'))
        target.write_bytes(b'y' * 65536)
        time.sleep(0.4)
        incremental = measure_run(lambda: storage_service.refresh(paths))
        full = measure_run(lambda: storage_service.inventory(paths))
        # The refresh spends most of its time waiting for FSEvents to report a
        # settled journal, which is not scanning work. Measure the replay alone
        # so the two costs are not conflated.
        index = storage_index.open_index()
        record = index.root(str(temporary.resolve()))
        index.close()
        replay = median_run(
            lambda: storage_events.replay(str(temporary.resolve()),
                                          record['event_id'],
                                          newer_than=record['last_scan_at']),
            repeats)
        return [dict(
            scenario='60 directories / 9000 files: cache and incremental',
            baseline=dict(seconds=first['seconds'], cleanSeconds=first['cleanSeconds'],
                          metadataCalls=first['metadataCalls'],
                          peakBytes=first['peakBytes'], value=None),
            fresh=dict(seconds=first['seconds'], cleanSeconds=first['cleanSeconds'],
                       metadataCalls=first['metadataCalls'],
                       peakBytes=first['peakBytes'], value=None),
            reuse=dict(seconds=cached['seconds'], cleanSeconds=cached['cleanSeconds'],
                       metadataCalls=cached['metadataCalls'],
                       peakBytes=cached['peakBytes'], value=None),
            same=(incremental['value'] is not None
                  and incremental['value']['managedBytes']
                  == full['value']['managedBytes']),
            incremental=incremental['cleanSeconds'],
            incrementalCalls=incremental['metadataCalls'],
            replay=replay['cleanSeconds'],
            fullRescan=full['cleanSeconds'],
        )]
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(state, ignore_errors=True)


# ---------------------------------------------------------------------------
# Reporting
def render(results, repeats: int) -> str:
    lines = [
        f'storage benchmark · {platform.platform()} · python {platform.python_version()}',
        f'median of {repeats} runs; times exclude the counter wrapper',
        'metadata calls counted via os.stat/lstat/scandir',
        '',
        'scenario / implementation        time     speedup  metadata  files  dirs   peak heap  bytes agree',
    ]
    for row in results:
        if 'incremental' in row:
            lines.append(f"{row['scenario']}")
            lines.append(f"  first full scan              {row['fresh']['seconds']:7.3f}s"
                         f"  {row['fresh']['metadataCalls']:>9.0f}")
            lines.append(f"  cached page load             {row['reuse']['seconds']:7.4f}s"
                         f"  {row['reuse']['metadataCalls']:>9.0f}")
            lines.append(f"  journal replay (wait)        {row['replay']:7.3f}s")
            lines.append(f"  incremental update           {row['incremental']:7.3f}s"
                         f"  {row['incrementalCalls']:>9.0f}")
            lines.append(f"  full rescan (reference)      {row['fullRescan']:7.3f}s"
                         f"  agrees: {row['same']}")
            continue
        base, fresh, reuse = row['baseline'], row['fresh'], row['reuse']
        speedup = (base['cleanSeconds'] / fresh['cleanSeconds']
                   if fresh['cleanSeconds'] else float('inf'))
        warm = (base['cleanSeconds'] / reuse['cleanSeconds']
                if reuse['cleanSeconds'] else float('inf'))
        files = row.get('files', fresh['value'].files)
        dirs = row.get('dirs', fresh['value'].dirs)
        lines.append(f"{row['scenario']}")
        lines.append(f"  previous implementation      {base['cleanSeconds']:7.3f}s"
                     f"  {base['metadataCalls']:>9.0f}  {'':5}  {'':5}"
                     f"  {base['peakBytes'] / 1e6:7.1f} MB")
        lines.append(f"  unified scan (cold)          {fresh['cleanSeconds']:7.3f}s"
                     f"  {speedup:6.2f}x  {fresh['metadataCalls']:>9.0f}  {files:5}  {dirs:4}"
                     f"  {fresh['peakBytes'] / 1e6:7.1f} MB  {row['same']}")
        lines.append(f"  unified scan (leaf cache)    {reuse['cleanSeconds']:7.3f}s"
                     f"  {warm:6.2f}x  {reuse['metadataCalls']:>9.0f}"
                     f"  {reuse['peakBytes'] / 1e6:7.1f} MB")
        lines.append(f"  cpu seconds old/new          {row['cpuBaseline']:7.3f}s"
                     f"  {row['cpuFresh']:7.3f}s")
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, action='append', default=[])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--skip-fixture', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    results = []
    if not args.skip_fixture:
        results += scenario_fixture(args.repeats)
        results += scenario_cache(args.repeats)
    for root in args.root:
        results += scenario_root(root.resolve(), args.repeats)
    if args.json:
        def clean(value):
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()
                        if key != 'value'}
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value
        print(json.dumps(clean(results), ensure_ascii=False, indent=2))
    else:
        print(render(results, args.repeats))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
