"""Bounded HTTPS downloads; every redirect and cached/downloaded byte is verified."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import ssl
import urllib.request
from urllib.parse import urlsplit
from uuid import uuid4

TOOL_HOSTS = frozenset({'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
    'codeload.github.com', 'raw.githubusercontent.com', 'cmake.org', 'www.apache.org',
    'repo.maven.apache.org', 'repo1.maven.org', 'maven.fabricmc.net', 'ftp.gnu.org'})
GAME_HOSTS = frozenset({'piston-meta.mojang.com', 'piston-data.mojang.com',
    'launcher.mojang.com', 'libraries.minecraft.net', 'resources.download.minecraft.net'})


def check_url(url, hosts):
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443) or p.fragment:
        raise ValueError('Download URL outside the fixed HTTPS origins: ' + url)


def opener(hosts):
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            check_url(newurl, hosts)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    context = ssl.create_default_context()
    if Path('/etc/ssl/cert.pem').is_file(): context.load_verify_locations(cafile='/etc/ssl/cert.pem')
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), Redirect())


def fetch(spec, target, hosts=TOOL_HOSTS):
    check_url(spec['url'], hosts)
    target = Path(target)
    algorithm = 'sha256' if 'sha256' in spec else 'sha1'
    digest = spec[algorithm]
    size = spec['size']
    if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= 2 * 1024**3:
        raise ValueError('Invalid download byte budget')
    if target.is_symlink(): raise ValueError('Linked download target')
    for parent in target.parents:
        if parent.is_symlink(): raise ValueError('Linked download parent: ' + str(parent))
    if target.exists():
        with target.open('rb') as stream: actual = hashlib.file_digest(stream, algorithm).hexdigest()
        if target.stat().st_size != size or actual != digest: raise ValueError('Modified cached input: ' + str(target))
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.' + uuid4().hex + '.part')
    count, actual = 0, hashlib.new(algorithm)
    with opener(hosts).open(spec['url'], timeout=45) as response, partial.open('xb') as stream:
        check_url(response.url, hosts)
        if response.status != 200: raise ValueError('Unexpected HTTP status')
        while block := response.read(1024**2):
            count += len(block)
            if count > size: raise ValueError('Download exceeds pinned size')
            actual.update(block)
            stream.write(block)
    if count != size or actual.hexdigest() != digest: raise ValueError('Downloaded size/hash mismatch: ' + str(partial))
    partial.rename(target)
    return target


def metadata(url, hosts=GAME_HOSTS, limit=4 * 1024**2):
    check_url(url, hosts)
    with opener(hosts).open(url, timeout=45) as response:
        check_url(response.url, hosts)
        if response.status != 200: raise ValueError('Unexpected metadata status')
        data = response.read(limit + 1)
    if len(data) > limit: raise ValueError('Metadata exceeds byte budget')
    return json.loads(data)
