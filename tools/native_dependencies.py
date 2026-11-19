"""Native dependency inventory and transactional rebuilds for the desktop workbench.

Only fixed first-party builders are dispatched. Reports are read-only until a new
timestamped build has passed verification; the selected config is committed once.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import struct
from pathlib import Path
import sys

from bootstrap_toolchain import sha256
from mod_file_policy import is_metadata


def client_jar(paths) -> Path:
    """The hash-verified vanilla client recorded by the prepared build input."""
    prepared = read(paths['prepared'] / 'result.json')
    if prepared.get('status') != 'PREPARED':
        raise ValueError('客户端准备记录未通过：' + str(paths['prepared']))
    client = next((Path(r['path']) for r in prepared.get('referenceLibraries', [])
                   if Path(r['path']).name == '26.1.2.jar'), None)
    if client is None or not client.is_file():
        raise ValueError('构建配置缺少已核验的 26.1.2 客户端 JAR')
    entry = next(r for r in prepared['referenceLibraries'] if Path(r['path']) == client)
    if sha256(client) != entry.get('sha256'):
        raise ValueError('客户端 JAR 哈希与准备记录不一致：' + str(client))
    return client

# Topological order: the OpenGL shim reads OSMesa's exports while generating JNI.
SPECS = (
    ('glfw', 'GLFW-lite', 'build_glfw_lite', 'NATIVE_SUBSET_BUILT', (), ('libglfw.dylib',)),
    ('lwjgl', 'LWJGL-lite', 'build_lwjgl_lite', 'STATIC_JNI_BRIDGE_BUILT', ('glfw',),
     ('liblwjgl.dylib', 'lwjgl-ios.jar', 'lwjgl-glfw-ios.jar', 'lwjgl-stb-ios.jar', 'lwjgl-openal-ios.jar')),
    ('gl41', 'OSMesa / MoltenVK', 'fetch_gl41_runtime', 'GL41_RUNTIME_FETCHED', (), ('libOSMesa.8.dylib', 'libMoltenVK.dylib')),
    ('lwjglOpengl', 'LWJGL OpenGL shim', 'build_lwjgl_opengl_ios', 'LWJGL_OPENGL_SHIM_BUILT', ('gl41',), ('liblwjgl_opengl.dylib',)),
    ('metal', 'Metal 后端', 'build_metal_backend', 'METAL_BOOTSTRAP_BUILT', ('glfw', 'lwjgl'), ('libfaot_metal.dylib', 'metal-backend.jar', 'fabricaot-present.metallib')),
    ('openal', 'OpenAL Soft', 'build_openal_soft', 'OPENAL_SOFT_BUILT', (), ('libopenal.dylib',)),
    ('shaders', '着色器', 'translate_shaders', 'VANILLA_SHADERS_PRECOMPILED', (), ('bundle/index.json',)),
)
BY_KEY = {s[0]: s for s in SPECS}
REQUIRED = ('glfw', 'lwjgl', 'gl41', 'lwjglOpengl', 'openal')
SOURCE_GROUPS = {
    'glfw': ('ios/glfw-lite', 'tools/glfw_runtime_contract.py', 'tools/inventory_client_native_calls.py'),
    'lwjgl': ('compiler/lwjgl-lite', 'ios/lwjgl-lite', 'compiler/stb.lock.json', 'tools/lwjgl_codegen.py', 'tools/fetch_stb.py', 'interop/graphics/LwjglProbe.java'),
    'gl41': ('tools/verified_download.py',),
    'lwjglOpengl': (),
    'metal': ('compiler/metal-backend', 'ios/metal-bridge', 'interop/graphics/MetalProbe.java',
              'interop/graphics/MetalResourceProbe.java', 'interop/graphics/NativeImageProbe.java',
              'interop/graphics/MetalDrawProbe.java', 'interop/graphics/TextureSpecProbe.java',
              'interop/graphics/texture_transfer_test.c'),
    'openal': ('compiler/openal.lock.json', 'compiler/graphics-toolchain.lock.json', 'tools/prepare_shader_toolchain.py'),
    'shaders': ('compiler/shaders', 'compiler/graphics-toolchain.lock.json', 'tools/collect_shader_catalog.py'),
}
MANIFEST = 'dependency-manifest.json'


def read(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError('JSON 记录必须是对象：' + str(path))
    return value


def config_paths(config):
    values = read(config)
    if any(not isinstance(v, str) or not v.strip() or any(c in v for c in '\0\n\r') for v in values.values()):
        raise ValueError('依赖配置包含无效路径')
    return {k: (config.parent / Path(v).expanduser()).resolve() for k, v in values.items()}


def sources(root, key):
    paths = [root / ('tools/' + BY_KEY[key][2] + '.py'), root / 'tools/graphics_common.py']
    for name in SOURCE_GROUPS[key]:
        path = root / name
        paths.extend(path.rglob('*') if path.is_dir() else [path])
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(set(paths))
            if p.is_file() and not is_metadata(p) and '__pycache__' not in p.parts
            and p.suffix not in ('.pyc', '.class', '.jar')}


def artifacts(directory, key, report):
    """Require every shipped artifact's recorded hash, including overlays and shaders."""
    hashes = {}
    if key == 'gl41':
        from fetch_gl41_runtime import FILES, APACHE
        pinned = {r['name']: r['sha256'] for r in FILES}
        pinned['LICENSE-Apache-2.0.txt'] = APACHE[1]
        hashes.update(report.get('filesSHA256', {}))
        if any(hashes.get(name) != digest for name, digest in pinned.items()):
            raise ValueError('OSMesa / MoltenVK 记录偏离固定版本哈希')
    elif key == 'shaders':
        hashes['bundle/index.json'] = report.get('indexSHA256')
        for p in report.get('programs', []):
            hashes['bundle/' + p['key'] + '.metallib'] = p.get('metallibSHA256')
        if not report.get('programs'):
            raise ValueError('着色器构建记录缺少程序清单')
    else:
        hashes[BY_KEY[key][5][0]] = report.get('binarySHA256')
        if key == 'lwjgl':
            if not isinstance(report.get('overlaysSHA256'), dict):
                raise ValueError('LWJGL 产物记录缺少有效的 JAR 哈希清单')
            for name in ('lwjgl-ios.jar', 'lwjgl-glfw-ios.jar', 'lwjgl-stb-ios.jar', 'lwjgl-openal-ios.jar'):
                hashes[name] = report.get('overlaysSHA256', {}).get(str(directory / name))
        if key == 'metal':
            hashes.update({'metal-backend.jar': report.get('jarSHA256'),
                           'fabricaot-present.metallib': report.get('metallibSHA256')})
    for name, expected in hashes.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError('产物记录越过依赖目录：' + name)
        if not path.is_file():
            raise FileNotFoundError('依赖产物缺失：' + name)
        if not expected or sha256(path) != expected:
            raise ValueError('产物哈希校验失败：' + name)
        if path.suffix == '.dylib':
            from fetch_gl41_runtime import macho_platform
            macho_platform(path)
    if key == 'shaders':
        from build_c0_harness import validate_shader_bundle
        validate_shader_bundle(directory / 'bundle', simulator=False)
    return hashes


def dependency_hashes(paths, key):
    return {dep: {name: sha256(paths[dep] / name) for name in BY_KEY[dep][5]}
            for dep in BY_KEY[key][4]}


def inspect(root, paths, key):
    spec = BY_KEY[key]
    directory = paths.get(key)
    row = dict(key=key, name=spec[1], path=str(directory) if directory else '',
               builtAt=None, target='未知', state='missing', changedFiles=[], reasons=[],
               dependsOn=list(spec[4]), required=key in REQUIRED,
               mode='fetch' if key == 'gl41' else 'build')
    if not directory or not directory.is_dir() or not (directory / 'result.json').is_file():
        row['reasons'] = ['未配置路径或缺少构建记录']
        return row
    try:
        report = read(directory / 'result.json')
        row['builtAt'] = datetime.fromtimestamp((directory / 'result.json').stat().st_mtime, timezone.utc).isoformat()
        row['timeBasis'] = 'report-mtime'
        row['target'] = report.get('target') or ('arm64-apple-ios17.0' if key == 'gl41' or report.get('sdk') == 'iphoneos' else '未知')
        if row['target'] != 'arm64-apple-ios17.0':
            raise ValueError('目标架构不匹配：需要 iPhoneOS arm64，当前为 ' + row['target'])
        if report.get('status') != spec[3]:
            raise ValueError(report.get('error') or '构建记录未成功：' + str(report.get('status')))
        verified = artifacts(directory, key, report)
        manifest = read(directory / MANIFEST) if (directory / MANIFEST).exists() else None
        if manifest:
            if manifest.get('key') != key or manifest.get('artifacts') != verified:
                raise ValueError('依赖清单与构建记录不一致')
            recorded = manifest['sources']
            if not isinstance(recorded, dict):
                raise ValueError('依赖清单中的源码指纹格式无效')
            current = sources(root, key)
            row.update(builtAt=manifest['builtAt'], timeBasis='build', target=manifest['target'])
            row['changedFiles'] = sorted(n for n in recorded.keys() | current.keys() if recorded.get(n) != current.get(n))
        else:
            recorded = report.get('sourcesSHA256', {})
            if not isinstance(recorded, dict):
                raise ValueError('历史构建记录中的源码指纹格式无效')
            # Legacy reports did not all fingerprint the builder itself. Compare
            # the sources actually recorded, and directory membership where known.
            if not recorded and key != 'gl41':
                raise ValueError('历史构建缺少源码指纹，请重建以建立清单')
            for name, expected in recorded.items():
                path = (root / name).resolve()
                if not path.is_relative_to(root.resolve()):
                    raise ValueError('源码记录越过项目目录：' + name)
                if not path.is_file() or sha256(path) != expected:
                    row['changedFiles'].append(name)
            for group in SOURCE_GROUPS[key]:
                if any(n.startswith(group + '/') for n in recorded):
                    for name in sources(root, key):
                        if name.startswith(group + '/') and name not in recorded:
                            row['changedFiles'].append(name)
            row['changedFiles'] = sorted(set(row['changedFiles']))
        if row['target'] != 'arm64-apple-ios17.0':
            raise ValueError('目标架构不匹配：需要 iPhoneOS arm64，当前为 ' + row['target'])
        row['state'] = 'stale' if row['changedFiles'] else 'current'
        if row['changedFiles']:
            row['reasons'].append('源码已变更')
        try:
            deps = dependency_hashes(paths, key)
            legacy_hash = {'lwjgl': ('glfwLibrarySHA256', 'glfw', 'libglfw.dylib'),
                           'lwjglOpengl': ('osmesaSHA256', 'gl41', 'libOSMesa.8.dylib'),
                           'metal': ('glfwSHA256', 'glfw', 'libglfw.dylib')}.get(key)
            if manifest and manifest.get('dependencies') != deps:
                row['state'] = 'stale'
                row['reasons'].append('依赖库哈希已变更，待重建')
            if legacy_hash:
                field, dep, filename = legacy_hash
                if report.get(field) != deps[dep][filename]:
                    row['state'] = 'stale'
                    row['reasons'].append(BY_KEY[dep][1] + ' 哈希已变更，待重建')
            # GLFW exports are derived from the client's constant pools, so a
            # different client can require different entry points.
            if key == 'glfw':
                try:
                    current_client = sha256(client_jar(paths))
                except (OSError, ValueError, KeyError) as exc:
                    row['state'] = 'stale'
                    row['reasons'].append('客户端输入不可用，待重建：' + str(exc))
                else:
                    if report.get('clientSHA256') != current_client:
                        row['state'] = 'stale'
                        row['reasons'].append('客户端已变更，待重建')
        except (KeyError, OSError):
            row['state'] = 'stale'
            row['reasons'].append('前置依赖缺失，待重建')
    except FileNotFoundError as exc:
        row.update(state='missing', reasons=[str(exc)])
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        row.update(state='invalid', reasons=[str(exc)])
    return row


def inventory(root, config):
    paths = config_paths(config)
    rows = [inspect(root, paths, s[0]) for s in SPECS]
    by_key = {r['key']: r for r in rows}
    for row in rows:
        if row['state'] == 'current':
            blocked = [BY_KEY[k][1] for k in row['dependsOn'] if by_key[k]['state'] != 'current']
            if blocked:
                row.update(state='stale', reasons=['前置依赖需要重建：' + '、'.join(blocked)])
    return dict(ready=all(r['state'] == 'current' for r in rows if r['required']), libraries=rows,
                checkedAt=datetime.now(timezone.utc).isoformat())


def preflight(root, config):
    result = inventory(root, config)
    if not result['ready']:
        bad = [r for r in result['libraries'] if r['required'] and r['state'] != 'current']
        raise ValueError('原生依赖需要重建，请到「环境与资源」一键重建：\n' + '\n'.join(
            r['name'] + '：' + '；'.join(r['reasons'] + r['changedFiles']) for r in bad))
    return result


def plan(keys):
    if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or k not in BY_KEY for k in keys):
        raise ValueError('不支持的依赖库动作')
    if len(set(keys)) != len(keys):
        raise ValueError('依赖库选择重复')
    return [s[0] for s in SPECS if s[0] in keys]


def prerequisites(root, paths, key):
    for dep in BY_KEY[key][4]:
        row = inspect(root, paths, dep)
        if row['state'] != 'current':
            raise ValueError('请先重建 ' + row['name'] + '：' + '；'.join(row['reasons'] + row['changedFiles']))


def command(root, paths, key, output):
    argv = [sys.executable, '-B', root / ('tools/' + BY_KEY[key][2] + '.py'), '--output', output]
    if key != 'gl41':
        argv += ['--sdk', 'iphoneos']
    # A packaged app omits artifacts/, so client-derived inputs come from the
    # selected build configuration instead of the source tree.
    if key == 'glfw':
        argv += ['--client', client_jar(paths)]
    if key in ('lwjgl', 'metal'):
        argv += ['--prepared', paths['prepared']]
        argv += ['--glfw-library', paths['glfw'] / 'libglfw.dylib']
    if key == 'metal':
        argv += ['--graphics-bridge', paths['lwjgl']]
    if key == 'lwjglOpengl':
        prepared = read(paths['prepared'] / 'result.json')
        jar = next((Path(r['path']) for r in prepared['referenceLibraries'] if Path(r['path']).name == 'lwjgl-opengl-3.4.1.jar'), None)
        if jar is None:
            raise ValueError('参考输入缺少 LWJGL OpenGL 3.4.1 JAR')
        entry = next(r for r in prepared['referenceLibraries'] if Path(r['path']) == jar)
        if sha256(jar) != entry['sha256']:
            raise ValueError('LWJGL OpenGL JAR 哈希校验失败')
        argv += ['--java-home', prepared['javaHome'], '--lwjgl-opengl', jar, '--osmesa', paths['gl41'] / 'libOSMesa.8.dylib']
    if key == 'shaders':
        # Optional Metal route: the catalog and host tools are separate builds,
        # not part of a packaged source tree.
        catalog = root / 'artifacts/graphics/shader-catalog-03'
        toolchain = root / 'artifacts/graphics/shader-toolchain-03'
        if not (catalog / 'result.json').is_file() or not (toolchain / 'result.json').is_file():
            raise ValueError('着色器重建需要先准备 shader-catalog-03 与 shader-toolchain-03；'
                             '分发应用不含 artifacts/，请从源码目录生成，或继续使用已有着色器产物')
        argv += ['--catalog', catalog, '--toolchain', toolchain]
    return list(map(str, argv))


def build_one(root, paths, key, destination, execute, write_json):
    prerequisites(root, paths, key)
    before = sources(root, key)
    before_deps = dependency_hashes(paths, key)
    argv = command(root, paths, key, destination)
    execute(argv, key)
    report = read(destination / 'result.json')
    if report.get('status') != BY_KEY[key][3]:
        raise ValueError(report.get('error') or key + ' 构建未通过')
    hashes = artifacts(destination, key, report)
    if before != sources(root, key) or before_deps != dependency_hashes(paths, key):
        raise ValueError('构建过程中源码或依赖库发生变化：' + key)
    manifest = dict(schema=1, key=key, builtAt=datetime.now(timezone.utc).isoformat(),
                    target='arm64-apple-ios17.0', sources=before, artifacts=hashes, dependencies=before_deps)
    write_json(destination / MANIFEST, manifest)
    row = inspect(root, {**paths, key: destination}, key)
    if row['state'] != 'current':
        raise ValueError('新产物验证失败：' + '；'.join(row['reasons'] + row['changedFiles']))
    from graphics_common import register_tree
    register_tree(destination / MANIFEST, argv, recursive=False)


def rebuild(root, config, keys, output, execute, cancelled, update, write_json):
    """Build in dependency order; atomically switch paths only after all succeed."""
    keys = plan(keys)
    original_hash = sha256(config)
    original = read(config)
    paths = config_paths(config)
    # Validate every selected input before compiling anything. A packaged app
    # omits artifacts/, so an optional Metal shader rebuild must fail now rather
    # than after the required libraries have already been compiled.
    problems = []
    for key in keys:
        try:
            command(root, paths, key, output / key)
        except (OSError, ValueError, KeyError) as exc:
            problems.append(BY_KEY[key][1] + '：' + str(exc))
    if problems:
        raise ValueError('依赖重建所需输入不完整：\n' + '\n'.join(problems))
    output.mkdir(parents=True, exist_ok=False)
    outputs = {}
    for index, key in enumerate(keys):
        if cancelled():
            raise InterruptedError('依赖库重建已取消')
        destination = output / key
        update(stage='dependency-' + key, dependencyProgress=dict(completed=index, total=len(keys), key=key))
        def execute_step(argv, name):
            execute(argv, name)
            if cancelled():
                raise InterruptedError('依赖库重建已取消')
        build_one(root, paths, key, destination, execute_step, write_json)
        paths[key] = destination
        outputs[key] = str(destination)
    # Verify all selected inputs again immediately before committing the config.
    for key in keys:
        row = inspect(root, paths, key)
        if row['state'] != 'current':
            raise ValueError('提交配置前依赖已变更：' + key)
    if cancelled():
        raise InterruptedError('依赖库重建已取消')
    if sha256(config) != original_hash:
        raise ValueError('构建配置已被修改，保留新产物；请刷新配置后重试')
    write_json(config, {**original, **outputs})
    update(configFields=read(config), dependencyProgress=dict(completed=len(keys), total=len(keys)))
    return outputs
