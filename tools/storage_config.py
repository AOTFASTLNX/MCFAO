"""Four independent storage roots. Configuration never moves or deletes data."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
from pathlib import Path
from contextlib import contextmanager
import fcntl

ROOT = Path(__file__).resolve().parents[1]
ROLES = ('cache', 'builds', 'jobs', 'rust')
RESERVE = dict(cache=8 * 1024**3, builds=24 * 1024**3, jobs=4 * 1024**3, rust=4 * 1024**3)


def config_path(root=ROOT):
    if os.environ.get('MCFAO_STORAGE_CONFIG'):
        return Path(os.environ['MCFAO_STORAGE_CONFIG']).expanduser()
    # A distributed source tree is read-only inside the signed application.
    identity = 'bundled' if (root / 'bundle-manifest.json').exists() else hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return Path.home() / 'Library/Application Support/NCL Builder' / identity / 'storage.json'


@contextmanager
def control_lock(root=ROOT):
    path = config_path(root).with_suffix('.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def default_paths(root=ROOT):
    root = Path(root)
    if (root / 'bundle-manifest.json').exists():
        base = Path.home() / 'Library/Application Support/NCL Builder'
        defaults = dict(cache=Path.home() / 'Library/Caches/NCL Builder/compiler',
                        builds=base / 'builds', jobs=base / 'jobs',
                        rust=Path.home() / 'Library/Caches/NCL Builder/rust')
    else:
        defaults = dict(cache=root / '.cache', builds=root / 'artifacts/desktop-builds',
                        jobs=root / 'artifacts/desktop-jobs', rust=root / 'desktop/src-tauri/target')
    return defaults


def storage_paths(root=ROOT):
    root = Path(root)
    defaults = default_paths(root)
    saved = json.loads(config_path(root).read_text()) if config_path(root).is_file() else {}
    for role in ROLES:
        value = os.environ.get('MCFAO_' + role.upper() + '_DIR') or saved.get(role)
        if value:
            path = Path(value).expanduser()
            if not path.is_absolute() or any(c in str(path) for c in '\0\n\r'):
                raise ValueError('Storage directory must be an absolute path: ' + role)
            defaults[role] = path
    return defaults


def cache_path(relative='', root=ROOT):
    return storage_paths(root)['cache'] / relative


def job_roots(root=ROOT):
    path = config_path(root)
    saved = json.loads(path.read_text()) if path.is_file() else {}
    return list(dict.fromkeys([storage_paths(root)['jobs'], *map(Path, saved.get('previousJobRoots', []))]))


def existing_parent(path):
    path = Path(path).absolute()
    # Never turn a disconnected symlink or an absent external volume into a local directory.
    for part in [path, *path.parents]:
        if part.is_symlink() and not part.exists():
            raise ValueError('Disconnected storage link: ' + str(part))
    if path.parts[1:2] == ('Volumes',):
        volume = Path(*path.parts[:3])
        if not os.path.ismount(volume):
            raise ValueError('Storage volume is not mounted: ' + str(volume))
    while not path.exists():
        path = path.parent
    if not path.is_dir():
        raise ValueError('Storage path is not a directory: ' + str(path))
    return path.resolve()


def space_report(paths, required=None):
    required = RESERVE if required is None else required
    volumes = {}
    rows = []
    for role, path in paths.items():
        parent = existing_parent(path)
        device = parent.stat().st_dev
        group = volumes.setdefault(device, dict(free=shutil.disk_usage(parent).free, required=0, roles=[]))
        group['required'] += required.get(role, 0)
        group['roles'].append(role)
        rows.append(dict(role=role, path=str(path), freeBytes=group['free']))
    return dict(paths=rows, volumes=list(volumes.values()),
                ready=all(v['free'] >= v['required'] for v in volumes.values()))


def require_space(paths=None, required=None):
    report = space_report(paths or storage_paths(), required)
    if not report['ready']:
        raise ValueError('Insufficient storage space; choose a disk with more free space: ' + json.dumps(report))
    return report


def validate_paths(values, root=ROOT):
    if set(values) != set(ROLES) or not all(isinstance(v, str) and v.strip() for v in values.values()):
        raise ValueError('Choose all four storage directories')
    paths = {k: Path(v).expanduser() for k, v in values.items()}
    for role, path in paths.items():
        if not path.is_absolute() or any(c in str(path) for c in '\0\n\r'):
            raise ValueError('Storage directory must be absolute: ' + role)
        resolved = path.resolve()
        if resolved == Path.home() or len(resolved.parts) < 3 or resolved == root or any(resolved.is_relative_to(root / p) for p in ('tools', 'compiler', 'ios', 'interop')):
            raise ValueError('Choose a dedicated storage directory: ' + role)
    resolved = [p.resolve() for p in paths.values()]
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a) for i, a in enumerate(resolved) for b in resolved[i+1:]):
        raise ValueError('Storage directories must be separate and must not contain each other')
    report = space_report(paths)
    return paths, report


def save_paths(values, root=ROOT):
    paths, report = validate_paths(values, root)
    previous = job_roots(root)
    target = config_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps({**{k: str(v) for k, v in paths.items()},
                                    'previousJobRoots': list(map(str, previous))}, indent=2) + '\n')
    temporary.replace(target)
    return {**report, 'migration': 'NONE', 'config': str(target)}


def reset_paths(root=ROOT):
    if any(os.environ.get('MCFAO_' + role.upper() + '_DIR') for role in ROLES):
        raise ValueError('环境变量固定了储存位置，请先移除路径覆盖后再重置。')
    values = {role: str(path) for role, path in default_paths(root).items()}
    return {**save_paths(values, root), 'storage': values}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        from external_storage import require_mount
        require_mount('storage preflight')
        require_space()
    print(json.dumps({k: str(v) for k, v in storage_paths().items()}))
