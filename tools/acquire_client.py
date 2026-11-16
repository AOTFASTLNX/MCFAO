"""Acquire owned client inputs from official origins; never authenticate or execute game code."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from bootstrap_toolchain import sha256
from verified_download import fetch, metadata, GAME_HOSTS, TOOL_HOSTS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'


def library_path(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe library path')
    return Path(*p.parts)


def engine_url(name):
    if name.startswith('asm-'):
        artifact = name.removesuffix('-9.10.1.jar')
        return f'https://repo.maven.apache.org/maven2/org/ow2/asm/{artifact}/9.10.1/{name}'
    if name.startswith('fabric-loader-'):
        return 'https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.19.3/' + name
    return 'https://maven.fabricmc.net/net/fabricmc/sponge-mixin/0.17.3+mixin.0.8.7/' + name


def acquire(output, owned, progress=print):
    if owned is not True:
        raise ValueError('Confirm ownership before downloading Minecraft')
    output = Path(output).resolve()
    if output.is_relative_to(ROOT.resolve()):
        raise ValueError('Owned game content must be stored outside the source repository')
    output.mkdir(parents=True, exist_ok=True)
    versions = metadata(MANIFEST)['versions']
    entry = next(v for v in versions if v['id'] == '26.1.2' and v['type'] == 'release')
    # Official version manifest supplies SHA-1; obtain bounded bytes and verify before use.
    from verified_download import opener, check_url
    check_url(entry['url'], GAME_HOSTS)
    with opener(GAME_HOSTS).open(entry['url'], timeout=45) as response:
        check_url(response.url, GAME_HOSTS)
        raw = response.read(4 * 1024**2 + 1)
    if len(raw) > 4 * 1024**2 or hashlib.sha1(raw).hexdigest() != entry['sha1']:
        raise ValueError('Official version metadata fingerprint mismatch')
    version = json.loads(raw)
    if version['id'] != '26.1.2': raise ValueError('Wrong Minecraft version')
    meta_path = output / '26.1.2.json'
    if meta_path.exists() and meta_path.read_bytes() != raw: raise ValueError('Existing version metadata changed')
    if not meta_path.exists(): meta_path.write_bytes(raw)
    jars = []
    def add(spec, path, hosts=GAME_HOSTS):
        progress('校验游戏输入：' + path.name)
        fetch(spec, path, hosts)
        jars.append(dict(path=str(path), sha256=sha256(path), size=path.stat().st_size))
    add(version['downloads']['client'], output / 'meta/versions/26.1.2/26.1.2.jar')
    total = version['downloads']['client']['size']
    for library in version['libraries']:
        rules = library.get('rules', [])
        allowed = not rules
        for rule in rules:
            os_rule = rule.get('os', {})
            if os_rule.get('name', 'osx') == 'osx' and os_rule.get('arch', 'arm64') in ('arm64', 'aarch64') and not rule.get('features'):
                allowed = rule['action'] == 'allow'
        if not allowed: continue
        artifact = library.get('downloads', {}).get('artifact')
        if not artifact: continue
        total += artifact['size']
        if total > 1024**3 or len(jars) > 1000: raise ValueError('Client library budget exceeded')
        add(artifact, output / 'meta/libraries' / library_path(artifact['path']))
    for spec in json.loads((ROOT / 'compiler/fabric.lock.json').read_text())['engineLibraries']:
        add(dict(url=engine_url(spec['file']), size=spec['bytes'], sha256=spec['sha256']),
            output / 'meta/libraries/engine' / spec['file'], TOOL_HOSTS)
    from stage_game_assets import verified_assets
    assets = output / 'assets'
    assets.mkdir(exist_ok=True)
    progress('下载并校验官方资源索引与对象')
    verified_assets(assets, version, assets)
    result = dict(status='OWNED_CLIENT_INPUTS_VERIFIED', gateA0='BLOCKED',
                  scope='download/hash verification only; no desktop game execution or ownership authentication',
                  ownershipConfirmed=True, jars=jars, versionMetadata=str(meta_path), assets=str(assets))
    temporary = output / 'client-inputs.pending.json'
    temporary.write_text(json.dumps(result, indent=2) + '\n')
    temporary.replace(output / 'client-inputs.json')
    return result
