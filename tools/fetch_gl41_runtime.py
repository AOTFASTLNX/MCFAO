#!/usr/bin/env python3
"""Build patched Mesa and fetch pinned MoltenVK for the experimental iOS GL41 renderer.

Mesa is built from hash-pinned upstream source with repository patches. MoltenVK comes
from an immutable Amethyst-iOS commit. Provenance, hashes and licenses accompany both.
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
from pathlib import Path

from capture import ROOT
from graphics_common import register_tree
from storage_config import cache_path
from verified_download import fetch
from build_gl41_mesa import build as build_mesa, patch_identity, digest, MESA, MVK_HEADERS

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
    # Share the bounded HTTPS transport, redirect allowlist and system CA roots
    # with the other desktop dependency downloads. TLS verification stays on.
    cached = cache_path('graphics/gl41-runtime').resolve() / destination.name
    fetch({'url': url, 'size': expected_bytes, 'sha256': expected_sha}, cached)
    if cached != destination.resolve():
        shutil.copyfile(cached, destination)
    return expected_sha


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


def validate_runtime(directory: Path, report: dict) -> None:
    """Reject historical unpatched runtimes and verify source-built Mesa provenance."""
    mesa = report.get("mesa", {})
    if mesa.get("patchIdentity") != patch_identity() or mesa.get("source") != MESA or mesa.get("headers") != MVK_HEADERS:
        raise ValueError("GL41 patched Mesa source provenance changed; rebuild runtime")
    hashes = report.get("filesSHA256", {})
    if hashes.get("libOSMesa.8.dylib") != mesa.get("sha256"):
        raise ValueError("GL41 Mesa binary differs from source build record")
    for entry in FILES:
        name = entry["name"]
        expected = mesa.get("sha256") if name == "libOSMesa.8.dylib" else entry["sha256"]
        if not expected or digest(directory / name) != expected:
            raise ValueError("GL41 runtime fingerprint changed: " + name)
        macho_platform(directory / name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    records = {}
    builds = {}
    mesa_dir = cache_path("graphics/gl41-mesa/" + patch_identity()).resolve()
    mesa_binary = build_mesa(mesa_dir)
    mesa_record = json.loads((mesa_dir / "result.json").read_text())
    shutil.copy2(mesa_dir / "LICENSE-Mesa.rst", out / "LICENSE-Mesa.rst")
    for entry in FILES:
        destination = out / entry["name"]
        if entry["name"] == "libOSMesa.8.dylib":
            shutil.copy2(mesa_binary, destination)
            file_digest = mesa_record["sha256"]
        else:
            file_digest = download(BASE + entry["name"], destination, entry["bytes"], entry["sha256"])
        platform, minimum, sdk = macho_platform(destination)
        builds[entry["name"]] = {"platform": platform, "minimum": f"{minimum >> 16}.{(minimum >> 8) & 0xff}", "sdk": f"{sdk >> 16}.{(sdk >> 8) & 0xff}"}
        records[entry["name"]] = file_digest
    license_bytes = download(APACHE[0], out / "LICENSE-Apache-2.0.txt", 11358, APACHE[1])
    notice = (
        "Native Craft Launcher experimental OpenGL 4.1 runtime\n\n"
        f"MoltenVK binary source: https://github.com/Taylen27/Amethyst-iOS\nCommit: {COMMIT}\n"
        f"Path: Natives/resources/Frameworks/\n\n"
        "libOSMesa.8.dylib: Mesa 3D Graphics Library, MIT License.\n"
        f"  Source: {MESA['url']}\n  SHA-256: {MESA['sha256']}\n"
        "  https://docs.mesa3d.org/license.html\n"
        "libMoltenVK.dylib: MoltenVK, Apache License 2.0.\n"
        "  https://github.com/KhronosGroup/MoltenVK/blob/main/LICENSE\n"
        "  Full Apache-2.0 text: LICENSE-Apache-2.0.txt\n\n"
        "Mesa is source-built with NCL checked readback and diagnostics patches. MoltenVK is hash-pinned.\n"
    )
    (out / "NOTICE.txt").write_text(notice)
    result = {"status": "GL41_RUNTIME_FETCHED",
              "scope": "source-built patched Mesa / pinned MoltenVK; device acceptance separate",
              "mesa": mesa_record,
              "provenance": {"repository": "https://github.com/Taylen27/Amethyst-iOS", "commit": COMMIT,
                             "files": [entry for entry in FILES if entry["name"] != "libOSMesa.8.dylib"],
                             "mesaSource": MESA},
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
