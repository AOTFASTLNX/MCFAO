#!/usr/bin/env python3
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'external-storage.json'


class ExternalStorageUnavailable(RuntimeError):
    pass


def descriptors(CONFIG=None):
    CONFIG = CONFIG or globals()['CONFIG']
    return json.loads(Path(CONFIG).read_text())['directories']


def mount_check(VOLUME=None, DATA=None, CONFIG=None, ROOT=None):
    config = Path(CONFIG or globals()['CONFIG'])
    root = Path(ROOT or globals()['ROOT'])
    if not config.is_file():
        from storage_config import storage_paths, space_report
        report = space_report(storage_paths(root))
        return {'available': True, 'volume': 'configured storage', 'data': str(root), 'links': [], 'space': report}
    settings = json.loads(config.read_text())
    volume = Path(VOLUME or settings['volume'])
    data = Path(DATA or (volume / 'MCFAO-data' if VOLUME else settings.get('data', volume / 'MCFAO-data')))
    if not os.path.ismount(volume):
        return {'available': False, 'reason': 'volume-not-mounted', 'volume': str(volume)}
    if not data.is_dir():
        return {'available': False, 'reason': 'data-directory-missing', 'volume': str(volume), 'data': str(data)}
    missing = []
    for row in descriptors(config):
        external = (data / row['external']).resolve()
        if not external.is_dir():
            missing.append(row['external'])
            continue
        link = root / row['link']
        if not link.is_symlink():
            missing.append(row['link'] + ':not-a-symlink')
        elif link.resolve() != external:
            missing.append(row['link'] + ':wrong-target')
    if missing:
        return {'available': False, 'reason': 'missing-links', 'volume': str(volume), 'missing': missing}
    return {'available': True, 'volume': str(volume), 'data': str(data),
            'links': [row['link'] for row in descriptors(config)]}


def require_mount(action, **kwargs):
    status = mount_check(**kwargs)
    if status['available']:
        return status
    raise ExternalStorageUnavailable(
        f"{action}: PAUSED - external disk {status['volume']} is required for local builds. "
        'Insert/mount the disk, confirm MCFAO-data exists, then retry. '
        f'Status: {json.dumps(status, sort_keys=True)}')


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Check the external build disk.')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    status = mount_check()
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    elif status['available']:
        print(f"OK: {status['data']} is mounted; {len(status['links'])} links resolved")
    else:
        print('PAUSED: external disk is required for local builds')
        print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if status['available'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
