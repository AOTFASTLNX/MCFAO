"""One traversal of the storage tree, shared by inventory and cleanup planning.

Design notes
------------
* Directories are visited iteratively with an explicit stack, so an extremely
  deep compiler tree cannot overflow the Python stack.
* Each directory is read exactly once. Nothing is ``stat``-ed that the listing
  did not already describe: ``DirEntry.stat(follow_symlinks=False)`` reuses the
  type bits from ``readdir`` on every platform, and on macOS
  ``getattrlistbulk`` returns name, inode, device, timestamps, link count and
  allocated size for a whole directory in one syscall.
* Files are aggregated inside the listing loop. A file never becomes a Python
  object, which is what makes trees with millions of small files tractable.
* Only regular files contribute bytes (``st_blocks * 512``, the allocated size).
  Symlinks, sockets and devices are counted as entries but never followed.
* A directory that cannot be read is recorded as an error. Its size is reported
  as unknown rather than silently zero.
* Per-directory results carry a fingerprint (inode, device, mtime, ctime) taken
  from the parent listing *before* the descent, so a later scan can reuse an
  unchanged subtree from the persistent index and detect a subtree that changed
  while it was being read.
"""
from __future__ import annotations

import errno
import os
import stat
import sys
import threading
import time
from dataclasses import dataclass, field

try:  # Optional macOS bulk metadata syscall.
    import ctypes
    import ctypes.util
except ImportError:  # pragma: no cover - non-CPython builds
    ctypes = None

ATTR_BIT_MAP_COUNT = 5
ATTR_CMN_RETURNED_ATTRS = 0x80000000
ATTR_CMN_NAME = 0x00000001
ATTR_CMN_DEVID = 0x00000002
ATTR_CMN_OBJTYPE = 0x00000008
ATTR_CMN_MODTIME = 0x00000400
ATTR_CMN_CHGTIME = 0x00000800
ATTR_CMN_FILEID = 0x02000000
ATTR_FILE_LINKCOUNT = 0x00000001
ATTR_FILE_ALLOCSIZE = 0x00000004
BULK_COMMON = (ATTR_CMN_RETURNED_ATTRS | ATTR_CMN_NAME | ATTR_CMN_DEVID
               | ATTR_CMN_OBJTYPE | ATTR_CMN_MODTIME | ATTR_CMN_CHGTIME
               | ATTR_CMN_FILEID)
BULK_FILE = ATTR_FILE_LINKCOUNT | ATTR_FILE_ALLOCSIZE
OBJ_REG, OBJ_DIR, OBJ_LINK = 1, 2, 5
MAX_ERRORS = 8
BULK_BUFFER_BYTES = 256 * 1024
# Bump when the meaning of a stored node changes; older rows are then discarded.
ENGINE_VERSION = 2


if ctypes is not None:
    class _AttrList(ctypes.Structure):
        _fields_ = [
            ('bitmapcount', ctypes.c_ushort),
            ('reserved', ctypes.c_ushort),
            ('commonattr', ctypes.c_uint32),
            ('volattr', ctypes.c_uint32),
            ('dirattr', ctypes.c_uint32),
            ('fileattr', ctypes.c_uint32),
            ('forkattr', ctypes.c_uint32),
        ]
else:  # pragma: no cover
    _AttrList = None


_bulk_function = None
_bulk_checked = False
# One buffer per thread: allocating and zeroing 256 KiB per directory would
# dominate the walk on trees with thousands of small directories.
_buffers = threading.local()


def _bulk_available():
    """Resolve getattrlistbulk once; unavailable platforms simply return None."""
    global _bulk_function, _bulk_checked
    if _bulk_checked:
        return _bulk_function
    _bulk_checked = True
    if ctypes is None or sys.platform != 'darwin':
        return None
    try:
        libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
        function = libc.getattrlistbulk
        function.argtypes = [ctypes.c_int, ctypes.POINTER(_AttrList), ctypes.c_void_p,
                             ctypes.c_size_t, ctypes.c_uint64]
        function.restype = ctypes.c_ssize_t
        _bulk_function = function
    except (OSError, AttributeError):  # pragma: no cover - defensive
        _bulk_function = None
    return _bulk_function


def _bulk_buffer():
    buffer = getattr(_buffers, 'value', None)
    if buffer is None:
        buffer = ctypes.create_string_buffer(BULK_BUFFER_BYTES)
        _buffers.value = buffer
    return buffer


@dataclass(slots=True)
class Subdir:
    """A child directory and the identity its parent listing reported."""
    name: str
    ino: int
    dev: int
    mtime_ns: int
    ctime_ns: int


@dataclass(slots=True)
class Listing:
    """Aggregates for one directory plus the subdirectories still to visit."""
    bytes: int = 0
    files: int = 0
    ipa: int = 0
    multi_links: int = 0
    dirs: list = field(default_factory=list)
    # Only populated for the scanned root, for the "largest items" list.
    top_files: list = field(default_factory=list)
    collect: bool = False

    def add_file(self, name: str, size: int, ino: int, dev: int, nlink: int,
                 seen: set) -> None:
        if nlink > 1:
            self.multi_links += 1
            identity = (dev, ino)
            if identity in seen:
                return
            seen.add(identity)
        self.bytes += size
        self.files += 1
        if name.endswith('.ipa'):
            self.ipa += 1
        if self.collect:
            self.top_files.append((name, size))


def _bulk_entries(path: str, seen: set, collect: bool = False):
    """Read one directory via getattrlistbulk, or None when unsupported."""
    function = _bulk_available()
    if function is None:
        return None
    import struct

    attrs = _AttrList(ATTR_BIT_MAP_COUNT, 0, BULK_COMMON, 0, 0, BULK_FILE, 0)
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_CLOEXEC', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    buffer = _bulk_buffer()
    result = Listing(collect=collect)
    unpack = struct.unpack_from
    try:
        while True:
            count = function(descriptor, ctypes.byref(attrs), buffer, len(buffer), 0)
            if count < 0:
                code = ctypes.get_errno()
                if code in (errno.ENOTSUP, errno.EINVAL, errno.ENOSYS):
                    return None
                raise OSError(code, os.strerror(code), path)
            if count == 0:
                return result
            # One memoryview per syscall batch: buffer.raw would copy the whole
            # 256 KiB buffer for every directory, which dominates the walk.
            raw = memoryview(buffer)
            offset = 0
            for _ in range(count):
                length = unpack('<I', raw, offset)[0]
                common, _vol, _dir, fileattr, _fork = unpack('<IIIII', raw, offset + 4)
                cursor = offset + 24
                name = ''
                if common & ATTR_CMN_NAME:
                    data_offset, name_length = unpack('<iI', raw, cursor)
                    # attr_dataoffset is relative to the attribute reference.
                    start = cursor + data_offset
                    name = str(raw[start:start + max(0, name_length - 1)],
                               'utf-8', 'surrogateescape')
                    cursor += 8
                dev = unpack('<i', raw, cursor)[0]
                object_type = unpack('<I', raw, cursor + 4)[0]
                cursor += 8
                mod_sec, mod_ns = unpack('<qq', raw, cursor)
                cursor += 16
                chg_sec, chg_ns = unpack('<qq', raw, cursor)
                cursor += 16
                ino = unpack('<Q', raw, cursor)[0]
                cursor += 8
                nlink, allocated = 1, 0
                if fileattr & ATTR_FILE_LINKCOUNT:
                    nlink = unpack('<I', raw, cursor)[0]
                    cursor += 4
                if fileattr & ATTR_FILE_ALLOCSIZE:
                    allocated = unpack('<q', raw, cursor)[0]
                if object_type == OBJ_REG:
                    result.add_file(name, allocated, ino, dev, nlink, seen)
                elif object_type == OBJ_DIR:
                    result.dirs.append(Subdir(name, ino, dev,
                                              mod_sec * 1_000_000_000 + mod_ns,
                                              chg_sec * 1_000_000_000 + chg_ns))
                offset += length
    finally:
        os.close(descriptor)


def _scandir_entries(path: str, seen: set, collect: bool = False) -> Listing:
    """Portable fallback: one scandir pass, no follow, no extra stat."""
    result = Listing(collect=collect)
    with os.scandir(path) as iterator:
        for item in iterator:
            try:
                info = item.stat(follow_symlinks=False)
            except OSError:
                continue
            mode = info.st_mode
            if stat.S_ISDIR(mode):
                result.dirs.append(Subdir(item.name, info.st_ino, info.st_dev,
                                          info.st_mtime_ns, info.st_ctime_ns))
            elif stat.S_ISREG(mode):
                result.add_file(item.name, info.st_blocks * 512, info.st_ino,
                                info.st_dev, info.st_nlink, seen)
    return result


def list_directory(path: str, seen: set | None = None, *, bulk: bool = True,
                   collect: bool = False) -> Listing:
    seen = set() if seen is None else seen
    if bulk:
        listing = _bulk_entries(path, seen, collect)
        if listing is not None:
            return listing
    return _scandir_entries(path, seen, collect)


def fingerprint(path: str):
    """Identity of a directory; the fallback when a listing lacks one."""
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    return (info.st_ino, info.st_dev, info.st_mtime_ns, info.st_ctime_ns)


# Stored node layout, in order:
#   ino, dev, mtime_ns, ctime_ns, own_bytes, own_files, own_ipa, multi_links,
#   sub_bytes, sub_files, sub_dirs, sub_ipa, sub_multi, complete
# ``complete`` is 0 when a descendant is missing from this run's index; such a
# subtree must be walked instead of reused.
NODE_FIELDS = 14


@dataclass
class ScanResult:
    root: str
    bytes: int = 0
    files: int = 0
    dirs: int = 0
    ipa: int = 0
    nodes: dict = field(default_factory=dict)
    children: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    error_count: int = 0
    complete: bool = True
    cancelled: bool = False
    reused: int = 0
    walked: int = 0
    bulk: bool = True
    elapsed: float = 0.0
    started: float = 0.0
    # Wall-clock time when the walk began. Anything older is already reflected
    # in these totals, which is what lets a later refresh ignore stale events.
    started_at: float = 0.0

    def warnings(self, limit: int = 5):
        return self.errors[:limit]


class ScanCancelled(RuntimeError):
    pass


class Scanner:
    """Aggregate one storage root, optionally reusing an index of subtrees."""

    def __init__(self, root, *, excluded=None, index=None, progress=None, cancel=None,
                 bulk=True, seen_hardlinks=None, progress_interval=0.15, deadline=None):
        self.root = os.path.abspath(str(root))
        self.excluded = {os.path.abspath(str(p)) for p in (excluded or set())}
        self.index = index or {}
        self.progress = progress
        self.cancel = cancel
        self.bulk = bulk
        self.seen_hardlinks = seen_hardlinks if seen_hardlinks is not None else set()
        self.progress_interval = progress_interval
        self.deadline = deadline
        self.result = ScanResult(root=self.root, bulk=bulk)
        self._last_report = 0.0
        self._phase = 'scanning'
        self._current = self.root

    def _report(self, force=False):
        if self.progress is None:
            return
        now = time.monotonic()
        if not force and now - self._last_report < self.progress_interval:
            return
        self._last_report = now
        self.progress(dict(phase=self._phase, current=self._current,
                           files=self.result.files, dirs=self.result.dirs,
                           bytes=self.result.bytes, walked=self.result.walked,
                           reused=self.result.reused,
                           errors=self.result.error_count))

    def _check(self):
        if self.cancel is not None and self.cancel():
            self.result.cancelled = True
            raise ScanCancelled('扫描已取消')
        if self.deadline is not None and time.monotonic() > self.deadline:
            self.result.cancelled = True
            raise ScanCancelled('扫描超时')

    def _error(self, path, error):
        self.result.complete = False
        self.result.error_count += 1
        if len(self.result.errors) < MAX_ERRORS:
            self.result.errors.append(f'{path}: {error}')

    def _reusable(self, rel, cached, key):
        """A cached directory may be reused only when it is a proven leaf.

        A directory's own mtime/ctime do not change when a file is added to a
        *descendant*, so a parent's identity can never certify its subtree.
        Only a directory with no child directory can be skipped: everything it
        contains is described by its own listing, and that listing is what the
        fingerprint covers.

        Leaves holding multiply linked files are always re-walked, because the
        hard-link de-duplication set has to observe their inodes.
        """
        if cached is None or cached[:4] != key:
            return None
        if len(cached) < 14:
            return None
        # sub_dirs, multi_links (own), sub_multi must all be zero.
        if cached[10] or cached[7] or cached[12]:
            return None
        if not cached[13]:
            return None
        if rel and self.excluded:
            prefix = self.root + '/' + rel + '/'
            if any(path.startswith(prefix) for path in self.excluded):
                return None
        return cached

    def run(self):
        started = time.monotonic()
        self.result.started = started
        self.result.started_at = time.time()
        self._check()
        key = fingerprint(self.root)
        if key is None:
            self._error(self.root, FileNotFoundError(self.root))
            self.result.elapsed = time.monotonic() - started
            return self.result
        nodes = {}
        order = []
        parents = {}
        # Frame: (absolute path, rel, fingerprint, parent rel)
        stack = [(self.root, '', key, None)]
        while stack:
            path, rel, key, parent = stack.pop()
            self._check()
            self._current = path
            cached = self._reusable(rel, self.index.get(rel), key)
            if cached is not None:
                # A reused leaf has no children and no sub-totals, so it needs
                # no expansion and no special handling in the rollup.
                nodes[rel] = tuple(cached)
                order.append(rel)
                parents[rel] = parent
                self.result.reused += 1
                self.result.walked += 1
                continue
            try:
                listing = list_directory(path, self.seen_hardlinks, bulk=self.bulk,
                                         collect=(rel == ''))
            except OSError as error:
                self._error(path, error)
                nodes[rel] = (key[0], key[1], key[2], key[3], 0, 0, 0, 0,
                              0, 0, 0, 0, 0, 0)
                order.append(rel)
                parents[rel] = parent
                continue
            self.result.walked += 1
            nodes[rel] = (key[0], key[1], key[2], key[3], listing.bytes,
                          listing.files, listing.ipa, listing.multi_links,
                          0, 0, 0, 0, 0, 1)
            if rel == '':
                for name, size in listing.top_files:
                    self.result.children[name] = size
            order.append(rel)
            parents[rel] = parent
            for entry in listing.dirs:
                child = path + '/' + entry.name
                if child in self.excluded:
                    continue
                child_key = (entry.ino, entry.dev, entry.mtime_ns, entry.ctime_ns)
                if not entry.ino:
                    child_key = fingerprint(child)
                    if child_key is None:
                        self._error(child, FileNotFoundError(child))
                        continue
                child_rel = (rel + '/' + entry.name) if rel else entry.name
                stack.append((child, child_rel, child_key, rel))
            self._report()
        # Every node starts with zero sub-totals (a reused leaf has none), so a
        # single reverse pass yields exact aggregates.
        for rel in reversed(order):
            parent = parents[rel]
            if parent is None:
                continue
            child = nodes[rel]
            p = nodes[parent]
            nodes[parent] = (p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7],
                             p[8] + child[4] + child[8],
                             p[9] + child[5] + child[9],
                             p[10] + child[10] + 1,
                             p[11] + child[6] + child[11],
                             p[12] + child[7] + child[12],
                             p[13] if len(p) > 13 else 1)
        self.result.nodes = nodes
        top = nodes.get('')
        if top is not None:
            self.result.bytes = top[4] + top[8]
            self.result.files = top[5] + top[9]
            self.result.dirs = top[10]
            self.result.ipa = top[6] + top[11]
        for rel in order:
            if parents.get(rel) == '':
                values = nodes[rel]
                self.result.children[rel] = values[4] + values[8]
        self.result.elapsed = time.monotonic() - started
        self._report(True)
        return self.result


def scan(root, **kwargs):
    return Scanner(root, **kwargs).run()
