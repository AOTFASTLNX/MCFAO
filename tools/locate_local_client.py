#!/usr/bin/env python3
"""Inspect an explicitly selected Swift Craft instance and its shared client.

Reads version metadata/JAR structure only. It never reads launcher databases,
accounts, logs or worlds, and does not execute the client or any Mod.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from bootstrap_toolchain import sha256


def inspect_profile(profile: Path, metadata_path: Path) -> dict:
    profile = profile.resolve()
    if not profile.is_dir() or profile.parent.name != "profiles":
        raise ValueError("Expected an existing Swift Craft Launcher profiles/<instance> directory")
    root = profile.parent.parent
    if metadata_path.stat().st_size > 2 * 1024**2:
        raise ValueError("Version metadata exceeds inspection budget")
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("id") != "26.1.2":
        raise ValueError("This project requires exact Minecraft 26.1.2 metadata")
    jar = root / "meta/versions/26.1.2/26.1.2.jar"
    expected = metadata.get("downloads", {}).get("client", {})
    result = {"profile": str(profile), "launcherRoot": str(root), "version": "26.1.2",
              "clientJar": str(jar), "clientJarPresent": jar.is_file(),
              "metadataPath": str(metadata_path.resolve()), "metadataSHA256": sha256(metadata_path),
              "javaVersion": metadata.get("javaVersion"), "assetIndex": metadata.get("assetIndex", {}).get("id"),
              "sharedLibraries": str(root / "meta/libraries"), "sharedAssets": str(root / "meta/assets"),
              "sharedNatives": str(root / "meta/natives"), "sharedRuntime": str(root / "runtime"),
              "declaredLibraries": len(metadata.get("libraries", [])),
              "ownership": "NOT CHECKED", "fabricLaunch": "NOT RUN", "gateA0": "BLOCKED"}
    if jar.is_file():
        if jar.stat().st_size > 1024**3:
            raise ValueError("Client JAR exceeds inspection budget")
        with jar.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha1").hexdigest()
        main = metadata.get("mainClass", "").replace(".", "/") + ".class"
        with zipfile.ZipFile(jar) as archive:
            main_present = main in archive.namelist()
        result.update(clientBytes=jar.stat().st_size, clientSHA1=digest, clientSHA256=sha256(jar),
                      expectedBytes=expected.get("size"), expectedSHA1=expected.get("sha1"),
                      containsMainClass=main_present,
                      matchesVersionMetadata=bool(expected.get("sha1") and digest == expected["sha1"]
                                                  and jar.stat().st_size == expected.get("size") and main_present))
    loader_root = root / "meta/libraries/net/fabricmc/fabric-loader"
    result["fabricLoaderVersions"] = sorted(p.name for p in loader_root.iterdir() if p.is_dir()) if loader_root.is_dir() else []
    mods = profile / "mods"
    result["profileModJarCount"] = sum(1 for p in mods.glob("*.jar") if p.is_file()) if mods.is_dir() else 0
    result["fabricApiFiles"] = sorted(p.name for p in mods.glob("fabric-api-*.jar")) if mods.is_dir() else []
    result["note"] = "Matching local version metadata does not verify ownership, Fabric startup, or iOS compatibility."
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--version-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = inspect_profile(args.profile, args.version_metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("matchesVersionMetadata") else 2


if __name__ == "__main__":
    raise SystemExit(main())
