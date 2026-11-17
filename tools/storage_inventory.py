"""Read-only allocated-byte inventory for Builder storage and its backing volumes."""
from __future__ import annotations

import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

from storage_config import existing_parent


def inventory(paths: dict[str, Path]) -> dict:
    """Resolve only explicitly configured roots; never traverse child symlinks.

    Nested roots and hard links are counted once. Disk capacity is reported once
    per filesystem, not once per directory. Unavailable roots stay visible.
    """
    resolved = {}
    resolution_errors = {}
    for role, path in paths.items():
        try:
            resolved[role] = path.resolve()
        except (OSError, RuntimeError) as error:
            resolution_errors[role] = str(error)
    seen_files = set()
    claimed_roots = set()
    volumes = {}
    usage = []
    warnings = []

    for role, path in paths.items():
        errors = []
        row = dict(role=role, path=str(path), bytes=0, items=[], available=True)
        usage.append(row)
        if role in resolution_errors:
            row.update(available=False, error=resolution_errors[role])
            warnings.append(f'{path}: ' + row['error'])
            continue
        try:
            parent = existing_parent(path)
            device = str(parent.stat().st_dev)
            disk = shutil.disk_usage(parent)
            volume = volumes.setdefault(device, dict(id=device, path=str(parent.anchor),
                totalBytes=disk.total, freeBytes=disk.free, roles=[]))
            # Find a useful volume name, including mounted external disks.
            mount = parent
            while mount.parent != mount and mount.parent.stat().st_dev == int(device):
                mount = mount.parent
            volume['path'] = str(mount)
            volume['roles'].append(role)
            row['volumeId'] = device
        except (OSError, ValueError) as error:
            row.update(available=False, error=str(error))
            warnings.append(f'{path}: {error}')
            continue

        root = resolved[role]
        if root in claimed_roots:
            row['error'] = '与另一个存储目录相同，占用已计入该目录。'
            warnings.append(f'{path}: ' + row['error'])
            continue
        claimed_roots.add(root)
        excluded = {other for other in resolved.values() if other != root and other.is_relative_to(root)}

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
                # Only multiply-linked files need inode bookkeeping; ordinary
                # compiler trees can contain millions of unique files.
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
        if errors:
            row['error'] = '部分内容无法读取，占用统计不完整。'
            warnings.extend(f'{path}: {error}' for error in errors)

    for volume in volumes.values():
        volume['managedBytes'] = sum(row['bytes'] for row in usage if row.get('volumeId') == volume['id'])
        volume['otherBytes'] = max(0, volume['totalBytes'] - volume['freeBytes'] - volume['managedBytes'])
    return dict(usage=usage, volumes=list(volumes.values()), warnings=warnings,
                scannedAt=datetime.now(timezone.utc).isoformat(),
                managedBytes=sum(row['bytes'] for row in usage))
