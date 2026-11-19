"""Give Native Image a clean Java home when macOS sidecars pollute its module paths."""
from contextlib import contextmanager
from pathlib import Path
import os

from mod_file_policy import copy_content_file, is_metadata, local_build_temp


def metadata_entries(root: Path):
    for folder, dirs, files in os.walk(root, onerror=_raise_walk_error):
        for name in dirs + files:
            if is_metadata(name):
                yield Path(folder) / name
        dirs[:] = [name for name in dirs if not is_metadata(name)]


def _raise_walk_error(error):
    raise error


@contextmanager
def native_image_home(home: Path):
    """Keep normal JDKs in place. Isolate affected JDKs without editing their cache."""
    home = home.resolve(strict=True)
    if not any(path.name != ".DS_Store" for path in metadata_entries(home)):
        yield home
        return
    with local_build_temp("mcfao-native-image-") as scratch:
        staged = scratch / "Home"
        # copytree applies copystat to directories even with a custom copy function.
        # Copy the directory structure ourselves so no resource forks or xattrs follow.
        for folder, dirs, files in os.walk(home, onerror=_raise_walk_error):
            source = Path(folder)
            destination = staged / source.relative_to(home)
            destination.mkdir()
            dirs[:] = [name for name in dirs if not is_metadata(name)]
            for name in [*dirs, *files]:
                if is_metadata(name):
                    continue
                path = source / name
                target = destination / name
                if path.is_symlink():
                    resolved = path.resolve(strict=True)
                    if not resolved.is_relative_to(home) or is_metadata(resolved.relative_to(home)):
                        raise ValueError(f"Cannot stage GraalVM link to a non-content path inside its Java home: {path}")
                    target.symlink_to(os.path.relpath(staged / resolved.relative_to(home), target.parent))
                elif path.is_file():
                    copy_content_file(path, target)
                elif not path.is_dir():
                    raise ValueError(f"Unexpected file in GraalVM Java home: {path}")
            dirs[:] = [name for name in dirs if not (source / name).is_symlink()]
        if unexpected := next(metadata_entries(staged), None):
            raise ValueError(f"Native Image staging created a macOS metadata entry: {unexpected}")
        yield staged
