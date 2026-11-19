"""Reviewed storage transitions. Only explicit configured roots are candidates."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from uuid import uuid4

from mod_file_policy import is_metadata
from storage_config import ROLES, RESERVE, existing_parent, save_paths, storage_paths, validate_paths


def manifest(root):
    rows = []
    if not root.exists():
        return rows
    def visit(path):
        for entry in sorted(os.scandir(path), key=lambda e: e.name):
            info = entry.stat(follow_symlinks=False)
            relative = str(Path(entry.path).relative_to(root))
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                raise ValueError('不支持迁移或删除特殊文件：' + entry.path)
            link = os.readlink(entry.path) if entry.is_symlink() else None
            rows.append([relative, info.st_mode, info.st_size, info.st_mtime_ns, link])
            if entry.is_dir(follow_symlinks=False): visit(entry.path)
    visit(root)
    return rows


def review(values, root):
    if any(os.environ.get('MCFAO_' + role.upper() + '_DIR') for role in ROLES):
        raise ValueError('环境变量固定了储存位置，请先移除路径覆盖后再切换目录。')
    paths, report = validate_paths(values, root)
    previous = storage_paths(root)
    old = {role: path.resolve() for role, path in previous.items()}
    new = {role: path.resolve() for role, path in paths.items()}
    # Do not operate across overlapping trees, or erase source/user home roots.
    for role, path in previous.items():
        existing_parent(path)
        resolved = old[role]
        if resolved == Path.home() or resolved.is_mount() or len(resolved.parts) < 3 or root.resolve().is_relative_to(resolved) or any(resolved.is_relative_to(root.resolve() / name) for name in ('tools', 'compiler', 'ios', 'interop', 'desktop/src', 'desktop/src-tauri/src')):
            raise ValueError('原目录包含源码或不是专用储存目录，不能自动处理：' + str(path))
    all_roots = [*old.values(), *new.values()]
    if len(set(all_roots)) != len(all_roots) or any(a.is_relative_to(b) or b.is_relative_to(a) for i, a in enumerate(all_roots) for b in all_roots[i+1:]):
        raise ValueError('新旧储存目录不能相同、重叠或互相包含，请选择另一个目录。')
    records = {role: manifest(path) for role, path in old.items()}
    rows = [dict(role=role, source=str(previous[role]), resolvedSource=str(old[role]), destination=str(paths[role]),
                 count=sum(stat.S_ISREG(r[1]) or stat.S_ISLNK(r[1]) for r in records[role]),
                 bytes=sum(r[2] for r in records[role] if stat.S_ISREG(r[1]))) for role in ROLES]
    token = hashlib.sha256(json.dumps([rows, records], sort_keys=True).encode()).hexdigest()
    return dict(token=token, rows=rows, paths=values, ready=report['ready']), old, new, records


def plan(values, root):
    return review(values, root)[0]


def remap(value, old, new):
    if isinstance(value, dict): return {k: remap(v, old, new) for k, v in value.items()}
    if isinstance(value, list): return [remap(v, old, new) for v in value]
    if isinstance(value, str):
        for role in ROLES:
            prefix = str(old[role])
            if value == prefix or value.startswith(prefix + '/'):
                return str(new[role]) + value[len(prefix):]
    return value


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.digest()


def apply(values, policy, token, root):
    if policy not in ('keep', 'migrate', 'delete'):
        raise ValueError('请选择迁移、删除或保留已有文件')
    if policy == 'keep':
        return dict(save_paths(values, root), policy=policy)
    current, old, new, records = review(values, root)
    if current['token'] != token:
        raise ValueError('已有文件或目录设置已变化，请重新预览后确认。')
    mappings = {str(storage_paths(root)[role]): str(values[role]) for role in ROLES}
    mappings.update({str(old[role]): str(new[role]) for role in ROLES})
    stages = {}
    installed = []
    try:
        if policy == 'migrate':
            required = {}
            for row in current['rows']:
                parent = existing_parent(new[row['role']])
                volume = parent.stat().st_dev
                required.setdefault(volume, [parent, 0])[1] += row['bytes'] + RESERVE[row['role']]
            if any(shutil.disk_usage(parent).free < amount for parent, amount in required.values()):
                raise ValueError('目标磁盘空间不足，无法复制并保留构建所需空间。')
            for role in ROLES:
                target = new[role]
                if target.exists():
                    raise ValueError('迁移目标已存在，请选择空的新目录以免覆盖：' + str(target))
                target.parent.mkdir(parents=True, exist_ok=True)
                stage = target.with_name('.ncl-transfer-' + uuid4().hex)
                stages[role] = stage
                if old[role].exists(): shutil.copytree(old[role], stage, symlinks=True)
                else: stage.mkdir()
                # Verify every copied regular file and every link before switching.
                shape = lambda rows: [(r[0], stat.S_IFMT(r[1]), r[2] if stat.S_ISREG(r[1]) else None, r[4]) for r in rows]
                if shape(manifest(stage)) != shape(records[role]):
                    raise ValueError('迁移副本的目录或文件信息不一致：' + role)
                for row in records[role]:
                    if stat.S_ISREG(row[1]) and digest(old[role] / row[0]) != digest(stage / row[0]):
                        raise ValueError('迁移文件校验失败：' + row[0])
                    if stat.S_ISLNK(row[1]):
                        target = (old[role] / row[0]).resolve()
                        mapped = remap(str(target), old, new)
                        # Relative links inside the same root keep their exact
                        # signed layout. Other links retain their target meaning.
                        if os.path.isabs(row[4]) or not target.is_relative_to(old[role]):
                            link = stage / row[0]
                            link.unlink()
                            link.symlink_to(mapped)
            # Only first-party task/config metadata is remapped. Game files,
            # archives, signed products, logs and input fingerprints stay intact.
            metadata = list(stages['jobs'].glob('*/job.json')) + list((stages['jobs'] / 'configs').glob('*.json'))
            for path in metadata:
                if is_metadata(path.relative_to(stages['jobs'])):
                    continue
                if path.is_symlink() or not path.resolve().is_relative_to(stages['jobs'].resolve()):
                    raise ValueError('任务元数据不能是目录外链接：' + str(path))
                data = json.loads(path.read_text())
                # Include lexical roots as well as canonical external paths.
                def replace(v):
                    if isinstance(v, dict): return {k: replace(x) for k, x in v.items()}
                    if isinstance(v, list): return [replace(x) for x in v]
                    if isinstance(v, str):
                        for source, destination in sorted(mappings.items(), key=lambda pair: -len(pair[0])):
                            if v == source or v.startswith(source + '/'): return destination + v[len(source):]
                    return v
                path.write_text(json.dumps(replace(data), ensure_ascii=False, indent=2) + '\n')
            if any(manifest(old[role]) != records[role] for role in ROLES):
                raise ValueError('迁移期间源文件发生变化，原设置和源文件保留。')
            for role in ROLES:
                if new[role].exists():
                    raise ValueError('迁移期间目标目录已出现，原文件保留：' + str(new[role]))
                stages[role].rename(new[role])
                installed.append(new[role])
        result = save_paths(values, root)
    except BaseException:
        for stage in stages.values():
            if stage.exists(): shutil.rmtree(stage)
        for path in installed:
            if path.exists(): shutil.rmtree(path)
        raise
    # Settings now point to verified destinations. Preserve root links (including
    # personal external-storage mappings), remove only the reviewed root contents.
    errors = []
    for role in ROLES:
        if not old[role].exists(): continue
        if manifest(old[role]) != records[role]:
            errors.append('源目录在确认后发生变化，已保留：' + str(old[role]))
            continue
        for path in old[role].iterdir():
            try:
                if path.is_symlink() or path.is_file(): path.unlink()
                else: shutil.rmtree(path)
            except OSError as error: errors.append(str(error))
    return dict(result, policy=policy, pathMappings=mappings if policy == 'migrate' else {},
                warnings=errors, migration='VERIFIED' if policy == 'migrate' else 'NONE')
