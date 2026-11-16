"""Persistent first-run download worker. No downloaded build script or Mod is executed."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from storage_config import storage_paths, require_space, control_lock
from external_storage import require_mount
from verified_download import fetch
from bootstrap_toolchain import sha256

ROOT = Path(__file__).resolve().parents[1]


def download_specs(root=ROOT):
    tools = json.loads((root / 'compiler/toolchains.lock.json').read_text())
    rows = [(Path('toolchains') / tools[key]['file'], tools[key]) for key in ('graalvm', 'iosCandidate')]
    for key, spec in json.loads((root / 'compiler/upstream.lock.json').read_text()).items():
        if not isinstance(spec, dict): continue
        rows.append((Path('upstream') / (key + '-' + spec['commit'] + '.tar.gz'),
                     dict(url=spec['url'], size=spec['archiveBytes'], sha256=spec['archiveSHA256'])))
    for spec in json.loads((root / 'compiler/graphics-toolchain.lock.json').read_text()).values():
        rows.append((Path('graphics/shader-toolchain/archives') / spec['file'], spec))
    spec = json.loads((root / 'compiler/openal.lock.json').read_text())
    rows.append((Path('graphics/openal-soft') / spec['file'], spec))
    for spec in json.loads((root / 'compiler/asm.lock.json').read_text()).values():
        rows.append((Path('libs/asm-9.9') / spec['file'], spec))
    for name, spec in json.loads((root / 'compiler/stb.lock.json').read_text())['files'].items():
        rows.append((Path('graphics/stb-lwjgl-3.4.1') / name, dict(url=spec['url'], size=spec['bytes'], sha256=spec['sha256'])))
    from fetch_gl41_runtime import FILES, BASE, APACHE
    for spec in FILES:
        rows.append((Path('graphics/gl41-runtime') / spec['name'], dict(url=BASE + spec['name'], size=spec['bytes'], sha256=spec['sha256'])))
    rows.append((Path('graphics/gl41-runtime/LICENSE-Apache-2.0.txt'), dict(url=APACHE[0], size=11358, sha256=APACHE[1])))
    return rows


def state_path():
    return storage_paths()['jobs'] / 'setup/status.json'


def status():
    path = state_path()
    state = json.loads(path.read_text()) if path.is_file() else {'state': 'idle'}
    if state.get('state') in ('queued', 'running') and state.get('pid'):
        try:
            command = subprocess.check_output(['/bin/ps', '-p', str(state['pid']), '-o', 'args='], text=True, timeout=5)
            alive = 'first_run.py' in command
        except (OSError, subprocess.SubprocessError): alive = False
        if not alive:
            state.update(state='failed', error='工具链准备进程已中断，请重试；原文件保留。')
            write_state(path, state)
    return state


def write_state(path, value):
    pending = path.with_name('status-' + uuid4().hex + '.json')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)


def start(owned=False):
    with control_lock():
        return _start(owned)


def _start(owned=False):
    require_mount('first-run downloads')
    require_space()
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = json.loads(path.read_text()) if path.exists() else {}
        if old.get('state') in ('queued', 'running'):
            try:
                args = subprocess.check_output(['/bin/ps', '-p', str(old['pid']), '-o', 'args='], text=True, timeout=5)
                if 'first_run.py' in args: return old
            except (KeyError, OSError, subprocess.SubprocessError): pass
        if old.get('state') == 'ready' and old.get('cache') == str(storage_paths()['cache'].resolve()) and (not owned or old.get('client')): return old
        state = dict(state='queued', totalBytes=sum(s['size'] for _, s in download_specs()), completedBytes=0,
                     message='准备下载固定版本工具链', owned=owned)
        write_state(path, state)
        with (path.parent / 'worker.log').open('ab') as log:
            child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--state', str(path),
                                      *(['--owned'] if owned else [])],
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        state['pid'] = child.pid
        # The worker waits for this record before taking the execution lock.
        write_state(path, state)
        return state


def run(path, owned=False):
    # Share the launch lock: the parent's queued/PID write must precede our progress writes.
    with (path.parent / 'launch.lock').open('a') as launch:
        fcntl.flock(launch, fcntl.LOCK_EX)
    with (path.parent / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = dict(state='running', pid=os.getpid(), completedBytes=0, cache=str(storage_paths()['cache'].resolve()),
                     totalBytes=sum(s['size'] for _, s in download_specs()))
        def update(**fields):
            state.update(fields)
            write_state(path, state)
        try:
            require_mount('first-run worker')
            require_space()
            cache = storage_paths()['cache'].resolve()
            update(message='下载并校验工具链，不执行第三方脚本')
            for relative, spec in download_specs():
                update(message='下载 / 校验 ' + relative.name)
                fetch(spec, cache / relative)
                update(completedBytes=state['completedBytes'] + spec['size'])
            from prepare_shader_toolchain import extract
            jdk_lock = json.loads((ROOT / 'compiler/toolchains.lock.json').read_text())['graalvm']
            update(message='校验并展开 GraalVM 与固定版本源码')
            extract(cache / 'toolchains' / jdk_lock['file'], cache / 'toolchains/graalvm-25.0.2')
            homes = list((cache / 'toolchains/graalvm-25.0.2').glob('*/Contents/Home'))
            if len(homes) != 1 or not (homes[0] / 'bin/native-image').is_file(): raise ValueError('GraalVM executable missing')
            # The candidate ZIP remains data: executionAllowed=false is preserved.
            for key, spec in json.loads((ROOT / 'compiler/upstream.lock.json').read_text()).items():
                if not isinstance(spec, dict): continue
                archive = cache / 'upstream' / (key + '-' + spec['commit'] + '.tar.gz')
                # OpenJDK has more entries than shader archives; use its audited bounded extractor.
                from fetch_upstream import extract_source
                directory = cache / 'upstream' / key
                if not directory.exists(): source = extract_source(archive, directory, spec['commit'])
                else:
                    source = directory / (('labs-openjdk-' if key == 'jdk' else 'graal-') + spec['commit'])
                    if not source.is_dir(): raise ValueError('Upstream extraction differs from pinned root')
                    extract(archive, directory, max_entries=150000)
                notices = {name: sha256(source / name) for name in spec['licenseFiles'] if (source / name).is_file()}
                if not notices: raise ValueError('Missing source license notices')
                record = dict(path=str(source), commit=spec['commit'], archiveSHA256=spec['archiveSHA256'], licenseFilesSHA256=notices)
                (cache / 'upstream' / (key + '.json')).write_text(json.dumps(record, indent=2) + '\n')
            if owned:
                from acquire_client import acquire
                client = cache / 'owned-client/26.1.2'
                result = acquire(client, True, lambda message: update(message=message))
                update(client=str(client), clientMetadata=result['versionMetadata'], assets=result['assets'])
            update(state='ready', javaHome=str(homes[0]), message='工具链下载和校验完成；iOS 编译前置产物仍需按构建说明准备。')
        except Exception as exc:
            update(state='failed', error=str(exc), message='准备失败；已下载文件与日志保留，可重试')
            return 2
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--owned', action='store_true')
    args = parser.parse_args()
    raise SystemExit(run(args.state, args.owned))
