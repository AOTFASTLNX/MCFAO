"""Share exact .mrpack Mod JARs across imports without trusting local filenames."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import os
from pathlib import Path
import re
import stat
from tempfile import NamedTemporaryFile

import external_storage
from mod_file_policy import is_metadata
from storage_config import cache_path, existing_parent


def is_mod_jar(name):
    return name.startswith('mods/') and name.lower().endswith('.jar') and not is_metadata(name)


def _identity(entry, limit):
    size = entry.get('fileSize')
    if type(size) is not int or not 0 <= size <= limit:
        return None
    hashes = entry['hashes']
    sha1, sha512 = hashes.get('sha1', '').lower(), hashes.get('sha512', '').lower()
    if re.fullmatch('[0-9a-f]{40}', sha1) and re.fullmatch('[0-9a-f]{128}', sha512):
        return size, sha1, sha512
    return None


def _matches(data, expected):
    size, sha1, sha512 = expected
    return (len(data) == size and hashlib.sha512(data).hexdigest() == sha512
            and hashlib.sha1(data).hexdigest() == sha1)


def _read_verified(path, expected):
    def open_regular(path, flags):
        # Do not follow local links or block on a special file swapped into place.
        return os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)

    try:
        with open(path, 'rb', opener=open_regular) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != expected[0]:
                return None
            data = stream.read(expected[0] + 1)
            return data if _matches(data, expected) else None
    except OSError:
        return None


class ModDownloadCache:
    def __init__(self):
        if external_storage.CONFIG.is_file():
            external_storage.require_mount('Mod cache')
        base = cache_path()
        existing_parent(base)
        self.root = base.resolve() / 'mods'
        self.objects = self.root / 'objects'
        self.local_by_size = None

    def _local_files(self):
        if self.local_by_size is None:
            by_size = defaultdict(list)
            try:
                with os.scandir(self.root) as entries:
                    for entry in entries:
                        if is_metadata(entry.name) or not entry.name.lower().endswith('.jar'):
                            continue
                        try:
                            info = entry.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        if stat.S_ISREG(info.st_mode):
                            by_size[info.st_size].append(Path(entry.path))
            except OSError:
                pass
            self.local_by_size = by_size
        return self.local_by_size

    def find(self, entry, limit):
        expected = _identity(entry, limit)
        if expected is None or self.root.is_symlink():
            return None
        size, _, sha512 = expected
        if not self.objects.is_symlink():
            data = _read_verified(self.objects / (sha512 + '.jar'), expected)
            if data is not None:
                return data
        name = Path(entry['path']).name
        for path in sorted(self._local_files().get(size, ()), key=lambda p: (p.name != name, p.name)):
            data = _read_verified(path, expected)
            if data is not None:
                return data
        return None

    def store(self, entry, data, limit):
        expected = _identity(entry, limit)
        if expected is not None and _matches(data, expected):
            self._publish(expected, data)

    def store_file(self, entry, path, limit):
        expected = _identity(entry, limit)
        if expected is not None:
            data = _read_verified(path, expected)
            if data is not None:
                self._publish(expected, data)

    def _publish(self, expected, data):
        if self.root.is_symlink() or self.objects.is_symlink():
            return
        target = self.objects / (expected[2] + '.jar')
        pending = None
        try:
            self.objects.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                return
            with NamedTemporaryFile(dir=self.objects, prefix='.part-', delete=False) as stream:
                pending = Path(stream.name)
                stream.write(data)
            pending.replace(target)
        except OSError:
            # An unavailable cache must not discard an already verified download.
            pass
        finally:
            if pending is not None:
                try:
                    pending.unlink(missing_ok=True)
                except OSError:
                    pass
