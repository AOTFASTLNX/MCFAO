"""macOS FSEvents journal replay used to invalidate cached directory sizes.

The builder never keeps a long-lived daemon. Instead, before showing a cached
snapshot it asks the system log what happened since the event id recorded by the
last successful scan. That is what makes an update incremental without a
background process, and it survives the application being closed.

FSEvents is explicitly best-effort: events can be dropped, the journal can be
purged after a reboot or volume change, and the id space is per-boot. Every
call therefore reports whether the replay is trustworthy; callers fall back to
a normal scan when it is not. Nothing here is allowed to influence what may be
deleted.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
import threading
import time

UTF8 = 0x08000100
# FileEvents: per-file paths; NoDefer: deliver the first event promptly;
# WatchRoot: a rename of the watched root is reported rather than followed;
# UseCFTypes: the paths argument is a CFArray instead of a char**.
STREAM_FLAGS = 0x00000010 | 0x00000020 | 0x00000001
FLAG_MUST_SCAN_SUBDIRS = 0x00000001
FLAG_USER_DROPPED = 0x00000002
FLAG_KERNEL_DROPPED = 0x00000004
FLAG_EVENT_IDS_WRAPPED = 0x00000008
FLAG_ROOT_CHANGED = 0x00000020
FLAG_MOUNT = 0x00000040
FLAG_UNMOUNT = 0x00000080
FLAG_ITEM_CREATED = 0x00000100
FLAG_ITEM_REMOVED = 0x00000200
FLAG_ITEM_RENAMED = 0x00000400
FLAG_ITEM_MODIFIED = 0x00001000
FLAG_HISTORY_DONE = 0x00080000
# Any of these means the journal cannot be trusted to describe every change.
UNTRUSTWORTHY = (FLAG_USER_DROPPED | FLAG_KERNEL_DROPPED | FLAG_EVENT_IDS_WRAPPED
                 | FLAG_ROOT_CHANGED | FLAG_UNMOUNT | FLAG_MUST_SCAN_SUBDIRS)

CALLBACK = None
_LOCK = threading.Lock()
_LIBRARIES = None


class JournalUnavailable(RuntimeError):
    pass


def available() -> bool:
    return sys.platform == 'darwin' and _libraries() is not None


def _libraries():
    global _LIBRARIES, CALLBACK
    if _LIBRARIES is not None:
        return _LIBRARIES
    if sys.platform != 'darwin':
        _LIBRARIES = False
        return False
    try:
        cf = ctypes.CDLL(ctypes.util.find_library('CoreFoundation'))
        fs = ctypes.CDLL(ctypes.util.find_library('CoreServices'))
    except (OSError, TypeError):  # pragma: no cover - defensive
        _LIBRARIES = False
        return False
    CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
                                ctypes.POINTER(ctypes.c_uint64))

    def signature(library, name, args, result):
        function = getattr(library, name)
        function.argtypes = args
        function.restype = result
        return function

    ref = ctypes.c_void_p
    libs = dict(
        cf=cf, fs=fs, CALLBACK=CALLBACK,
        string_create=signature(cf, 'CFStringCreateWithCString',
                                [ref, ctypes.c_char_p, ctypes.c_uint32], ref),
        array_create=signature(cf, 'CFArrayCreate',
                               [ref, ctypes.POINTER(ref), ctypes.c_long, ref], ref),
        array_count=signature(cf, 'CFArrayGetCount', [ref], ctypes.c_long),
        array_value=signature(cf, 'CFArrayGetValueAtIndex', [ref, ctypes.c_long], ref),
        string_cstring=signature(cf, 'CFStringGetCString',
                                 [ref, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32],
                                 ctypes.c_bool),
        string_max=signature(cf, 'CFStringGetMaximumSizeForEncoding',
                             [ctypes.c_long, ctypes.c_uint32], ctypes.c_long),
        string_length=signature(cf, 'CFStringGetLength', [ref], ctypes.c_long),
        run_loop=signature(cf, 'CFRunLoopGetCurrent', [], ref),
        run_mode=signature(cf, 'CFRunLoopRunInMode',
                           [ref, ctypes.c_double, ctypes.c_bool], ctypes.c_int32),
        release=signature(cf, 'CFRelease', [ref], None),
        current_id=signature(fs, 'FSEventsGetCurrentEventId', [], ctypes.c_uint64),
        stream_create=signature(fs, 'FSEventStreamCreate',
                                [ref, CALLBACK, ref, ref, ctypes.c_uint64, ctypes.c_double,
                                 ctypes.c_uint32], ref),
        stream_schedule=signature(fs, 'FSEventStreamScheduleWithRunLoop',
                                  [ref, ref, ref], None),
        stream_start=signature(fs, 'FSEventStreamStart', [ref], ctypes.c_bool),
        stream_stop=signature(fs, 'FSEventStreamStop', [ref], None),
        stream_invalidate=signature(fs, 'FSEventStreamInvalidate', [ref], None),
        stream_release=signature(fs, 'FSEventStreamRelease', [ref], None),
        stream_flush=signature(fs, 'FSEventStreamFlushSync', [ref], None),
        mode=signature(cf, 'CFStringCreateWithCString',
                       [ref, ctypes.c_char_p, ctypes.c_uint32], ref)(None, b'kCFRunLoopDefaultMode', UTF8),
    )
    _LIBRARIES = libs
    return libs


def _changed_after(path: str, when: float) -> bool:
    """Whether a reported path was modified after ``when``.

    The path itself, or for a deleted path its parent, must have a timestamp at
    or after the cut-off. Anything unreadable is kept: a change we cannot date
    is safer to re-walk than to ignore.
    """
    cutoff = when - 0.05  # tolerate coarse filesystem timestamps
    for candidate in (path, os.path.dirname(path) or path):
        try:
            info = os.stat(candidate, follow_symlinks=False)
        except OSError:
            continue
        if max(info.st_mtime, info.st_ctime) >= cutoff:
            return True
    return False


def _recent(name: str, when: float | None) -> bool:
    """Skip a path whose own entry predates the last completed scan."""
    if when is None:
        return True
    try:
        info = os.stat(name, follow_symlinks=False)
    except OSError:
        # A deleted path cannot be dated; its parent's change is still reported
        # separately, so dropping it is safe only if the parent is fresh.
        parent = os.path.dirname(name)
        if not parent:
            return True
        try:
            info = os.stat(parent, follow_symlinks=False)
        except OSError:
            return True
    return max(info.st_mtime, info.st_ctime) >= when - 0.05


def current_event_id() -> int | None:
    """The journal position right now; record it before a scan starts."""
    libs = _libraries()
    if not libs:
        return None
    try:
        return int(libs['current_id']())
    except (OSError, ValueError):  # pragma: no cover - defensive
        return None


def _decode(libs, ref, fallback_bytes=8192) -> str:
    size = libs['string_max'](libs['string_length'](ref), UTF8) + 1
    buffer = ctypes.create_string_buffer(max(16, min(size, 1 << 20)))
    if libs['string_cstring'](ref, buffer, len(buffer), UTF8):
        return buffer.value.decode('utf-8', 'replace')
    return ''


def replay(root: str, since: int | None, *, timeout: float = 2.0,
           newer_than: float | None = None) -> dict:
    """Return changes under ``root`` recorded after ``since``.

    ``trusted`` is False whenever the journal reported a gap, a dropped batch,
    an unmount or a root rename, or when no stream could be created. Callers
    must then ignore the paths and rescan.

    ``newer_than`` (a wall-clock time) drops events that happened before it.
    The journal position is recorded after a scan, but events for work already
    counted can still be written afterwards; without this, a quiet tree would
    look dirty forever. File timestamps are used because FSEventStream does not
    expose per-event times to this callback.
    """
    result = dict(trusted=False, paths=[], latest=since, events=0, reason='unavailable')
    if since is None:
        result['reason'] = 'no-cursor'
        return result
    libs = _libraries()
    if not libs:
        return result
    try:
        canonical = os.path.realpath(root)
    except OSError:
        result['reason'] = 'root-missing'
        return result
    current = current_event_id()
    if current is None:
        result['reason'] = 'no-journal'
        return result
    with _LOCK:
        collected: list[tuple[str, int]] = []
        state = {'done': False, 'gap': False, 'latest': 0}

        def handler(_stream, _info, count, paths, flags, ids):
            for index in range(count):
                flag = int(flags[index])
                event_id = int(ids[index]) if ids else 0
                if event_id > state['latest']:
                    state['latest'] = event_id
                if flag & UNTRUSTWORTHY:
                    state['gap'] = True
                if flag & FLAG_HISTORY_DONE:
                    state['done'] = True
                reference = libs['array_value'](paths, index)
                name = _decode(libs, reference) if reference else ''
                if name and _recent(name, newer_than):
                    collected.append((name, flag))

        callback = libs['CALLBACK'](handler)
        reference = libs['string_create'](None, canonical.encode('utf-8', 'surrogateescape'), UTF8)
        if not reference:
            return result
        paths = [reference]
        array = libs['array_create'](None, (ctypes.c_void_p * 1)(*paths), 1, None)
        stream = None
        try:
            if not array:
                return result
            # FSEvents may journal several changes under the same event id, and
            # a change made immediately after a scan can reuse the cursor's id.
            # Asking for `since` rather than `since + 1` keeps that event; the
            # duplicate work is one directory re-listing.
            stream = libs['stream_create'](None, callback, None, array, max(0, int(since)),
                                           0.0, STREAM_FLAGS)
            if not stream:
                result['reason'] = 'stream-create-failed'
                return result
            libs['stream_schedule'](stream, libs['run_loop'](), libs['mode'])
            if not libs['stream_start'](stream):
                result['reason'] = 'stream-start-failed'
                return result
            # Stop once the journal has both replayed history and caught up to
            # the current position. A quiet run alone is not enough: macOS can
            # deliver the initial batch before the backlog, and stopping then
            # would report "no changes" for a tree that did change.
            started = time.monotonic()
            deadline = started + timeout
            quiet_since = started
            caught_up = False
            while time.monotonic() < deadline:
                before = len(collected)
                libs['run_mode'](libs['mode'], 0.02, False)
                if state['gap']:
                    break
                now_mono = time.monotonic()
                if len(collected) != before:
                    quiet_since = now_mono
                if state['latest'] >= since:
                    caught_up = True
                    if now_mono - quiet_since > 0.08:
                        break
                elif not caught_up and now_mono - quiet_since > 0.6:
                    # Nothing has arrived for a long time and the journal still
                    # has not reached the recorded position: do not claim it.
                    state['gap'] = True
                    break
        finally:
            if stream:
                libs['stream_stop'](stream)
                libs['stream_invalidate'](stream)
                libs['stream_release'](stream)
            if array:
                libs['release'](array)
            libs['release'](reference)
    result['latest'] = int(state['latest'] or since)
    result['events'] = len(collected)
    result['paths'] = [name for name, _ in collected]
    if state['gap']:
        result['reason'] = 'journal-gap'
        return result
    if state['latest'] and state['latest'] < int(since):
        result['reason'] = 'cursor-ahead-of-journal'
        return result
    result['trusted'] = True
    result['reason'] = 'ok'
    return result
