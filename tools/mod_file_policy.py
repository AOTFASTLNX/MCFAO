"""Shared filesystem policy for macOS metadata; never inspect or rewrite Mod bytes."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import sys
import tempfile
from artifact_copy import copy_artifact


def _walk_error(error):
    raise error


def is_metadata(path):
    """Match entire relative paths, including archive members and nested directories."""
    return any(part.startswith('._') or part in ('.DS_Store', '__MACOSX')
               for part in str(path).replace('\\', '/').split('/'))


def content_paths(root):
    """Walk without following links; expose content links for callers to reject."""
    root = Path(root)
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=_walk_error):
        dirs[:] = sorted(name for name in dirs if not is_metadata(name))
        for name in dirs[:]:
            path = Path(folder) / name
            if path.is_symlink():
                dirs.remove(name)
                yield path
        for name in sorted(files):
            if not is_metadata(name):
                yield Path(folder) / name


def mod_candidates(root):
    return sorted(p for p in Path(root).iterdir()
                  if not is_metadata(p.name) and p.suffix.lower() == '.jar')


def copy_ignore(directory, names):
    return [name for name in names if is_metadata(name)]


def copy_content_file(source, destination):
    """Copy bytes and mode only, without Finder metadata or resource forks."""
    copy_artifact(source, destination)
    shutil.copymode(source, destination)
    return destination


@contextmanager
def local_build_temp(prefix):
    # Stage on the host volume even when capture() points TMPDIR into a build
    # directory on external storage.
    with tempfile.TemporaryDirectory(prefix=prefix, dir="/private/tmp" if sys.platform == "darwin" else None) as directory:
        yield Path(directory).resolve(strict=True)


def clean_staged_metadata(root):
    """Remove sidecars only in a caller-owned staging tree, without following links.

    Ordinary files (even under __MACOSX) and symlinks are never deleted. Metadata
    directories are pruned only when empty. Content filtering remains authoritative
    because exFAT/macOS can recreate sidecars after this pass.
    """
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Metadata cleanup requires a regular staging directory')
    removed = []
    for folder, dirs, files in os.walk(root, topdown=False, followlinks=False, onerror=_walk_error):
        for name in files:
            path = Path(folder) / name
            if (name.startswith('._') or name == '.DS_Store') and not path.is_symlink():
                path.unlink()
                removed.append(str(path.relative_to(root)))
        for name in dirs:
            path = Path(folder) / name
            if is_metadata(name) and not path.is_symlink() and not any(path.iterdir()):
                path.rmdir()
                removed.append(str(path.relative_to(root)))
    return sorted(removed)
