#!/usr/bin/env python3
"""Fetch the pinned iOS OpenGL 4.1 runtime used by the experimental renderer.

The two binaries come from the public Amethyst-iOS repository at an immutable commit. They are
not committed to this repository. Mesa is MIT-licensed and MoltenVK is Apache-2.0 licensed;
provenance, hashes and license links are recorded next to the downloaded files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import urllib.request
from pathlib import Path

from capture import ROOT
from graphics_common import register_tree

COMMIT = "54d20f9a7b22c8cadc026cbad8eb1a386a1e6efe"
BASE = f"https://raw.githubusercontent.com/Taylen27/Amethyst-iOS/{COMMIT}/Natives/resources/Frameworks/"
FILES = [
    {"name": "libOSMesa.8.dylib", "bytes": 17802296,
     "sha256": "081a4895a35fcb534ea34e19cca6b2093cd2b175791dfc1ab384dea0008ce369"},
    {"name": "libMoltenVK.dylib", "bytes": 4904816,
     "sha256": "e513ae03cde3e1a052cc51074665eeb1fab3c3b82b13bd8e00db7cf68e9e1037"},
]
APACHE = ("https://www.apache.org/licenses/LICENSE-2.0.txt",
          "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30")


def download(url: str, destination: Path, expected_bytes: int, expected_sha: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "FabricAOT-renderer/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        chunks = []
        remaining = expected_bytes + 1
        while remaining > 0:
            chunk = response.read(min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    if len(data) != expected_bytes:
        raise ValueError(f"size mismatch for {url}: {len(data)} != {expected_bytes}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha:
        raise ValueError(f"sha256 mismatch for {url}: {digest}")
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(destination)
    return digest


def macho_platform(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError("truncated Mach-O: " + path.name)
    magic, cpu, subtype, filetype, ncmds, size, flags, reserved = struct.unpack_from("<IiiIIIII", data, 0)
    if magic != 0xFEEDFACF or cpu != 0x0100000C or filetype != 6:
        raise ValueError("expected an arm64 dylib: " + path.name)
    offset = 32
    platform = minimum = None
    for _ in range(ncmds):
        command, length = struct.unpack_from("<II", data, offset)
        if length < 8 or offset + length > len(data):
            raise ValueError("invalid Mach-O load command: " + path.name)
        if command == 0x32 and length >= 24:
            platform, minimum, sdk, tools = struct.unpack_from("<IIII", data, offset + 8)
        offset += length
    if platform != 2 or minimum is None:
        raise ValueError("not an iOS binary: " + path.name)
    if minimum > 0x110000:
        raise ValueError(f"binary requires iOS newer than 17.0: {path.name} {minimum:#x}")
    return platform, minimum, sdk


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    records = {}
    builds = {}
    for entry in FILES:
        destination = out / entry["name"]
        digest = download(BASE + entry["name"], destination, entry["bytes"], entry["sha256"])
        platform, minimum, sdk = macho_platform(destination)
        builds[entry["name"]] = {"platform": platform, "minimum": f"{minimum >> 16}.{(minimum >> 8) & 0xff}", "sdk": f"{sdk >> 16}.{(sdk >> 8) & 0xff}"}
        records[entry["name"]] = digest
    license_bytes = download(APACHE[0], out / "LICENSE-Apache-2.0.txt", 11358, APACHE[1])
    notice = (
        "FabricAOT experimental OpenGL 4.1 runtime\n\n"
        f"Source repository: https://github.com/Taylen27/Amethyst-iOS\nCommit: {COMMIT}\n"
        f"Path: Natives/resources/Frameworks/\n\n"
        "libOSMesa.8.dylib: Mesa 3D Graphics Library, MIT License.\n"
        "  https://docs.mesa3d.org/license.html\n"
        "libMoltenVK.dylib: MoltenVK, Apache License 2.0.\n"
        "  https://github.com/KhronosGroup/MoltenVK/blob/main/LICENSE\n"
        "  Full Apache-2.0 text: LICENSE-Apache-2.0.txt\n\n"
        "These are prebuilt, hash-pinned runtime libraries; no source or game content is redistributed.\n"
    )
    (out / "NOTICE.txt").write_text(notice)
    result = {"status": "GL41_RUNTIME_FETCHED",
              "scope": "hash-pinned iOS OSMesa/MoltenVK binaries; no game execution or device acceptance",
              "provenance": {"repository": "https://github.com/Taylen27/Amethyst-iOS", "commit": COMMIT,
                             "files": FILES},
              "filesSHA256": {**records, "LICENSE-Apache-2.0.txt": license_bytes},
              "machO": builds,
              "licenses": {"Mesa": "MIT", "MoltenVK": "Apache-2.0"}}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    register_tree(out, [sys.executable, "-B", str(Path(__file__).resolve()),
                        *(sys.argv[1:] if argv is None else argv)])
    print(json.dumps({k: v for k, v in result.items() if k != "provenance"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
