#!/usr/bin/env python3
"""Fetch fixed, hash-pinned research inputs. Never run third-party build scripts.

This is not a general modpack downloader or the Gate D0 security boundary.
Only the official desktop JDK is extracted. The iOS candidate remains a ZIP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import ssl
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_HOSTS = {"github.com", "release-assets.githubusercontent.com",
                 "objects.githubusercontent.com"}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Toolchain download URL outside fixed HTTPS origin policy")


class FixedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(spec: dict, destination: Path) -> Path:
    validate_url(spec["url"])
    if destination.is_symlink():
        raise ValueError("Refusing symlink destination")
    if destination.exists():
        if destination.stat().st_size != spec["size"] or sha256(destination) != spec["sha256"]:
            raise ValueError(f"Existing input failed pinned hash: {destination}")
        print(f"Verified cached {destination.name}", flush=True)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    context = ssl.create_default_context()
    # python.org macOS installers may have no default CA bundle configured.
    # Add the OS CA bundle while retaining certificate/hostname verification.
    system_ca = Path("/etc/ssl/cert.pem")
    if system_ca.is_file():
        context.load_verify_locations(cafile=str(system_ca))
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), FixedRedirects())
    request = urllib.request.Request(spec["url"], headers={"User-Agent": "FabricAOT-research/0.1"})
    count = 0
    digest = hashlib.sha256()
    # Exclusive creation preserves any interrupted download for inspection.
    with opener.open(request, timeout=45) as response, partial.open("xb") as output:
        validate_url(response.url)
        if response.status != 200:
            raise ValueError(f"Unexpected HTTP status: {response.status}")
        while block := response.read(1024 * 1024):
            count += len(block)
            if count > spec["size"]:
                raise ValueError("Download exceeds pinned size")
            output.write(block)
            digest.update(block)
    if count != spec["size"] or digest.hexdigest() != spec["sha256"]:
        raise ValueError(f"Downloaded input failed pinned size/hash: {partial}")
    partial.rename(destination)
    print(f"Verified {destination.name}: {digest.hexdigest()}", flush=True)
    return destination


def extract_jdk(archive: Path, destination: Path) -> Path:
    if destination.exists():
        # Do not silently trust a previously modified extracted installation.
        raise ValueError(f"Extraction directory already exists: {destination}; use its JDK explicitly")
    destination.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        if len(members) > 30_000 or sum(m.size for m in members) > 3 * 1024**3:
            raise ValueError("JDK archive exceeds extraction budget")
        # Python 3.11.8 includes the backported data filter: reject escaping
        # paths, special files, and escaping hard/symbolic links.
        source.extractall(destination, members=members, filter="data")
    homes = list(destination.glob("*/Contents/Home"))
    if len(homes) != 1 or not (homes[0] / "bin/native-image").is_file():
        raise ValueError("Official archive does not contain one expected GraalVM JDK")
    return homes[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args(argv)
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("Pinned desktop input requires macOS arm64")
    # JDK launch options must not inject agents into these first-party tests.
    injected = [name for name in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")
                if os.environ.get(name)]
    if injected:
        parser.error("Unset JVM option injection variables: " + ", ".join(injected))
    lock = json.loads((ROOT / "compiler/toolchains.lock.json").read_text())
    cache = ROOT / ".cache/toolchains"
    for key in ("iosCandidate", "graalvm"):
        fetch(lock[key], cache / lock[key]["file"])
    if not args.download_only:
        home = extract_jdk(cache / lock["graalvm"]["file"], cache / "graalvm-25.0.2")
        print(f"GRAALVM_HOME={home}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
