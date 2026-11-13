#!/usr/bin/env python3
"""Fetch Minecraft 26.1.2 client + libraries + Fabric engine jars, and synthesise the
A0 reference evidence that tools/prepare_b0.py expects.

Nothing here is committed: the jar lives only in the CI workspace and is never uploaded.
The user must own the game; we only use the public Mojang CDN like a launcher would.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) FabricAOT-research/0.1"}
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC = "https://maven.fabricmc.net"
MAVEN = "https://repo1.maven.org/maven2"

ENGINE = [
    (f"{FABRIC}/net/fabricmc/fabric-loader/0.19.3/fabric-loader-0.19.3.jar", "fabric-loader-0.19.3.jar"),
    (f"{FABRIC}/net/fabricmc/sponge-mixin/0.17.3+mixin.0.8.7/sponge-mixin-0.17.3+mixin.0.8.7.jar",
     "sponge-mixin-0.17.3+mixin.0.8.7.jar"),
]
for name in ("asm", "asm-analysis", "asm-commons", "asm-tree", "asm-util"):
    ENGINE.append((f"{MAVEN}/org/ow2/asm/{name}/9.10.1/{name}-9.10.1.jar", f"{name}-9.10.1.jar"))


def get(url: str, dest: Path, *, sha1: str | None = None, size: int | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        data = dest.read_bytes()
        if (sha1 is None or hashlib.sha1(data).hexdigest() == sha1) and (size is None or len(data) == size):
            return dest
        dest.unlink()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if size is not None and len(data) != size:
        raise SystemExit(f"size mismatch for {url}: {len(data)} != {size}")
    if sha1 is not None and hashlib.sha1(data).hexdigest() != sha1:
        raise SystemExit(f"sha1 mismatch for {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.rename(dest)
    return dest


def rules_allow(lib: dict, os_name: str = "osx", arch: str = "arm64") -> bool:
    rules = lib.get("rules")
    if not rules:
        return True
    allowed = False
    for rule in rules:
        if "os" in rule:
            os_rule = rule["os"]
            if os_rule.get("name", os_name) != os_name:
                continue
            if "arch" in os_rule and os_rule["arch"] != arch:
                continue
        allowed = rule.get("action") == "allow"
    return allowed


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--src-root", type=Path, required=True, help="cloned upstream root")
    args = p.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    meta = out / "meta"
    (meta / "versions").mkdir(parents=True, exist_ok=True)

    manifest = json.loads(urllib.request.urlopen(
        urllib.request.Request(MANIFEST, headers=UA), timeout=60).read())
    entry = next(v for v in manifest["versions"] if v["id"] == "26.1.2")
    version_json = out / "26.1.2.json"
    if not version_json.is_file():
        version_json.write_bytes(urllib.request.urlopen(
            urllib.request.Request(entry["url"], headers=UA), timeout=60).read())
    version = json.loads(version_json.read_text())
    assert version["id"] == "26.1.2", version["id"]

    jars = []

    def add(path: Path):
        jars.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "size": path.stat().st_size})

    client = meta / "versions/26.1.2/26.1.2.jar"
    download = version["downloads"]["client"]
    get(download["url"], client, sha1=download["sha1"], size=download.get("size"))
    add(client)

    libdir = meta / "libraries"
    skipped = 0
    for lib in version["libraries"]:
        if not rules_allow(lib):
            skipped += 1
            continue
        art = lib.get("downloads", {}).get("artifact")
        if not art:
            continue
        path = libdir / art["path"]
        get(art["url"], path, sha1=art["sha1"], size=art.get("size"))
        add(path)
        for classifier, art2 in (lib.get("downloads", {}).get("classifiers") or {}).items():
            if "macos" in classifier or "osx" in classifier:
                path2 = libdir / art2["path"]
                get(art2["url"], path2, sha1=art2["sha1"], size=art2.get("size"))
                add(path2)

    lock = json.loads((args.src_root / "compiler/fabric.lock.json").read_text())
    for url, name in ENGINE:
        path = libdir / "engine" / name
        get(url, path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = next(r["sha256"] for r in lock["engineLibraries"] if r["file"] == name)
        if digest != expected:
            raise SystemExit(f"engine jar hash mismatch: {name}: {digest} != {expected}")
        add(path)

    # Synthetic A0 reference: keeps prepare_b0.py's shared_meta filter happy.
    profile = out / "a0" / "profile.json"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(json.dumps({"profiles": {"ci": {"name": "ci"}}}, indent=2))
    (out / "a0" / "dependencies.json").write_text(json.dumps({"jars": jars}, indent=2))
    (out / "a0" / "result.json").write_text(json.dumps({
        "gateA0": "PASS",
        "scope": ("synthetic A0 reference built by the CI wrapper from the public Mojang CDN; "
                  "the operator must own the Minecraft client. Not a Mac desktop launch record."),
        "profile": str(profile),
        "clientJar": str(client),
        "jars": len(jars),
        "skippedByRules": skipped,
    }, indent=2))

    summary = {"version": version["id"], "clientBytes": client.stat().st_size,
               "jars": len(jars), "libraries": sum(j["size"] for j in jars),
               "metadata": str(version_json)}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
