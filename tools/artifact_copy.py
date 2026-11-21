"""Copy build artifacts without paying for a second physical copy on APFS.

Build staging needs an independent path and inode: Xcode re-signs
``Frameworks/*.dylib`` in place, so a hard link would let one experiment rewrite
another's signature. ``clonefile(2)`` gives us a copy-on-write clone instead:
independent inode, identical bytes, no new blocks until either side is written.
Volumes without clone support (exFAT build disks, network shares) fall back to a
regular copy with the same bytes and permissions.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import shutil
import sys
from pathlib import Path

_LIBC = None


def _clonefile(source: str, destination: str) -> bool:
    """Return True when the kernel produced an APFS clone."""
    global _LIBC
    if sys.platform != "darwin":
        return False
    if _LIBC is None:
        path = ctypes.util.find_library("System") or "/usr/lib/libSystem.B.dylib"
        library = ctypes.CDLL(path, use_errno=True)
        library.clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        library.clonefile.restype = ctypes.c_int
        _LIBC = library
    return _LIBC.clonefile(os.fsencode(source), os.fsencode(destination), 0) == 0


def copy_artifact(source: Path | str, destination: Path | str, *,
                  preserve_metadata: bool = False) -> str:
    """Copy ``source`` to ``destination`` and report ``clone`` or ``copy``.

    ``destination`` may already exist; it is replaced. Callers that rely on a
    fingerprint still verify the result after this returns.
    """
    source_path = Path(source)
    destination_path = Path(destination)
    if not source_path.is_file():
        raise ValueError(f"Not a regular file: {source_path}")
    if source_path.absolute() == destination_path.absolute():
        return "same"
    if destination_path.is_symlink() or destination_path.exists():
        if destination_path.is_dir():
            raise IsADirectoryError(destination_path)
        destination_path.unlink()
    if _clonefile(str(source_path), str(destination_path)):
        if preserve_metadata:
            shutil.copystat(source_path, destination_path)
        return "clone"
    shutil.copyfile(source_path, destination_path)
    if preserve_metadata:
        shutil.copystat(source_path, destination_path)
    return "copy"
