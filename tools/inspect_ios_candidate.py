#!/usr/bin/env python3
"""Inspect a pinned iOS runtime ZIP as data, without loading or executing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

from bootstrap_toolchain import ROOT, sha256
from preflight import validate_zip_members


def archive_platforms(data: bytes) -> list[dict]:
    """Read ar members and Mach-O LC_BUILD_VERSION commands, never run tools."""
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("Not a Unix static library")
    offset = 8
    platforms = []
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:] != b"`\n":
            raise ValueError("Invalid ar header")
        size = int(header[48:58].strip())
        body = data[offset + 60:offset + 60 + size]
        if len(body) != size:
            raise ValueError("Truncated ar member")
        name = header[:16].decode("ascii").strip()
        if name.startswith("#1/"):
            name_size = int(name[3:])
            name = body[:name_size].decode("utf-8").rstrip("\x00")
            body = body[name_size:]
        if body[:4] == b"\xcf\xfa\xed\xfe":
            if len(body) < 32:
                raise ValueError("Truncated Mach-O header")
            cpu, subtype, kind, commands, command_bytes = struct.unpack_from("<IIIII", body, 4)
            pos = 32
            if pos + command_bytes > len(body):
                raise ValueError("Truncated Mach-O load commands")
            platform = None
            for _ in range(commands):
                command, length = struct.unpack_from("<II", body, pos)
                if length < 8 or pos + length > 32 + command_bytes:
                    raise ValueError("Invalid Mach-O load command")
                if command == 0x32:  # LC_BUILD_VERSION
                    platform = struct.unpack_from("<I", body, pos + 8)[0]
                elif command == 0x25:  # LC_VERSION_MIN_IPHONEOS
                    platform = 2
                pos += length
            platforms.append({"member": name, "cpu": hex(cpu), "platform": platform})
        elif not (name.startswith("__.SYMDEF") or name in ("/", "//")):
            raise ValueError(f"Unrecognized object format: {name}")
        offset += 60 + size + (size % 2)
    if not platforms:
        raise ValueError("No Mach-O objects in archive")
    return platforms


def inspect(path: Path, spec: dict) -> dict:
    if path.stat().st_size != spec["size"] or sha256(path) != spec["sha256"]:
        raise ValueError("Candidate outer archive hash/size mismatch")
    findings = []
    with zipfile.ZipFile(path) as archive:
        if not validate_zip_members(archive, findings, str(path)):
            raise ValueError(f"Unsafe candidate archive: {findings}")
        members = archive.infolist()
        if any(m.file_size > 16 * 1024**2 for m in members) or sum(m.file_size for m in members) > 64 * 1024**2:
            raise ValueError("Candidate inspection budget exceeded")
        contents = {m.filename: archive.read(m) for m in members if not m.is_dir()}
    manifest = json.loads(contents["manifest.json"])
    if (manifest.get("jdkVersion") != "25"
            or manifest.get("graalVmVersion") != spec["requiredGraalVM"]
            or manifest.get("labsOpenJdkCommit") != spec["jdkSourceCommit"]
            or manifest.get("graalCommit") != spec["graalSourceCommit"]):
        raise ValueError("Candidate manifest does not match locked source/version contract")
    checked = set()
    for line in contents["SHA256SUMS"].decode().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("Malformed inner checksum line")
        expected, name = match.groups()
        if name in checked or name not in contents:
            raise ValueError("Duplicate/missing checksummed input")
        if hashlib.sha256(contents[name]).hexdigest() != expected:
            raise ValueError(f"Inner checksum mismatch: {name}")
        checked.add(name)
    required = set(manifest["artifacts"]) | {manifest["capCacheIndex"]}
    if not required.issubset(checked) or set(contents) != checked | {"manifest.json", "SHA256SUMS"}:
        raise ValueError("Uncovered/missing archive contents")
    cap_index = contents[manifest["capCacheIndex"]].decode().splitlines()
    caps = sorted(name for name in contents if name.endswith(".cap"))
    if sorted("caps/" + name for name in cap_index) != caps:
        raise ValueError("CAP cache index differs from archive contents")
    libraries = {name: archive_platforms(contents[name]) for name in manifest["artifacts"] if name.endswith(".a")}
    for name, objects in libraries.items():
        if any(o["cpu"] != "0x100000c" or o["platform"] != 2 for o in objects):
            raise ValueError(f"Library is not exclusively arm64/iOS: {name}")
    return {"staticIntegrity": "PASS", "runtimeCompatibility": "UNKNOWN",
            "executionAllowed": False, "licenseStatus": spec["licenseStatus"],
            "sha256": spec["sha256"], "manifest": manifest, "capFiles": caps,
            "libraries": libraries, "gateA1": "BLOCKED",
            "note": "Static hashes/architectures do not prove correct runtime, licensing, or standalone iPhone execution."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    spec = json.loads((ROOT / "compiler/toolchains.lock.json").read_text())["iosCandidate"]
    result = inspect(ROOT / ".cache/toolchains" / spec["file"], spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
