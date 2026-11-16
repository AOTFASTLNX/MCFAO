#!/usr/bin/env python3
"""Local GUI build supervisor; fixed argv only, no shell and no device operations."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urljoin, urlsplit
from uuid import uuid4
import zipfile
from preflight import scan_pack, validate_zip_members, read_json_limited, MAX_MANIFEST, resource_unit, tls_context
from mcfao import instance_files
from bootstrap_toolchain import sha256
from mod_file_policy import is_metadata, content_paths, mod_candidates, copy_ignore, clean_staged_metadata
from external_storage import ExternalStorageUnavailable, require_mount
import cleanup_storage
from storage_config import storage_paths, job_roots, require_space, save_paths, space_report, control_lock

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('prepared', 'caps', 'bootstrapRuntime', 'splitter', 'versionMetadata', 'assets',
        'glfw', 'lwjgl', 'gl41', 'openal', 'lwjglOpengl', 'b1Evidence')
ACTIVE = {'queued', 'running', 'cancelling', 'awaiting-exclusions'}
STAGES = ['validate', 'source', 'doctor', 'fabric', 'split', 'gl41-patch', 'aot',
          'runtime', 'link', 'stage', 'package', 'archive', 'export-log', 'verify']
LIMIT = 256 * 1024 ** 2
CANCELLED = False

def now(): return datetime.now(timezone.utc).isoformat()
def read_json(path): return json.loads(Path(path).read_text())
def write_json(path, value):
    path = Path(path)
    pending = path.with_name('.' + path.name + '.' + uuid4().hex)
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)

def resolve(value, base=ROOT):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096 or any(ord(c) in (0, 10, 13) for c in value):
        raise ValueError('请选择有效路径')
    return (base / Path(value).expanduser()).resolve()

def workspace_path(value):
    p = resolve(value)
    if p != ROOT or not (p / 'tools/mcfao.py').is_file():
        raise ValueError('请选择与构建服务对应的 FabricAOT 源码目录')
    return p

def job_path(workspace, ident):
    if not re.fullmatch('[a-f0-9]{32}', ident or ''): raise ValueError('任务编号无效')
    roots = job_roots(workspace)
    return next((p / ident / 'job.json' for p in roots if (p / ident / 'job.json').is_file()), roots[0] / ident / 'job.json')

def tail(path, limit=16000):
    try:
        with Path(path).open('rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - limit))
            return f.read(limit).decode('utf-8', errors='replace')
    except OSError: return ''

def alive(job):
    if not isinstance(job.get('pid'), int): return False
    try:
        result = subprocess.run(['/bin/ps', '-p', str(job['pid']), '-o', 'args='], capture_output=True, text=True, timeout=3)
        return 'desktop_workbench.py' in result.stdout and job['id'] in result.stdout
    except (OSError, subprocess.SubprocessError): return False

def snapshot(path, logs=True):
    job = read_json(path)
    if job['state'] in ACTIVE and not alive(job):
        job.update(state='interrupted', error='任务进程已中断，可恢复已校验的阶段', finishedAt=now())
        write_json(path, job)
    elif job['state'] in ACTIVE and (path.parent / 'cancel').exists():
        job['state'] = 'cancelling'
    if logs:
        files = [p for pattern in ('*stdout.log', '*stderr.log', 'worker.log') for p in path.parent.rglob(pattern)]
        files += list(Path(job["build"]).glob("*/*/command/*.log"))
        files += list(Path(job["build"]).glob("aot/*/product/analysis/*.log"))
        files = sorted((p for p in files if not is_metadata(p) and p.is_file()),
                       key=lambda p: p.stat().st_mtime)[-6:]
        job['log'] = '\n'.join('[' + str(p) + ']\n' + tail(p) for p in files)
        if job['stage'] not in ('archive', 'export-log', 'verify'):
            for line in tail(path.parent / 'build.stdout.log', 64000).splitlines():
                if line.split(':', 1)[0] in STAGES: job['stage'] = line.split(':', 1)[0]
        for line in tail(path.parent / 'export.stdout.log').splitlines():
            stage = line.split(':', 1)[0]
            if stage in ('archive', 'export-log', 'unpack'): job['stage'] = 'verify' if stage == 'unpack' else stage
    return job

def history(workspace):
    paths = sorted((p for root in job_roots(workspace) for p in root.glob('*/job.json')), key=lambda p: p.stat().st_mtime, reverse=True)[:40]
    jobs = []
    for p in paths:
        try: jobs.append(snapshot(p, False))
        except (OSError, ValueError, KeyError): pass
    return jobs

def config_summary(value):
    config = resolve(value)
    data = read_json(config)
    if not isinstance(data, dict) or not set(KEYS) <= data.keys() or data.keys() - set(KEYS) - {'openjdkSource', 'graalSource'}:
        raise ValueError('构建配置字段不完整，请选择 mcfao 配置或补全高级配置')
    paths = {k: resolve(v, config.parent) for k, v in data.items()}
    missing = [k + ': ' + str(v) for k, v in paths.items() if not v.exists()]
    if missing: raise ValueError('构建输入不存在：\n' + '\n'.join(missing))
    return config, paths

def bootstrap(workspace):
    config = next((p for p in (workspace / 'artifacts/integration-20261115/config-gl41.json', workspace / 'artifacts/mcfao-gl41.json', workspace / 'mcfao.local.json') if p.is_file()), None)
    fields = {}
    if config:
        try: fields = read_json(config)
        except (OSError, ValueError): pass
    bundled = (workspace / 'bundle-manifest.json').is_file()
    setup = None
    if bundled:
        from first_run import start as start_setup
        try: setup = start_setup()
        except (OSError, ValueError, RuntimeError) as exc:
            setup = dict(state='failed', message='首次准备暂停，请检查存储位置后重试', error=str(exc))
    return dict(workspace=str(workspace), bundled=bundled, setup=setup, config=str(config) if config else '', configFields=fields,
                exportOptions=str(workspace / 'ios/C0Harness/ExportOptions.plist'),
                output=str(storage_paths(workspace)['builds']), storage={k: str(v) for k, v in storage_paths(workspace).items()}, jobs=history(workspace))

def check(request):
    workspace_path(request['workspace'])
    checks = []
    def add(name, fn):
        try:
            result = fn()
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            checks.append(dict(name=name, status='missing', detail=str(e)))
            return
        if isinstance(result, tuple):
            detail, warning = result
            checks.append(dict(name=name, status='warning' if warning else 'ready', detail=str(detail)))
        else:
            checks.append(dict(name=name, status='ready', detail=str(result)))
    def host():
        if platform.system() != 'Darwin' or platform.machine() != 'arm64':
            raise ValueError('需要 macOS Apple Silicon')
        if sys.version_info < (3, 11):
            return 'Python ' + platform.python_version() + ' 低于 3.11，构建仍会继续，异常时请查看日志', True
        return 'Apple Silicon · Python ' + platform.python_version()
    add('构建主机', host)
    add('Xcode 与 iPhoneOS SDK', lambda: subprocess.check_output(['/usr/bin/xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], text=True, timeout=20).strip())
    def configuration():
        _, paths = config_summary(request['config'])
        java = Path(read_json(paths['prepared'] / 'result.json')['javaHome']) / 'bin/native-image'
        version = subprocess.check_output([str(java), '--version'], text=True, timeout=25)
        first = version.splitlines()[0]
        if 'GraalVM CE 25.0.2' not in version:
            return first + ' 与记录中的 GraalVM CE 25.0.2 不同，构建仍会继续', True
        return '全部前置路径存在 · ' + first
    add('AOT 工具链与游戏资源', configuration)
    def signing():
        from mcfao import resolve_development_team
        team = request.get('team', '').strip()
        if team and not re.fullmatch('[A-Z0-9]{10}', team): raise ValueError('Team ID 应为 10 位大写字母或数字')
        team = team or resolve_development_team()
        if plistlib.loads(resolve(request['exportOptions']).read_bytes()).get('method') != 'debugging':
            raise ValueError('导出配置需要 debugging 开发导出方式')
        identities = subprocess.check_output(['/usr/bin/security', 'find-identity', '-v', '-p', 'codesigning'], text=True, timeout=15)
        if not re.search(r'\b[1-9]\d* valid identities found', identities): raise ValueError('钥匙串中没有有效签名证书，请先在 Xcode 准备开发签名')
        return '开发团队 ' + team + ' · 导出配置有效'
    if request.get('unsigned'):
        checks.append(dict(name='未签名导出', status='warning', detail='跳过签名与 Xcode 导出；未签名 IPA 不能直接装机，需要另行签名。'))
    else:
        add('开发签名', signing)
    add('磁盘剩余空间', lambda: str(require_space({**storage_paths(), 'builds': resolve(request['output'])})))
    return dict(ready=not any(c['status'] == 'missing' for c in checks), checks=checks, checkedAt=now())

def save_config(request):
    workspace = workspace_path(request['workspace'])
    values = request['fields']
    if not isinstance(values, dict) or not set(KEYS) <= values.keys() or values.keys() - set(KEYS) - {'openjdkSource', 'graalSource'}:
        raise ValueError('配置字段不完整')
    values = {k: str(resolve(v)) for k, v in values.items() if v}
    if not set(KEYS) <= values.keys(): raise ValueError('请填写所有必需路径')
    folder = storage_paths(workspace)['jobs'] / 'configs'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid4().hex + '.json')
    write_json(path, values)
    return dict(path=str(path))

def storage(action, request):
    """Plan or apply a cache/artefact cleanup; never touches a running build."""
    from storage_config import config_path
    if config_path().is_file() or (ROOT / 'bundle-manifest.json').is_file() or any(os.environ.get('MCFAO_' + role.upper() + '_DIR') for role in storage_paths()):
        if action != 'storage-plan':
            raise ValueError('自定义存储目录需单独确认逐文件清理计划；当前只提供只读统计')
        paths = storage_paths()
        report = space_report(paths)
        usage = [dict(role=role, path=str(path), bytes=cleanup_storage.tree_bytes(path.resolve())) for role, path in paths.items()]
        return dict(status='STORAGE_PLAN', dataRoot='configured directories', freeBytes=min(row['freeBytes'] for row in report['paths']),
                    reclaimBytes=0, groups=[], activeJobs=[], blocked=True,
                    reason='自定义目录当前只读统计；迁移与清理需另行确认具体文件计划。', usage=usage)
    data_root = cleanup_storage.default_data_root()
    if action == 'storage-plan':
        return cleanup_storage.plan(data_root=data_root,
                                    keep_builds=int(request.get('keepBuilds', 2)))
    groups = request.get('groups')
    if not isinstance(groups, list) or not groups or not all(isinstance(g, str) for g in groups):
        raise ValueError('请选择要清理的内容')
    return cleanup_storage.apply(data_root=data_root, groups=groups,
                                 keep_builds=int(request.get('keepBuilds', 2)))

def source_overrides(report, build_loader, force_compile=False):
    if report['fatal']:
        raise ValueError('来源检查失败：' + '; '.join(f['message'] for f in report['findings'] if f['severity'] == 'error'))
    source_loader = report.get('fabric_loader_version')
    if source_loader == build_loader: return []
    message = f'来源 Fabric Loader {source_loader} → 构建器 {build_loader}'
    # Loader drift is recorded and the build proceeds; the override stays visible in the job.
    return [dict(code='FABRIC_LOADER_OVERRIDE', sourceLoader=source_loader, buildLoader=build_loader, message=message)]

def resource_selection(report, selection):
    if selection is None: return None  # Legacy jobs retain their recorded import policy.
    if not isinstance(selection, dict) or selection.get('source') != report['source'] or selection.get('fingerprint') != report.get('resources_fingerprint'):
        raise ValueError('资源来源已改变，请重新检查来源并确认资源选择')
    included = selection.get('included')
    if not isinstance(included, list) or len(included) > 20000 or any(not isinstance(x, str) for x in included) or len(set(included)) != len(included):
        raise ValueError('资源选择格式无效')
    available = {row['id']: row for row in report.get('resources', [])}
    if any(ident not in available or not available[ident]['selectable'] for ident in included):
        raise ValueError('选择包含不存在或不可导入的资源，请重新检查来源')
    if not any(available[ident]['category'] == 'mods' and available[ident]['path'].lower().endswith('.jar') for ident in included):
        raise ValueError('整合包构建至少保留一个启用的 Mod；不带 Mod 请返回选择原版')
    return set(included)

def validate_request(request):
    workspace = workspace_path(request['workspace'])
    if not isinstance(request.get('unsigned', False), bool): raise ValueError('未签名选项必须为布尔值')
    if not isinstance(request.get('forceCompile', False), bool): raise ValueError('强制编译选项必须为布尔值')
    if request.get('loader') not in ('fabric', 'vanilla'): raise ValueError('请选择 Fabric 或原版')
    if request.get('existingBuild'):
        result = read_json(resolve(request['existingBuild']) / 'result.json')
        expected = 'UNSIGNED_DEVICE_APP' if request.get('unsigned') else 'SIGNED_DEVICE_APP'
        if result.get('status') != expected or result.get('target') != 'ios-arm64':
            raise ValueError('请选择已完成的 iPhoneOS 构建目录')
        if not request.get('unsigned') and plistlib.loads(resolve(request['exportOptions']).read_bytes()).get('method') != 'debugging':
            raise ValueError('请选择 debugging 导出配置')
        if not request.get('unsigned') and request.get('team') and not re.fullmatch('[A-Z0-9]{10}', request['team']):
            raise ValueError('Team ID 无效')
        if result.get('loader') in ('fabric', 'vanilla'):
            request['loader'] = result['loader']
        return workspace
    config_summary(request['config'])
    if not request.get('unsigned'):
        if plistlib.loads(resolve(request['exportOptions']).read_bytes()).get('method') != 'debugging': raise ValueError('请选择 debugging 导出配置')
        if request.get('team') and not re.fullmatch('[A-Z0-9]{10}', request['team']): raise ValueError('Team ID 无效')
    output = resolve(request['output'])
    if output == workspace or output in workspace.parents or any(output.is_relative_to(workspace / p) for p in ('tools', 'ios', 'compiler')):
        raise ValueError('请选择专用的构建产物目录')
    if request['loader'] == 'fabric':
        report = scan_pack(resolve(request.get('source', '')))
        loader = read_json(workspace / 'compiler/fabric.lock.json')['fabricLoader']
        source_overrides(report, loader, request.get('forceCompile', False))
        resource_selection(report, request.get('resourceSelection'))
        if request.get('audited') is not True: raise ValueError('请先审计 Mod 并确认允许隔离构建期转换')
    return workspace

DOWNLOAD_HOST = 'cdn.modrinth.com'

def download_opener():
    return urllib.request.build_opener(DownloadRedirect(), urllib.request.HTTPSHandler(context=tls_context()))

def download_url(value):
    parts = urlsplit(value)
    if parts.scheme != 'https' or parts.hostname != DOWNLOAD_HOST or parts.port not in (None, 443) or parts.username or parts.password or parts.fragment:
        raise ValueError('自动下载仅允许 HTTPS cdn.modrinth.com；其他来源请先导入完整 Prism 实例')
    return value

class DownloadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, download_url(urljoin(req.full_url, newurl)))

def download(entry, target):
    # urllib uses the macOS system proxy and the standard *_proxy environment variables.
    # The fixed CDN host plus TLS certificate/hostname verification decide trust; a proxy's
    # fake-IP or loopback DNS answer is not treated as an attack, because the name is pinned.
    opener = download_opener()
    last = None
    for url in entry['downloads']:
        try:
            url = download_url(url)
            expected = entry['fileSize']
            if not isinstance(expected, int) or not 0 <= expected <= LIMIT: raise ValueError('单个下载超过 256 MiB')
            request = urllib.request.Request(url, headers={'User-Agent': 'FabricAOT-local-builder/0.2'})
            with opener.open(request, timeout=25) as response:
                if response.status != 200: raise ValueError(f'下载失败 HTTP {response.status}')
                data = response.read(expected + 1)
            if len(data) != expected: raise ValueError('下载大小与清单不符')
            for algo, digest in entry['hashes'].items():
                if algo in ('sha1', 'sha512') and hashlib.new(algo, data).hexdigest() != digest: raise ValueError('下载哈希校验失败')
            target.write_bytes(data)
            return
        except (OSError, ValueError, http.client.HTTPException) as e: last = e
    raise ValueError(str(last or '没有下载地址'))

def stage_source(source, destination, progress=lambda _: None, cancelled=lambda: False, *, force_compile=False, selection=None):
    report = scan_pack(source)
    loader = read_json(ROOT / 'compiler/fabric.lock.json')['fabricLoader']
    overrides = source_overrides(report, loader, force_compile)
    included = resource_selection(report, selection)
    def keep(name, origin):
        if is_metadata(name): return False
        if included is None: return True
        ident = origin + ':' + resource_unit(name)
        if ident in included: return True
        progress('按资源选择排除：' + name)
        return False
    for override in overrides: progress('版本提示：' + override['message'])
    destination.mkdir()
    game = destination / '.minecraft'
    game.mkdir()
    allowed = {'mods', 'config', 'defaultconfigs', 'resourcepacks', 'shaderpacks', 'kubejs', 'scripts'}
    total = 0
    seen = {}
    def target_for(name, layer):
        if name != 'options.txt' and name.split('/')[0] not in allowed: raise ValueError('暂不支持整合包必要路径：' + name)
        key = name.casefold()
        if key in seen and (seen[key][0] != name or seen[key][1] >= layer): raise ValueError('整合包路径冲突：' + name)
        seen[key] = (name, layer)
        result = game / name
        result.parent.mkdir(parents=True, exist_ok=True)
        return result
    def budget(size):
        nonlocal total
        if cancelled(): raise InterruptedError('构建已取消')
        total += size
        if size > LIMIT or total > 4 * 1024 ** 3: raise ValueError('整合包超过大小限制')
    if source.is_dir():
        base = next((p for p in (source / '.minecraft', source / 'minecraft', source) if (p / 'mods').is_dir()), None)
        if base is None: raise ValueError('实例中没有 Mod 目录')
        for name in allowed:
            folder = base / name
            if folder.is_symlink(): raise ValueError('拒绝复制链接目录')
            if folder.is_dir():
                for p in sorted(content_paths(folder)):
                    if p.is_symlink() or not p.resolve().is_relative_to(source.resolve()): raise ValueError('实例中包含不安全链接')
                    if p.is_file():
                        if not keep(str(p.relative_to(base)), 'local'): continue
                        budget(p.stat().st_size)
                        shutil.copyfile(p, target_for(str(p.relative_to(base)), 0))
        options = base / 'options.txt'
        if selection is not None and options.is_file() and keep('options.txt', 'local'):
            if options.is_symlink(): raise ValueError('拒绝复制链接文件')
            budget(options.stat().st_size)
            shutil.copyfile(options, target_for('options.txt', 0))
    else:
        with zipfile.ZipFile(source) as archive:
            if not validate_zip_members(archive, [], str(source)): raise ValueError('归档路径检查失败')
            manifest = read_json_limited(archive, 'modrinth.index.json', MAX_MANIFEST)
            for entry in manifest['files']:
                side = entry.get('env', {}).get('client')
                if side == 'unsupported' or (included is None and side == 'optional'):
                    progress('跳过服务端或可选文件：' + entry['path'])
                    continue
                if not keep(entry['path'], 'manifest'): continue
                budget(entry['fileSize'])
                progress('下载并校验：' + entry['path'])
                download(entry, target_for(entry['path'], 0))
            for layer, prefix in enumerate(('overrides/', 'client-overrides/'), 1):
                for item in archive.infolist():
                    if item.is_dir() or is_metadata(item.filename) or not item.filename.startswith(prefix): continue
                    if not keep(item.filename[len(prefix):], prefix.rstrip('/')): continue
                    budget(item.file_size)
                    target = target_for(item.filename[len(prefix):], layer)
                    with archive.open(item) as src, target.open('wb') as dst: shutil.copyfileobj(src, dst, 1024 * 1024)
    clean_staged_metadata(game)
    mods = game / 'mods'
    if not mods.is_dir() or not mod_candidates(mods): raise ValueError('没有 Fabric Mod JAR；无 Mod 时请选择原版')
    if len(mod_candidates(mods)) > 128: raise ValueError('当前构建器最多支持 128 个根 Mod JAR')
    write_json(destination / 'mmc-pack.json', {'components': [{'uid': 'net.minecraft', 'version': '26.1.2'}, {'uid': 'net.fabricmc.fabric-loader', 'version': loader}]})
    staged = scan_pack(destination)
    if staged['fatal']: raise ValueError('下载或复制后的 Mod 检查未通过：' + '; '.join(f['message'] for f in staged['findings'] if f['severity'] == 'error'))
    hashes = {}
    for p in content_paths(game):
        if p.is_file():
            with p.open('rb') as f: hashes[str(p.relative_to(game))] = hashlib.file_digest(f, 'sha256').hexdigest()
    write_json(game / 'import.json', dict(status='INSTANCE_FILES_IMPORTED', root=str(game.resolve()), mods=str(mods.resolve()), files={name: dict(sha256=digest, bytes=(game / name).stat().st_size) for name, digest in hashes.items()}, source=str(source), resourceSelection=selection, compatibilityOverrides=overrides))
    with (game / 'import.json').open('rb') as f: hashes['import.json'] = hashlib.file_digest(f, 'sha256').hexdigest()
    write_json(destination / 'source.json', dict(source=str(source), filesSHA256=hashes, report=staged, sourceReport=report, resourceSelection=selection, compatibilityOverrides=overrides))
    return mods, game

def static_exclusion_plan(facts, source_folder):
    """Map unsupported Fabric IDs to the root Mod JARs that must be removed."""
    excluded = facts.get('excludedMods') or {}
    if not isinstance(excluded, dict) or not excluded:
        raise ValueError('AOT 报告没有可确认的静态排除项')
    mods = facts.get('mods') or []
    by_id = {}
    for row in mods:
        if isinstance(row, dict) and isinstance(row.get('id'), str):
            by_id.setdefault(row['id'], []).append(row)
    root_rows = [row for row in mods if isinstance(row, dict) and isinstance(row.get('path'), str) and '!' not in row['path']]
    inventory = read_json(Path(source_folder) / 'source.json').get('report', {}).get('mod_inventory', [])
    metadata_by_id = {row.get('mod', {}).get('id'): row.get('mod', {}) for row in inventory if isinstance(row, dict) and isinstance(row.get('mod'), dict)}
    removed = {}
    removed_ids = set()
    def include_jar_ids(root_path):
        for item in mods:
            item_path = item.get('path') if isinstance(item, dict) else None
            if isinstance(item_path, str) and (item_path == root_path or item_path.startswith(root_path + '!')):
                removed_ids.add(item['id'])
    for mod_id, reasons in excluded.items():
        removed_ids.add(mod_id)
        matches = by_id.get(mod_id, [])
        if not matches:
            raise ValueError(f'AOT 排除项无法映射到整合包 Mod：{mod_id}')
        for row in matches:
            owner_path = row['path'].split('!', 1)[0]
            owners = [item for item in root_rows if item['path'] == owner_path]
            if not owners:
                raise ValueError(f'无法定位受限依赖所属的根 Mod：{row["path"]}')
            for owner in owners:
                owner_id = owner['id']
                entry = removed.setdefault(owner['path'], {'path': owner['path'], 'ids': set(), 'reasons': []})
                entry['ids'].add(owner_id)
                entry['reasons'].extend(reasons if isinstance(reasons, list) else [str(reasons)])
                if row['path'] != owner_path:
                    entry['reasons'].append(f'内嵌依赖 {mod_id} 不受支持：{row["path"]}')
                include_jar_ids(owner_path)
    changed = True
    while changed:
        changed = False
        for row in root_rows:
            mod_id = row['id']
            if mod_id in removed_ids:
                continue
            metadata = metadata_by_id.get(mod_id, {})
            dependencies = metadata.get('declared_depends') or {}
            required = sorted(set(dependencies) & removed_ids) if isinstance(dependencies, dict) else []
            if required:
                removed_ids.add(mod_id)
                entry = removed.setdefault(row['path'], {'path': row['path'], 'ids': set(), 'reasons': []})
                entry['ids'].add(mod_id)
                entry['reasons'].append('依赖将被排除的 Mod：' + ', '.join(required))
                include_jar_ids(row['path'])
                changed = True
    for row in root_rows:
        if row['id'] not in removed_ids:
            continue
        entry = removed.setdefault(row['path'], {'path': row['path'], 'ids': set(), 'reasons': []})
        entry['ids'].add(row['id'])
    staged_game = Path(source_folder) / '.minecraft'
    visible = []
    filenames = set()
    for entry in removed.values():
        filename = Path(entry['path']).name
        if not filename.endswith('.jar') or Path(filename).name != filename:
            raise ValueError(f'不安全的 Mod 文件路径：{entry["path"]}')
        if not (staged_game / 'mods' / filename).is_file():
            raise ValueError(f'受限 Mod 文件不在已校验的暂存目录中：{filename}')
        filenames.add(filename)
        metadata = next((metadata_by_id.get(mod_id) for mod_id in sorted(entry['ids']) if metadata_by_id.get(mod_id)), {})
        visible.append({'modIds': sorted(entry['ids']), 'name': metadata.get('name') or ', '.join(sorted(entry['ids'])),
                        'version': metadata.get('version', ''), 'file': filename,
                        'reasons': list(dict.fromkeys(entry['reasons']))})
    remaining = [path for path in mod_candidates(staged_game / 'mods') if path.name not in filenames]
    if not remaining:
        raise ValueError('排除这些项目后没有剩余 Mod，无法继续 Fabric 构建')
    return {'mods': sorted(visible, key=lambda row: row['file'].casefold()),
            'modFiles': sorted(filenames), 'excludedIds': sorted(removed_ids)}

def filtered_source_copy(source_folder, destination, plan):
    """Create a fresh, integrity-described instance copy without excluded root Mod JARs."""
    source_folder, destination = Path(source_folder), Path(destination)
    game = source_folder / '.minecraft'
    if not (game / 'import.json').is_file() or destination.exists():
        raise ValueError('无法创建静态排除后的暂存副本')
    for path in content_paths(source_folder):
        if path.is_symlink():
            raise ValueError('暂存来源包含链接，拒绝复制')
    shutil.copytree(source_folder, destination, ignore=copy_ignore)
    copied_game = destination / '.minecraft'
    clean_staged_metadata(copied_game)
    removed_files = set(plan['modFiles'])
    for filename in removed_files:
        target = copied_game / 'mods' / filename
        if not target.is_file() or target.is_symlink():
            raise ValueError(f'排除目标已改变：{filename}')
        target.unlink()
    manifest_path = copied_game / 'import.json'
    manifest = read_json(manifest_path)
    manifest['mods'] = str((copied_game / 'mods').resolve())
    manifest['files'] = {name: facts for name, facts in manifest['files'].items()
                         if not is_metadata(name) and not (name.startswith('mods/') and Path(name).name in removed_files)}
    manifest['staticAotExclusions'] = plan['mods']
    write_json(manifest_path, manifest)
    record_path = destination / 'source.json'
    record = read_json(record_path)
    record['filesSHA256'] = instance_files(copied_game)
    record['staticAotExclusions'] = plan['mods']
    record['report'] = scan_pack(destination)
    write_json(record_path, record)
    # Verify the rewritten first-party manifest before exposing this copy to the compiler.
    instance_files(copied_game)
    if not record['report'] or record['report'].get('fatal'):
        raise ValueError('排除后的暂存 Mod 清单未通过安全检查')
    return destination

def fabric_exclusion_report(build, source_folder):
    checkpoint_path = Path(build) / 'fabric/checkpoint.json'
    if not checkpoint_path.is_file():
        raise ValueError('构建失败时未找到 Fabric 转换报告')
    checkpoint = read_json(checkpoint_path)
    attempt = checkpoint.get('attempt', '')
    if not re.fullmatch('[a-f0-9]{32}', attempt):
        raise ValueError('Fabric 转换检查点无效')
    product = checkpoint_path.parent / attempt / 'product'
    report_path = product / 'result.json'
    facts = read_json(report_path)
    if facts.get('status') != 'FABRIC_AOT_INPUT_PREPARED' or not facts.get('excludedMods'):
        raise ValueError('失败原因不是可确认的静态 AOT 排除项')
    mods = Path(source_folder) / '.minecraft/mods'
    current = {str(path.resolve()): sha256(path) for path in mod_candidates(mods)}
    if facts.get('modSHA256') != current:
        raise ValueError('Fabric 排除报告与当前暂存 Mod 不匹配')
    return facts

def await_exclusion_decision(path, challenge_id):
    decision_path = path.parent / 'exclusion-decision.json'
    while True:
        if CANCELLED or (path.parent / 'cancel').exists():
            raise InterruptedError('构建已取消')
        if decision_path.is_file():
            decision = read_json(decision_path)
            if decision.get('challengeId') != challenge_id:
                raise ValueError('排除确认与当前构建提示不匹配')
            decision_path.unlink()
            return decision.get('accepted') is True
        time.sleep(.2)

def resolve_exclusions(workspace, ident, payload):
    path = job_path(workspace, ident)
    job = read_json(path)
    challenge = job.get('exclusionChallenge') or {}
    if job.get('state') != 'awaiting-exclusions' or payload.get('challengeId') != challenge.get('id'):
        raise ValueError('此构建当前没有等待该项排除确认')
    if not isinstance(payload.get('accepted'), bool):
        raise ValueError('排除确认必须是明确选择')
    decision_path = path.parent / 'exclusion-decision.json'
    if decision_path.exists():
        raise ValueError('排除确认已提交')
    write_json(decision_path, {'challengeId': challenge['id'], 'accepted': payload['accepted'], 'respondedAt': now()})
    return snapshot(path, False)

def descendants(pid):
    result = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid='], capture_output=True, text=True, timeout=5)
    pairs = [tuple(map(int, line.split())) for line in result.stdout.splitlines() if len(line.split()) == 2]
    found = {pid}
    while True:
        extra = {p for p, parent in pairs if parent in found}
        if extra <= found: return found - {pid}
        found |= extra

def aot_heap_gib(physical_bytes=None):
    """Pick the Native Image heap that fits this host.

    probe_client_graph.py refuses anything above half of physical memory, so the
    ceiling is the only safe upper bound. The compiler needs the ceiling here:
    a modpack that registers more reachable state than a 7 GiB heap can hold dies
    with OutOfMemoryError during analysis, which costs a full rebuild to discover.
    """
    if physical_bytes is None:
        try: physical_bytes = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
        except (ValueError, OSError, AttributeError): return 7
    gib = physical_bytes / 1024 ** 3
    for choice in (9, 8, 7, 6):
        if choice <= gib / 2: return choice
    return 6


def compile_build(command, folder, request, build, mods, game, update, env, previous=None):
    """Run the compiler, moving to a fresh directory when a reused one is stale.

    A retry keeps the previous build directory so already verified stages stay
    cached. The compiler writes its input fingerprint once, so a directory whose
    inputs changed can never be reused; report the failure with that directory
    preserved and let the caller decide what to do next.
    """
    build = Path(build)
    previous = list(previous or [])
    for _ in range(3):
        args = [*command, 'build', '--version', '26.1.2', '--loader', request['loader'], '--renderer', 'gl41',
                '--heap-gib', str(aot_heap_gib()), '--parallelism', '3', '--target', 'ios-arm64',
                '--config', resolve(request['config']), '--output', build]
        if request['loader'] == 'fabric':
            args += ['--mods', mods, '--audited-mods', '--instance-data', game]
        if request.get('unsigned'):
            args += ['--unsigned']
        try:
            execute(args, folder, 'build', update, 'fabric' if request['loader'] == 'fabric' else 'split', env)
            return None, build
        except ValueError as error:
            if 'Build inputs changed' not in str(error):
                return error, build
            previous.append(dict(path=str(build), reason='输入指纹已变化，改用新的构建目录'))
            build = resolve(request['output']) / f'build-{uuid4().hex[:12]}'
            update(build=str(build), previousBuilds=previous)
    raise ValueError('输入指纹在重试期间反复变化，请重新发起构建')

def execute(argv, folder, name, update, stage, env):
    if CANCELLED or (folder / 'cancel').exists(): raise InterruptedError('构建已取消')
    update(stage=stage)
    # A job keeps appending across retries and exclusion rounds, so a previous
    # failure stays in these logs. Remember where this attempt starts and only
    # report text written by it; otherwise an earlier "excluded Mods" message
    # masks the real cause of a later AOT failure.
    stderr_path = folder / (name + '.stderr.log')
    stdout_path = folder / (name + '.stdout.log')
    started_at = stderr_path.stat().st_size if stderr_path.exists() else 0
    started_out = stdout_path.stat().st_size if stdout_path.exists() else 0
    with stdout_path.open('ab', buffering=0) as out, stderr_path.open('ab', buffering=0) as err:
        child = subprocess.Popen(list(map(str, argv)), cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        started = time.monotonic()
        while child.poll() is None:
            if CANCELLED or (folder / 'cancel').exists() or time.monotonic() - started > 4 * 3600:
                victims = descendants(os.getpid())
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    for pid in sorted(victims, reverse=True):
                        try: os.kill(pid, sig)
                        except ProcessLookupError: pass
                    if sig == signal.SIGTERM: time.sleep(1)
                child.wait()
                raise InterruptedError('构建已取消' if CANCELLED or (folder / 'cancel').exists() else '构建超过 4 小时上限')
            time.sleep(.2)
    if CANCELLED or (folder / 'cancel').exists(): raise InterruptedError('构建已取消')
    if child.returncode:
        reason = attempt_output(stderr_path, started_at, 5000) or attempt_output(stdout_path, started_out, 5000)
        raise ValueError(f'{name} 失败（退出码 {child.returncode}）\n' + reason)

def attempt_output(path, offset, limit):
    """Return only the text this attempt appended, capped to the last `limit` bytes."""
    try:
        with Path(path).open('rb') as f:
            f.seek(0, 2)
            end = f.tell()
            f.seek(max(offset, end - limit))
            return f.read().decode('utf-8', errors='replace')
    except OSError: return ''

def verify_unsigned_build(build):
    """Revalidate AOT evidence, app and each IPA member without signing/exportArchive."""
    from mcfao import verify
    build = Path(build).resolve(strict=True)
    result = read_json(build / 'result.json')
    if result.get('status') != 'UNSIGNED_DEVICE_APP' or result.get('signature') != 'UNSIGNED':
        raise ValueError('Expected a completed unsigned build')
    ipa = Path(result['ipa'])
    if ipa.is_symlink() or not ipa.resolve(strict=True).is_relative_to(build):
        raise ValueError('IPA is outside the build directory')
    verify(build, None)
    expected = {'Payload/' + Path(result['app']).name + '/' + name: digest
                for name, digest in result['appFilesSHA256'].items()}
    with zipfile.ZipFile(ipa) as archive:
        findings = []
        if not validate_zip_members(archive, findings, 'unsigned IPA'):
            raise ValueError('Unsafe unsigned IPA archive: ' + str(findings))
        actual = {}
        for member in archive.infolist():
            if member.is_dir(): continue
            with archive.open(member) as stream:
                actual[member.filename] = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected or archive.testzip() is not None:
            raise ValueError('Unsigned IPA content differs from the verified app')
    return result

def run_job(path):
    def stop(_sig, _frame):
        global CANCELLED
        CANCELLED = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    deadline = time.monotonic() + 10
    while not (path.parent / 'launch').exists():
        if time.monotonic() > deadline: return
        time.sleep(.02)
    job = read_json(path)
    folder = path.parent
    def update(**values):
        job.update(values, updatedAt=now())
        write_json(path, job)
    try:
        request = job['request']
        update(state='running', pid=os.getpid(), stage='validate')
        validate_request(request)
        if job.get('compatibilityOverrides'):
            for override in job['compatibilityOverrides']: print('版本提示：' + override['message'], flush=True)
        if CANCELLED or (folder / 'cancel').exists(): raise InterruptedError('构建已取消')
        checked = check(request) if not request.get('existingBuild') else {'ready': True, 'checks': []}
        write_json(folder / 'checks.json', checked)
        if not checked['ready']: raise ValueError('构建检查未通过：\n' + '\n'.join(c['name'] + '：' + c['detail'] for c in checked['checks'] if c['status'] == 'missing'))
        env = dict(os.environ, PYTHONUNBUFFERED='1')
        for key in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'CLASSPATH'): env.pop(key, None)
        if request.get('team') and not request.get('unsigned'): env['MCFAO_DEVELOPMENT_TEAM'] = request['team']
        for role, directory in storage_paths().items(): env['MCFAO_' + role.upper() + '_DIR'] = str(directory)
        env['CARGO_TARGET_DIR'] = str(storage_paths()['rust'])
        command = [sys.executable, '-B', ROOT / 'tools/mcfao.py']
        build = Path(job['build'])
        if not (build / 'result.json').exists():
            mods = game = None
            if request['loader'] == 'fabric':
                update(stage='source')
                source = Path(job.get('sourceFolder', str(folder / 'source')))
                if source.exists() and not (source / 'source.json').is_file():
                    source = folder / ('source-' + uuid4().hex[:8])
                if source.exists():
                    record = read_json(source / 'source.json')
                    if record.get('resourceSelection') != request.get('resourceSelection'):
                        raise ValueError('暂存内容的资源选择与任务不一致，请新建构建')
                    game = source / '.minecraft'
                    removed = clean_staged_metadata(game)
                    if removed: print(f'已清理 {len(removed)} 个 macOS 元数据项', flush=True)
                    actual = instance_files(game)
                    expected = {name: digest for name, digest in record['filesSHA256'].items() if not is_metadata(name)}
                    if actual != expected: raise ValueError('暂存内容发生变化，请新建构建')
                    mods = game / 'mods'
                else: mods, game = stage_source(resolve(request['source']), source, lambda s: print(s, flush=True), lambda: CANCELLED or (folder / 'cancel').exists(), force_compile=request.get('forceCompile', False), selection=request.get('resourceSelection'))
                update(compatibilityOverrides=read_json(source / 'source.json').get('compatibilityOverrides', []))
                update(sourceFolder=str(source))
            execute([*command, 'doctor', '--renderer', 'gl41', '--config', resolve(request['config'])], folder, 'doctor', update, 'doctor', env)
            for exclusion_round in range(5):
                build = Path(job['build'])
                error, build = compile_build(command, folder, request, build, mods, game, update, env,
                                             job.get('previousBuilds'))
                if error is None:
                    break
                elif 'Requested Fabric instance contains excluded Mods' not in str(error) or request['loader'] != 'fabric':
                    raise error
                else:
                    if exclusion_round == 4:
                        raise ValueError('静态排除后仍发现新的不支持项，已达到确认次数上限；请先调整整合包') from error
                    facts = fabric_exclusion_report(build, source)
                    plan = static_exclusion_plan(facts, source)
                    challenge_id = uuid4().hex
                    challenge = dict(id=challenge_id, mods=plan['mods'], excludedIds=plan['excludedIds'],
                                     summary=f'将从本次构建副本中排除 {len(plan["mods"])} 个 Mod 文件，原整合包不会被修改。')
                    decision_path = folder / 'exclusion-decision.json'
                    decision_path.unlink(missing_ok=True)
                    update(state='awaiting-exclusions', stage='mod-exclusion-review',
                           exclusionChallenge=challenge, exclusionRound=exclusion_round + 1)
                    if not await_exclusion_decision(path, challenge_id):
                        raise InterruptedError('用户取消排除；本次构建已停止，诊断报告已保留')
                    accepted = list(job.get('acceptedExclusions', [])) + [challenge]
                    update(state='running', stage='source', exclusionChallenge=None,
                           acceptedExclusions=accepted, message='已确认排除，正在生成独立暂存副本')
                    filtered = folder / f'source-excluded-{challenge_id[:8]}'
                    filtered_source_copy(source, filtered, plan)
                    previous = list(job.get('previousBuilds', []))
                    previous.append(dict(path=str(build), reason='首次静态 AOT 排除检查'))
                    build = resolve(request['output']) / f'build-{job["id"][:12]}-subset-{challenge_id[:8]}'
                    update(build=str(build), sourceFolder=str(filtered), previousBuilds=previous)
                    source = filtered
                    mods, game = source / '.minecraft/mods', source / '.minecraft'
            else:
                raise ValueError('静态排除后没有可继续的构建输入')
        elif not request.get('unsigned'): execute([*command, 'verify', '--target', 'ios-arm64', '--output', build], folder, 'reverify', update, 'verify', env)
        if request.get('unsigned'):
            result = verify_unsigned_build(build)
            update(state='succeeded', stage='verify', ipa=result['ipa'], sha256=result['sha256'], bytes=result['bytes'],
                   signature='UNSIGNED', warning='未签名 IPA 不能直接装机，需要另行签名。', finishedAt=now())
            return
        export = folder / ('ipa-' + uuid4().hex[:8])
        update(export=str(export))
        execute([*command, 'export', '--target', 'ios-arm64', '--build', build, '--export-options', resolve(request['exportOptions']), '--output', export], folder, 'export', update, 'archive', env)
        result = read_json(export / 'result.json')
        ipa = Path(result['ipa']).resolve(strict=True)
        with ipa.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
        if result['status'] != 'DEVELOPMENT_IPA_VERIFIED' or not ipa.is_relative_to(export.resolve()) or digest != result['sha256']: raise ValueError('IPA 完整性验证失败')
        update(state='succeeded', stage='verify', ipa=str(ipa), sha256=digest, bytes=result['bytes'], finishedAt=now())
    except InterruptedError as e: update(state='cancelled', error=str(e), finishedAt=now())
    except Exception as e: update(state='failed', error=str(e), finishedAt=now())

def start(request, retry=None):
    with control_lock(workspace_path(request.get('workspace', str(ROOT)))):
        return _start(request, retry)

def _start(request, retry=None):
    workspace = validate_request(request)
    require_mount('desktop build')
    require_space({**storage_paths(workspace), 'builds': resolve(request['output'])})
    root = storage_paths(workspace)['jobs']
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if any(j['state'] in ACTIVE for j in history(workspace)): raise ValueError('已有构建在运行，请等待完成或先取消')
        ident = uuid4().hex
        folder = root / ident
        folder.mkdir()
        job = dict(id=ident, name=('Fabric' if request['loader'] == 'fabric' else '原版') + ' · 26.1.2', request=request,
                   state='queued', stage='validate', startedAt=now(), updatedAt=now(),
                   build=str(resolve(request['output']) / ('build-' + ident[:12])), folder=str(folder), error='', retryOf=retry)
        if request['loader'] == 'fabric' and not request.get('existingBuild'):
            report = scan_pack(resolve(request['source']))
            loader = read_json(workspace / 'compiler/fabric.lock.json')['fabricLoader']
            job['compatibilityOverrides'] = source_overrides(report, loader, request.get('forceCompile', False))
        if request.get('existingBuild'):
            job['build'] = str(resolve(request['existingBuild']))
            job['name'] = 'IPA 导出 · 26.1.2'
        if retry:
            old = read_json(job_path(workspace, retry))
            if old['state'] in ACTIVE or old['state'] == 'succeeded' or old['request'] != request: raise ValueError('此任务不能重试')
            job['build'] = old['build']
            if old.get('sourceFolder'): job['sourceFolder'] = old['sourceFolder']
        path = folder / 'job.json'
        write_json(path, job)
        with (folder / 'worker.log').open('ab') as log:
            child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), 'run-job', '--job', str(path)], cwd=workspace, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        job['pid'] = child.pid
        write_json(path, job)
        (folder / 'launch').touch()
        return job

def cancel(workspace, ident):
    path = job_path(workspace, ident)
    job = snapshot(path, False)
    if job['state'] in ACTIVE:
        (path.parent / 'cancel').touch()
        job['state'] = 'cancelling'
        if alive(job): os.kill(job['pid'], signal.SIGTERM)
    return job

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['bootstrap', 'check', 'start', 'status', 'cancel', 'history', 'retry', 'resolve-exclusions', 'save-config', 'run-job', 'storage-plan', 'storage-clean', 'storage-settings', 'save-storage', 'setup-start', 'setup-status'])
    parser.add_argument('--request', default='{}')
    parser.add_argument('--workspace', default=str(ROOT))
    parser.add_argument('--id')
    parser.add_argument('--job', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'run-job': run_job(args.job); return 0
        workspace = workspace_path(args.workspace)
        request = json.loads(args.request)
        if args.action in ('start', 'retry'):
            require_mount(f'desktop workbench {args.action}')
        if args.action == 'bootstrap': result = bootstrap(workspace)
        elif args.action == 'check': result = check(request)
        elif args.action == 'save-config': result = save_config(request)
        elif args.action == 'storage-settings': result = space_report(storage_paths(workspace))
        elif args.action == 'save-storage':
            with control_lock(workspace):
                if any(j['state'] in ACTIVE for j in history(workspace)): raise ValueError('请在构建结束后更改存储位置')
                from first_run import status as setup_status
                if setup_status().get('state') in ('queued', 'running'): raise ValueError('请在工具链准备结束后更改存储位置')
                result = save_paths(request['fields'], workspace)
        elif args.action == 'setup-start':
            from first_run import start as start_setup
            result = start_setup(request.get('fields', {}).get('owned') is True)
        elif args.action == 'setup-status':
            from first_run import status as setup_status
            result = setup_status()
        elif args.action == 'start': result = start(request)
        elif args.action == 'retry': result = start(read_json(job_path(workspace, args.id))['request'], args.id)
        elif args.action == 'resolve-exclusions': result = resolve_exclusions(workspace, args.id, request.get('fields', {}))
        elif args.action in ('storage-plan', 'storage-clean'): result = storage(args.action, request.get('fields', request))
        elif args.action == 'status': result = snapshot(job_path(workspace, args.id))
        elif args.action == 'cancel': result = cancel(workspace, args.id)
        else: result = history(workspace)
        print(json.dumps(result, ensure_ascii=False)); return 0
    except ExternalStorageUnavailable as e:
        print(json.dumps({'error': str(e), 'paused': True}, ensure_ascii=False)); return 3
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False)); return 2

if __name__ == '__main__': raise SystemExit(main())
