"""Prepare the GL41 inputs for the installed Builder using the existing build tools."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

from bootstrap_toolchain import sha256
from bundle_source import B1_EVIDENCE
from capture import capture
from external_storage import require_mount
from prepare_shader_toolchain import extract
from storage_config import require_space
from verified_download import fetch
import native_dependencies

HEADER_DIR = Path('build/fabricaot-host/support/headers/java.base')


def check_host():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('自动准备需要 Apple Silicon Mac。')
    try:
        for command in (
            ['/usr/bin/xcodebuild', '-checkFirstLaunchStatus'],
            ['/usr/bin/xcrun', '--sdk', 'iphoneos', '--show-sdk-path'],
        ):
            subprocess.run(command, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('请打开 Xcode 完成初始设置，并在设置中选择含 iPhoneOS SDK 的 Xcode。') from exc
    return subprocess.check_output(['/usr/bin/xcodebuild', '-version'], timeout=20)


def host_tools(root, cache, scratch, run):
    specs = json.loads((root / 'compiler/jdk-host-tools.lock.json').read_text())
    prefix = scratch / 'host'
    env = {**os.environ, 'PATH': f'{prefix / "bin"}:/usr/bin:/bin:/usr/sbin:/sbin'}
    for name, spec in specs.items():
        archive = fetch(spec, cache / 'host-tools' / spec['file'])
        sources = scratch / name
        extract(archive, sources)
        directory = sources / spec['file'].removesuffix('.tar.gz')
        run('configure-' + name, ['/bin/bash', directory / 'configure',
                                  '--prefix=' + str(prefix), '--disable-nls'], directory, env)
        run('install-' + name, ['/usr/bin/make', '-j4', 'install'], directory, env)
    return env


def prepare_headers(root, cache, home, jdk, logs, run):
    headers = jdk / HEADER_DIR
    # Generate on the system volume. OpenJDK configure rejects spaces and the
    # source build can require filesystem features unavailable on external volumes.
    with tempfile.TemporaryDirectory(prefix='ncl-jdk-', dir='/private/tmp') as temporary:
        scratch = Path(temporary)
        env = host_tools(root, cache, scratch, run)
        spec = json.loads((root / 'compiler/upstream.lock.json').read_text())['jdk']
        archive = cache / 'upstream' / ('jdk-' + spec['commit'] + '.tar.gz')
        from fetch_upstream import extract_source
        source = extract_source(archive, scratch / 'jdk', spec['commit'])
        boot = home
        if any(char.isspace() for char in str(home)):
            boot = scratch / 'java'
            shutil.copytree(home, boot, symlinks=True)
        run('configure-jdk', ['/bin/bash', source / 'configure',
            '--with-conf-name=fabricaot-host', '--with-boot-jdk=' + str(boot),
            '--with-debug-level=release', '--with-native-debug-symbols=none',
            '--disable-warnings-as-errors', '--with-num-cores=4', '--with-memory-size=4096'], source, env)
        run('generate-jni-headers', ['/usr/bin/make', 'CONF=fabricaot-host', 'JOBS=4', 'java.base-java'], source, env)
        if not (source / HEADER_DIR / 'java_lang_System.h').is_file():
            raise ValueError('OpenJDK 没有生成所需的 JNI 头文件，请查看 ' + str(logs))
        # The extracted sources and these generated headers are used by both runtime builds.
        headers.parent.mkdir(parents=True, exist_ok=True)
        pending = headers.with_name('headers-' + uuid4().hex)
        shutil.copytree(source / HEADER_DIR, pending)
        pending.rename(headers)


def preparation_key(root, home, client, sdk):
    from bundle_source import source_identity
    digest = hashlib.sha256(sdk)
    digest.update(json.dumps(source_identity(root), sort_keys=True).encode())
    for path in (root, home, client['versionMetadata'], client['assets']):
        digest.update(os.fsencode(path) + b'\0')
    digest.update(bytes.fromhex(sha256(Path(client['versionMetadata']))))
    return digest.hexdigest()


def verify_config(root, path):
    from mcfao import inputs, load_config
    native_dependencies.preflight(root, path)
    inputs(load_config(path, 'gl41'), 'gl41')


def prepare(root, paths, home, client, game, sdk, update, write_json):
    """Reuse completed inputs. Publish the config only after the actual build preflight."""
    from inspect_ios_candidate import inspect
    import zipfile

    cache = paths['cache'].resolve()
    generation = (paths['jobs'] / 'setup' / preparation_key(root, home, game, sdk)).resolve()
    generation.mkdir(parents=True, exist_ok=True)
    logs = generation / ('attempt-' + uuid4().hex[:10])
    logs.mkdir()
    config = generation / 'config.json'
    update(stage='verify', message='检查已有构建环境', logDirectory=str(logs))
    try:
        if config.is_file():
            verify_config(root, config)
            return config
    except (OSError, RuntimeError, ValueError, KeyError):
        pass

    # A failed stage stays in its own attempt folder. Only validated stage
    # records enter the checkpoint, so a retry skips successful commands.
    checkpoint = generation / 'steps.json'
    completed = json.loads(checkpoint.read_text()) if checkpoint.is_file() else {}
    if config.is_file():
        completed = {}

    def run(name, argv, cwd=root, env=None):
        require_mount('prepare ' + name)
        require_space(paths)
        directory = logs / name
        if env is None:
            result = capture(list(map(str, argv)), directory, 2400, cwd)
            if not result['exitCode'] and not result['timedOut']:
                return
        else:
            directory.mkdir()
            with (directory / 'stdout.log').open('w') as out, (directory / 'stderr.log').open('w') as err:
                write_json(directory / 'command.json', {'argv': list(map(str, argv)), 'cwd': str(cwd)})
                process = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                         stdout=out, stderr=err, timeout=2400)
            if process.returncode == 0:
                return
        raise RuntimeError(name + ' 未完成。日志：' + str(directory))

    def stage(name, title, action, marker):
        update(stage=name, message=title)
        old = completed.get(name)
        if old:
            candidate = Path(old['path'])
            if candidate.is_relative_to(generation) and (candidate / marker).is_file() and sha256(candidate / marker) == old['sha256']:
                return candidate
        target = logs / name
        action(target)
        completed[name] = dict(path=str(target), sha256=sha256(target / marker))
        write_json(checkpoint, completed)
        return target

    def script(name, output, *args):
        run(name, [sys.executable, '-B', root / 'tools' / (name + '.py'), '--output', output, *args])

    def copy_caps(destination):
        spec = json.loads((root / 'compiler/toolchains.lock.json').read_text())['iosCandidate']
        archive = cache / 'toolchains' / spec['file']
        files = inspect(archive, spec)['capFiles']
        destination.mkdir()
        with zipfile.ZipFile(archive) as source:
            for name in files:
                (destination / Path(name).name).write_bytes(source.read(name))
        write_json(destination / 'result.json', {'filesSHA256': {Path(f).name: sha256(destination / Path(f).name) for f in files}})

    jdk = Path(json.loads((cache / 'upstream/jdk.json').read_text())['path'])
    graal = Path(json.loads((cache / 'upstream/graal.json').read_text())['path'])
    if not (jdk / HEADER_DIR / 'java_lang_System.h').is_file():
        update(stage='headers', message='正在生成 OpenJDK JNI 头文件')
        prepare_headers(root, cache, home, jdk, logs, run)
    prepared = stage('prepared', '正在准备 Minecraft 编译输入',
                     lambda out: script('prepare_b0', out, '--graalvm-home', home, '--client-dir', client), 'result.json')
    runtime = stage('runtime', '正在编译 iOS Java 运行库',
                    lambda out: script('build_ios_runtime', out, '--sdk', 'iphoneos', '--with-extnet',
                                       '--graalvm-home', home, '--jdk-source', jdk, '--graal-source', graal), 'result.json')
    splitter = stage('splitter', '正在编译字节码处理工具',
                     lambda out: script('build_method_splitter', out, '--java-home', home), 'result.json')
    caps = stage('caps', '正在校验 iOS ABI 数据', copy_caps, 'result.json')
    b1 = root / B1_EVIDENCE
    if json.loads(b1.read_text()).get('gateB1') != 'PASS':
        raise ValueError('应用缺少已确认的 B1 真机证据，请重新安装完整的 Builder。')
    fields = dict(prepared=prepared, caps=caps, bootstrapRuntime=runtime, splitter=splitter,
                  versionMetadata=game['versionMetadata'], assets=game['assets'], b1Evidence=b1,
                  openjdkSource=jdk, graalSource=graal)
    def compile_dependency(argv, name):
        run('dependency-' + name, argv)

    for key in native_dependencies.REQUIRED:
        label = native_dependencies.BY_KEY[key][1]
        fields[key] = stage(key, '正在准备 ' + label,
                            lambda out: native_dependencies.build_one(
                                root, fields, key, out, compile_dependency, write_json),
                            native_dependencies.MANIFEST)
    update(stage='verify', message='正在验证并保存构建配置')
    candidate = logs / 'config.json'
    write_json(candidate, {key: str(value) for key, value in fields.items()})
    try:
        verify_config(root, candidate)
    except (OSError, RuntimeError, ValueError, KeyError):
        # A tampered cached output can pass its marker check but fail full
        # validation. The next attempt starts fresh without touching old files.
        write_json(checkpoint, {})
        raise
    candidate.replace(config)
    return config
