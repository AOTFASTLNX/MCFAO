#!/usr/bin/env python3
"""Collect local Gate A prerequisites. Never launch Minecraft or read account tokens."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT, capture
from locate_local_client import inspect_profile


def client_metadata(root: Path) -> dict:
    version_dir = root / "versions/26.1.2"
    metadata = version_dir / "26.1.2.json"
    jar = version_dir / "26.1.2.jar"
    result = {"versionMetadataPresent": metadata.is_file(), "clientJarPresent": jar.is_file(),
              "ownership": "NOT CHECKED", "fabricLaunch": "NOT RUN"}
    if metadata.is_file():
        if metadata.stat().st_size > 2 * 1024**2:
            raise ValueError("Client version metadata too large")
        data = json.loads(metadata.read_text())
        result.update(version=data.get("id"), javaVersion=data.get("javaVersion"),
                      libraryCount=len(data.get("libraries", [])), metadataSHA256=sha256(metadata))
    # No launcher_accounts.json, auth sessions, worlds, or user profiles are read.
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--swiftcraft-profile", type=Path)
    args = parser.parse_args(argv)
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    commands = {
        "os": ["sw_vers"], "jdk-inventory": ["/usr/libexec/java_home", "-V"],
        "xcode": ["xcodebuild", "-version"], "iphoneos-sdk": ["xcrun", "--sdk", "iphoneos", "--show-sdk-version"],
        "devices": ["xcrun", "devicectl", "list", "devices"],
    }
    steps = {name: capture(command, output / name, 45) for name, command in commands.items()}
    client = client_metadata(Path.home() / "Library/Application Support/minecraft")
    swiftcraft = None
    if args.swiftcraft_profile:
        swiftcraft = inspect_profile(args.swiftcraft_profile, Path.home() / "Library/Application Support/minecraft/versions/26.1.2/26.1.2.json")
    result = {"host": {"system": platform.system(), "machine": platform.machine()},
              "commands": steps, "localClient": client,
              "swiftCraftClient": swiftcraft,
              "gates": {"A0": "BLOCKED", "A1": "BLOCKED"},
              "reason": "Prerequisite inventory does not establish an authenticated Fabric desktop launch or an iPhone AOT run."}
    (output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
