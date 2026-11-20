"""Unified, cached and incremental disk-usage service for the Builder.

One module owns every number the storage page shows:

``snapshot``   the cached report for the current layout (no traversal)
``measure``    scan every role once and commit a fresh snapshot
``refresh``    incremental update: replay FSEvents, re-walk only what changed
``start``      launch a detached scan worker (progress file + cancel marker)
``status``     read progress and completed roles of a running worker
``cancel``     stop a worker; an incomplete scan is never committed

Persistence lives in :mod:`storage_index` (SQLite). Incremental updates come
from replaying the macOS FSEvents journal between scans; when that is not
possible the affected subtrees are re-walked, never guessed.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import storage_events
import storage_index
import storage_scan

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_STATES = ('queued', 'running')
ROLES = ('cache', 'builds', 'jobs', 'rust')
SNAPSHOT_SCHEMA = 1
# After this age the cached numbers are still shown, but labelled as such.
STALE_AFTER_SECONDS = 300


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name('.' + path.name + '.' + uuid4().hex)
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def work_dir() -> Path:
    """Progress and cancel markers live beside the index, never in a build root."""
    return storage_index.default_index_path().parent / 'storage-scan'


def status_path(task: str | None = None) -> Path:
    return work_dir() / ((task or 'latest') + '.json')


def cancel_path(task: str) -> Path:
    return work_dir() / (task + '.cancel')


def index_path() -> Path:
    return storage_index.default_index_path()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def configured_layout() -> bool:
    from storage_config import config_path

    return bool(config_path().is_file()
                or (ROOT / 'bundle-manifest.json').is_file()
                or any(os.environ.get('MCFAO_' + role.upper() + '_DIR') for role in ROLES))


def paths_for(data_root: Path | None = None) -> dict:
    """The four measured roles in either the configured or the legacy layout."""
    from storage_config import storage_paths

    if configured_layout() or data_root is None:
        return storage_paths()
    cache = data_root / 'cache'
    if not cache.exists():
        cache = data_root / '.cache'
    return dict(cache=cache, builds=data_root / 'artifacts',
                jobs=data_root / 'artifacts/desktop-jobs',
                rust=data_root / 'desktop/src-tauri/target')


def free_bytes(path: Path) -> int:
    try:
        stats = os.statvfs(path)
        return stats.f_bavail * stats.f_frsize
    except OSError:
        return 0


def layout_key(paths) -> str:
    return json.dumps({role: str(Path(path)) for role, path in sorted(paths.items())},
                      sort_keys=True)


def _volume_data(paths):
    """Filesystem identity and capacity per role; unavailable roots stay visible."""
    from storage_config import existing_parent

    volumes = {}
    ids = {}
    errors = {}
    for role, path in paths.items():
        try:
            parent = existing_parent(path)
            device = str(parent.stat().st_dev)
            usage = shutil.disk_usage(parent)
            mount = parent
            try:
                while mount.parent != mount and mount.parent.stat().st_dev == int(device):
                    mount = mount.parent
            except OSError:
                pass
            volume = volumes.setdefault(device, dict(
                id=device, path=str(mount), totalBytes=usage.total,
                freeBytes=usage.free, roles=[]))
            volume['roles'].append(role)
            ids[role] = device
        except (OSError, ValueError) as error:
            errors[role] = str(error)
    return volumes, ids, errors


def _top_items(root: Path, result) -> list:
    items = [dict(path=str(root / rel), bytes=value)
             for rel, value in result.children.items()]
    items.sort(key=lambda item: (-item['bytes'], item['path']))
    return items[:12]


def _warnings(usage) -> list:
    messages = []
    for row in usage:
        if row.get('available') is False:
            messages.append(f"{row['path']}: {row.get('error', '目录不可用')}")
        elif row.get('error'):
            messages.append(f"{row['path']}: {row['error']}")
            for warning in (row.get('warnings') or [])[:5]:
                messages.append(f"{row['path']}: {warning}")
    return messages


# ---------------------------------------------------------------------------
# Measuring
class Measurement:
    """Result of one pass over the configured roles."""

    def __init__(self, paths, rows, results, volumes, volume_ids):
        self.paths = paths
        self.rows = rows
        self.results = results
        self.volumes = volumes
        self.volume_ids = volume_ids

    @property
    def complete(self) -> bool:
        return all(row.get('available') is not False and not row.get('error')
                   for row in self.rows)

    def report(self, *, state='complete', extra=None, scanned_at=None) -> dict:
        usage = [{key: value for key, value in row.items() if not key.startswith('_')}
                 for row in self.rows]
        for volume in self.volumes.values():
            volume['managedBytes'] = sum(row['bytes'] for row in usage
                                         if row.get('volumeId') == volume['id'])
            volume['otherBytes'] = max(0, volume['totalBytes'] - volume['freeBytes']
                                       - volume['managedBytes'])
        payload = dict(
            usage=usage, volumes=list(self.volumes.values()),
            warnings=_warnings(usage), scannedAt=scanned_at or now(),
            managedBytes=sum(row['bytes'] for row in usage),
            files=sum(row.get('files', 0) for row in usage),
            dirs=sum(row.get('dirs', 0) for row in usage),
            scanState=state, complete=self.complete,
            cache=dict(schema=storage_index.SCHEMA_VERSION,
                       engine=storage_scan.ENGINE_VERSION,
                       index=str(index_path())),
        )
        if extra:
            payload.update(extra)
        return payload


def _cached_nodes(index, root: Path):
    try:
        record = index.root(str(root))
        if (record and record.get('complete')
                and record.get('engine') == storage_scan.ENGINE_VERSION):
            return index.nodes(record['id'])
    except Exception:  # A damaged index must never block a real scan.
        return None
    return None


def measure(paths, *, index=None, progress=None, cancel=None, bulk=True,
            reuse=True, seen=None, deadline=None) -> Measurement:
    """Scan every role once, sharing hard-link de-duplication across roles."""
    from storage_config import existing_parent

    volumes, ids, errors = _volume_data(paths)
    rows = []
    results = {}
    resolved = {}
    for role, path in paths.items():
        row = dict(role=role, path=str(path), bytes=0, items=[], available=True,
                   files=0, dirs=0, cached=False, stale=True, volumeId=None,
                   itemCount=0)
        rows.append(row)
        if role in errors:
            row.update(available=False, error=errors[role])
            continue
        row['volumeId'] = ids.get(role)
        try:
            resolved[role] = Path(path).resolve()
            existing_parent(path)
        except (OSError, RuntimeError, ValueError) as error:
            row.update(available=False, error=str(error))
            continue
    claimed = set()
    seen = seen if seen is not None else set()
    for row in rows:
        if row.get('available') is False:
            continue
        role = row['role']
        root = resolved[role]
        if root in claimed:
            row['error'] = '与另一个存储目录相同，占用已计入该目录。'
            continue
        claimed.add(root)
        excluded = {other for other in resolved.values()
                    if other != root and other.is_relative_to(root)}
        cached_nodes = _cached_nodes(index, root) if (reuse and index is not None) else None
        if not root.exists():
            # A root that has never been created is a genuine zero: there is no
            # unreadable content hiding behind it. It still gets an index row so
            # later events can describe it.
            row.update(bytes=0, files=0, dirs=0, stale=False, scannedAt=now(),
                       complete=True)
            empty = storage_scan.ScanResult(root=str(root))
            empty.nodes = {'': (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1)}
            empty.started_at = time.time()
            results[role] = empty
            continue
        try:
            result = storage_scan.Scanner(
                root, excluded=excluded, index=cached_nodes, progress=progress,
                cancel=cancel, bulk=bulk, seen_hardlinks=seen,
                deadline=deadline).run()
        except storage_scan.ScanCancelled:
            row['cancelled'] = True
            raise
        except OSError as error:
            row.update(available=False, error=str(error))
            continue
        results[role] = result
        row.update(bytes=result.bytes, files=result.files, dirs=result.dirs,
                   items=_top_items(root, result),
                   itemCount=len(result.children), scannedAt=now(),
                   cached=False, stale=False,
                   elapsedMs=int(result.elapsed * 1000), reused=result.reused,
                   walked=result.walked, complete=result.complete)
        if result.error_count:
            row['error'] = '部分内容无法读取，占用统计不完整。'
            row['warnings'] = result.warnings()
        row['complete'] = result.complete
    return Measurement(paths, rows, results, volumes, ids)


# ---------------------------------------------------------------------------
# Persistence
def commit(measurement: Measurement, index, *, event_id=None,
           scanned_at=None) -> None:
    """Persist a complete measurement. Cancelled scans never reach this point.

    A role with read errors is stored as incomplete, so its subtrees are not
    reused by the next incremental pass.
    """
    for row in measurement.rows:
        result = measurement.results.get(row['role'])
        if result is None or not result.nodes:
            continue
        path = str(result.root)
        record = index.root(path)
        root_id = index.upsert_root(path)
        previous = None
        if record and record.get('engine') == storage_scan.ENGINE_VERSION:
            previous = index.nodes(root_id)
        index.replace_nodes(root_id, result.nodes, previous)
        # The cursor must be taken *after* the walk, otherwise a change made
        # during the scan would be assumed to be included in the totals.
        cursor = event_id if event_id is not None else storage_events.current_event_id()
        # `last_scan_at` is when the walk started: events older than that are
        # already reflected in the totals and must not mark the tree dirty.
        began = scanned_at or getattr(result, 'started_at', 0) or time.time()
        index.upsert_root(
            path, engine=storage_scan.ENGINE_VERSION,
            status='complete' if result.complete else 'partial',
            error=row.get('error'), complete=1 if result.complete else 0,
            last_scan_at=began, duration_ms=int(result.elapsed * 1000),
            files=result.files, dirs=result.dirs, bytes=result.bytes,
            event_id=cursor, event_valid=1 if cursor else 0)
    index.save_snapshot(layout_key(measurement.paths), measurement.report())


def snapshot(paths, index=None) -> dict | None:
    """The last committed report for this exact layout, or None."""
    owned = index is None
    index = index or storage_index.open_index()
    if index is None:
        return None
    try:
        payload = index.snapshot(layout_key(paths))
    finally:
        if owned:
            index.close()
    if payload is None:
        return None
    cached_at = payload.pop('_cachedAt', None)
    age = max(0, int(time.time() - cached_at)) if cached_at else None
    payload['scanState'] = 'cached'
    payload['cached'] = True
    payload['ageSeconds'] = age
    payload['stale'] = bool(age is not None and age > STALE_AFTER_SECONDS)
    return payload


# ---------------------------------------------------------------------------
# Targeted invalidation after Builder writes
def invalidate(paths, changed, *, index=None) -> int:
    """Forget cached directories that a Builder action just changed.

    Called after a build, download, extraction or cleanup so the next visit
    re-walks those directories instead of trusting their old totals. This never
    invents numbers: it only drops entries, and the following refresh or scan
    recomputes them. Missing or unusable index state is not an error.
    """
    if not changed:
        return 0
    owned = index is None
    index = index or storage_index.open_index()
    if index is None:
        return 0
    dropped = 0
    try:
        roots = {str(Path(p).resolve()) for p in paths.values()}
        for path in changed:
            # Compare canonical paths: /var and /private/var are the same place.
            try:
                text = str(Path(path).resolve())
            except OSError:
                continue
            for root_path in roots:
                if text == root_path:
                    rels = ['']
                elif text.startswith(root_path + '/'):
                    rels = [text[len(root_path) + 1:]]
                else:
                    continue
                record = index.root(root_path)
                if not record:
                    continue
                dropped += index.invalidate(record['id'], rels)
                # The snapshot is now known to be behind the filesystem.
                index.upsert_root(root_path, last_scan_at=time.time())
    except Exception:  # Invalidation is best effort; a scan still follows.
        return dropped
    finally:
        if owned:
            index.close()
    return dropped


# ---------------------------------------------------------------------------
# Incremental refresh
def _relative_events(paths, index) -> tuple[bool, dict, list, dict]:
    """Replay the journal for every role.

    Returns (trusted, changes, notes, cursors): changed paths relative to each
    root, human-readable reasons when a replay could not be trusted, and the
    journal position to record for the next refresh.
    """
    changes = {}
    cursors = {}
    trusted = True
    notes = []
    for role, path in paths.items():
        try:
            root = str(Path(path).resolve())
        except (OSError, RuntimeError):
            continue
        record = index.root(root)
        if not record or not record.get('event_valid') or not record.get('event_id'):
            # No journal position was recorded for this root (first run, an
            # upgrade from an older index, or a filesystem without events).
            return False, {}, ['没有可用的文件系统事件游标'], {}
        started = record.get('last_scan_at')
        report = storage_events.replay(root, record['event_id'],
                                       newer_than=started)
        if not report['trusted']:
            notes.append(f"{role}: 事件日志不可用（{report['reason']}）")
            trusted = False
            continue
        relative = []
        for changed in report['paths']:
            if changed == root:
                relative.append('')
            elif changed.startswith(root + '/'):
                relative.append(changed[len(root) + 1:])
        changes[root] = sorted(set(relative))
        cursors[root] = report.get('latest') or record['event_id']
    return trusted, changes, notes, cursors


def refresh(paths, *, index=None, bulk=True) -> dict | None:
    """Re-walk only directories reported changed since the last commit.

    Returns None when a trusted incremental update is not possible, so the
    caller can run a full scan. The returned report is marked ``incremental``.
    """
    owned = index is None
    index = index or storage_index.open_index()
    if index is None:
        return None
    try:
        trusted, changes, notes, cursors = _relative_events(paths, index)
        if not trusted:
            return None
        volumes, ids, errors = _volume_data(paths)
        rows = []
        resolved = {}
        for role, path in paths.items():
            row = dict(role=role, path=str(path), bytes=0, items=[], available=True,
                       files=0, dirs=0, cached=False, stale=True,
                       volumeId=ids.get(role), itemCount=0)
            rows.append(row)
            if role in errors:
                row.update(available=False, error=errors[role])
                continue
            try:
                resolved[role] = Path(path).resolve()
            except (OSError, RuntimeError) as error:
                row.update(available=False, error=str(error))
        claimed = set()
        seen = set()
        for row in rows:
            if row.get('available') is False:
                continue
            role = row['role']
            root = resolved[role]
            if root in claimed:
                row['error'] = '与另一个存储目录相同，占用已计入该目录。'
                continue
            claimed.add(root)
            record = index.root(str(root))
            if not record or not record.get('complete'):
                return None
            changed = changes.get(str(root))
            if changed is None:
                return None
            nodes = index.nodes(record['id'])
            if nodes is None:
                return None
            if changed:
                for rel in changed:
                    _forget(nodes, rel)
                if not root.exists():
                    nodes.clear()
            else:
                # Nothing was reported: every cached directory still matches its
                # fingerprint, so the committed totals stand. Re-walking a clean
                # tree would cost more than the cache is saving.
                items = _snapshot_items(index, paths, role)
                row.update(bytes=record['bytes'], files=record['files'],
                           dirs=record['dirs'], items=items,
                           itemCount=len(items), scannedAt=now(),
                           cached=False, stale=False,
                           reused=len(nodes), walked=len(nodes),
                           unchanged=True, complete=True)
                index.upsert_root(str(root), last_scan_at=time.time(),
                                  files=record['files'], dirs=record['dirs'],
                                  bytes=record['bytes'], status='complete',
                                  complete=1,
                                  event_id=cursors.get(str(root)),
                                  event_valid=1 if cursors.get(str(root)) else 0)
                continue
            excluded = {other for other in resolved.values()
                        if other != root and other.is_relative_to(root)}
            if not root.exists():
                # A root that was never created is a complete zero, not a
                # failed read: there is nothing it could be hiding.
                result = storage_scan.ScanResult(root=str(root))
                result.nodes = {'': (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1)}
                result.started_at = time.time()
            else:
                try:
                    result = storage_scan.Scanner(
                        root, excluded=excluded, index=nodes, bulk=bulk,
                        seen_hardlinks=seen).run()
                except OSError as error:
                    row.update(available=False, error=str(error))
                    continue
            row.update(bytes=result.bytes, files=result.files, dirs=result.dirs,
                       items=_top_items(root, result),
                       itemCount=len(result.children), scannedAt=now(),
                       cached=False, stale=False, reused=result.reused,
                       walked=result.walked,
                       elapsedMs=int(result.elapsed * 1000),
                       complete=result.complete)
            if result.error_count:
                row['error'] = '部分内容无法读取，占用统计不完整。'
                row['warnings'] = result.warnings()
            complete = bool(result.complete)
            index.upsert_root(
                str(root), last_scan_at=result.started_at, files=result.files,
                dirs=result.dirs, bytes=result.bytes,
                status='complete' if complete else 'partial',
                complete=1 if complete else 0,
                event_id=cursors.get(str(root)),
                event_valid=1 if cursors.get(str(root)) else 0)
            if complete:
                root_id = index.root(str(root))['id']
                index.replace_nodes(root_id, result.nodes, index.nodes(root_id))
        measurement = Measurement(paths, rows, {}, volumes, ids)
        # Keep the age of the oldest role: an incremental pass only refreshed
        # part of the picture and must not present itself as a full rescan.
        stamps = [row.get('scannedAt') for row in rows if row.get('scannedAt')]
        oldest = min(stamps) if stamps else now()
        payload = measurement.report(
            state='incremental', scanned_at=oldest,
            extra=dict(incremental=True, eventNotes=notes,
                       walked=sum(row.get('walked', 0) for row in rows),
                       reused=sum(row.get('reused', 0) for row in rows)))
        index.save_snapshot(layout_key(paths), payload)
        return payload
    finally:
        if owned:
            index.close()


def _snapshot_items(index, paths, role) -> list:
    """The largest direct children from the committed report."""
    payload = index.snapshot(layout_key(paths)) or {}
    for row in payload.get('usage', []):
        if row.get('role') == role:
            return row.get('items') or []
    return []


def _forget(nodes, rel) -> None:
    """Invalidate exactly what a reported path can have changed.

    FSEvents reports the deepest changed path plus the watched root, never every
    ancestor. So:

    * the root itself is only re-listed (its own files change; children are
      still described by their own events),
    * a known directory is re-walked together with its subtree,
    * anything else (a file, or a path we never indexed) only forces its parent
      to be re-listed, which rediscovers creations and removals.
    """
    if not rel:
        # The watched root is reported for every change below it. Re-listing it
        # rediscovers top-level creations, but a child whose identity still
        # matches the index is left alone.
        nodes.pop('', None)
        return
    if rel in nodes:
        prefix = rel + '/'
        for key in [key for key in nodes if key == rel or key.startswith(prefix)]:
            del nodes[key]
    # The parent must be re-listed so creations and removals are rediscovered.
    parent = rel.rsplit('/', 1)[0] if '/' in rel else ''
    nodes.pop(parent, None)
    # Its other children keep their identity and stay reusable; only the
    # parent's aggregate changes, and the rollup recomputes that.


# ---------------------------------------------------------------------------
# Background worker
def _progress_writer(task: str, paths, index_path_value: str):
    """Return a progress callback that throttles writes to the status file."""
    state = dict(task=task, state='running', startedAt=now(), updatedAt=now(),
                 phase='scanning', files=0, dirs=0, bytes=0, current='',
                 roles={}, completedRoles=[], totalRoles=len(paths),
                 indexPath=index_path_value)
    last = [0.0]
    lock = __import__('threading').Lock()

    def write(force=False):
        stamp = time.monotonic()
        if not force and stamp - last[0] < 0.25:
            return
        last[0] = stamp
        state['updatedAt'] = now()
        _atomic_json(status_path(task), state)

    def progress(fields):
        with lock:
            state.update(fields)
            write()

    def update(**fields):
        with lock:
            state.update(fields)
            write(True)

    return state, progress, update


def run_worker(job_path: Path) -> int:
    """Entry point of the detached scan process."""
    job = _read_json(job_path)
    if not job:
        return 2
    task = job['task']
    paths = {role: Path(value) for role, value in job['paths'].items()}
    state, progress, update = _progress_writer(task, paths, job.get('indexPath', ''))
    marker = cancel_path(task)

    def cancelled() -> bool:
        return marker.exists()

    def terminate(_signal, _frame):
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, terminate)
    except (ValueError, OSError):  # not the main thread
        pass
    index = storage_index.open_index(Path(job['indexPath']) if job.get('indexPath') else None)
    try:
        update(state='running', phase='scanning', pid=os.getpid())
        measurement = measure(paths, index=index, progress=progress, cancel=cancelled,
                              bulk=job.get('bulk', True), reuse=False)
        if cancelled():
            update(state='cancelled', phase='cancelled', finishedAt=now())
            return 0
        if index is not None:
            # commit() takes the journal position itself, after the walk.
            commit(measurement, index)
        payload = measurement.report(state='complete')
        update(state='complete', phase='complete', finishedAt=now(),
               result=payload, files=payload['files'], dirs=payload['dirs'],
               bytes=payload['managedBytes'])
        return 0
    except storage_scan.ScanCancelled:
        update(state='cancelled', phase='cancelled', finishedAt=now())
        return 0
    except KeyboardInterrupt:
        update(state='cancelled', phase='cancelled', finishedAt=now())
        return 0
    except BaseException as error:  # Never leave the UI waiting forever.
        update(state='failed', phase='failed', error=str(error), finishedAt=now())
        return 1
    finally:
        if index is not None:
            index.close()
        try:
            job_path.unlink()
        except OSError:
            pass


def _alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def status(task: str | None = None) -> dict:
    """Progress of a running worker, plus the last committed snapshot."""
    state = _read_json(status_path(task)) or {}
    if state.get('state') in ACTIVE_STATES and not _alive(state.get('pid')):
        state.update(state='interrupted', phase='interrupted',
                     error='扫描进程已退出；未完成的统计不会写入缓存。')
    return state


def cancel(task: str | None = None) -> dict:
    """Ask a worker to stop. Its partial result is never committed."""
    state = _read_json(status_path(task)) or {}
    if not task:
        task = state.get('task')
    if not task:
        return dict(state='idle')
    work_dir().mkdir(parents=True, exist_ok=True)
    cancel_path(task).touch()
    pid = state.get('pid')
    if isinstance(pid, int) and _alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    state.update(state='cancelling', phase='cancelling')
    return state


def start(paths, *, data_root=None) -> dict:
    """Start a detached scan; repeated calls reuse the running worker."""
    task = uuid4().hex
    work_dir().mkdir(parents=True, exist_ok=True)
    with (work_dir() / 'launch.lock').open('a') as lock:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_EX)
        current = status()
        if current.get('state') in ACTIVE_STATES and _alive(current.get('pid')):
            return dict(state='running', task=current.get('task'), reused=True,
                        progress=current)
        job = dict(task=task, paths={role: str(path) for role, path in paths.items()},
                   indexPath=str(index_path()), bulk=True)
        job_path = work_dir() / (task + '.job.json')
        _atomic_json(job_path, job)
        initial = dict(task=task, state='queued', phase='queued', startedAt=now(),
                       updatedAt=now(), files=0, dirs=0, bytes=0, current='',
                       completedRoles=[], totalRoles=len(paths), pid=None)
        _atomic_json(status_path(task), initial)
        _atomic_json(status_path(), initial)
        with (work_dir() / 'worker.log').open('ab') as log:
            child = subprocess.Popen(
                [sys.executable, '-B', str(Path(__file__).resolve()), 'worker',
                 '--job', str(job_path)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, close_fds=True)
        initial['pid'] = child.pid
        initial['state'] = 'running'
        initial['phase'] = 'scanning'
        _atomic_json(status_path(task), initial)
        _atomic_json(status_path(), initial)
        return dict(state='running', task=task, pid=child.pid, reused=False)


# ---------------------------------------------------------------------------
# Public helpers
def inventory(paths=None, *, data_root=None, cancel=None, bulk=True,
              reuse=False, store=False) -> dict:
    """Read-only per-role report with the legacy ``usage``/``volumes`` shape.

    ``store`` commits the result so the next visit can render it instantly.
    ``reuse`` additionally reuses unchanged subtrees from the index.
    """
    targets = paths if paths is not None else paths_for(data_root)
    index = storage_index.open_index() if (reuse or store) else None
    try:
        measurement = measure(targets, index=index, cancel=cancel, bulk=bulk,
                              reuse=reuse)
        if store and index is not None:
            commit(measurement, index)
        return measurement.report()
    finally:
        if index is not None:
            index.close()


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('worker', 'status', 'cancel', 'scan',
                                           'snapshot', 'refresh'))
    parser.add_argument('--job', type=Path)
    parser.add_argument('--task')
    parser.add_argument('--data-root', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'worker':
        return run_worker(args.job)
    if args.action == 'status':
        print(json.dumps(status(args.task), ensure_ascii=False))
        return 0
    if args.action == 'cancel':
        print(json.dumps(cancel(args.task), ensure_ascii=False))
        return 0
    paths = paths_for(args.data_root)
    if args.action == 'snapshot':
        print(json.dumps(snapshot(paths), ensure_ascii=False))
        return 0
    if args.action == 'refresh':
        print(json.dumps(refresh(paths), ensure_ascii=False))
        return 0
    print(json.dumps(inventory(paths), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
