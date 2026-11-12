#!/usr/bin/env python3
"""Package a completed device build into an unsigned IPA for later re-signing.

`tools/mcfao.py export-ipa` runs Xcode's `-exportArchive`, which needs a provisioning
profile and a developer certificate, so it can only produce an IPA that installs on the
machine's own team. This tool is the opposite: it takes the already-built `.app`, strips
its development signature (the `_CodeSignature` directory, `embedded.mobileprovision`,
and each Mach-O's LC_CODE_SIGNATURE), and writes the `Payload/` zip layout that every
sideloading tool accepts. The result contains no credentials and works with any signing
identity the user picks.

What it does not do: it never signs, never installs, and never claims the app runs. The
IPA is byte-for-byte the build's own binaries, so `docs/ACCEPTANCE.md` still requires a
real device run before anything is called playable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import zipfile
import sys

from capture import ROOT, capture
from mcfao import read_json, sha256, tree_files, write_json

TARGET = "ios-arm64"
STATUS = "SIGNED_DEVICE_APP"


def macho_files(app: Path) -> list[Path]:
    """Every Mach-O inside the bundle: the executable and its bundled dylibs."""
    found = []
    for item in sorted(app.rglob("*")):
        if not item.is_file():
            continue
        kind = subprocess.run(["/usr/bin/file", "-b", str(item)], check=True,
                              capture_output=True, text=True).stdout
        if "Mach-O" in kind:
            found.append(item)
    return found


def strip_signature(app: Path, logs: Path) -> list[str]:
    """Remove every trace of the development signature; return what was removed."""
    removed = []
    for name in ("_CodeSignature", "embedded.mobileprovision"):
        target = app / name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(name)
    for binary in macho_files(app):
        # `--remove-signature` is idempotent and leaves an unsigned Mach-O that any
        # signing tool can replace; without it a stale LC_CODE_SIGNATURE survives the
        # copy and re-signing tools report the bundle as already signed by another team.
        capture(["/usr/bin/codesign", "--remove-signature", str(binary)],
                logs / f"strip-{binary.name}", 120)
        removed.append(str(binary.relative_to(app)))
    return removed


def run(build: Path, output: Path) -> dict:
    build = build.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    manifest = read_json(build / "result.json")
    if manifest.get("status") != STATUS or manifest.get("target") != TARGET:
        raise ValueError(f"Expected a completed {TARGET} build, got {manifest.get('status')}"
                         f" for {manifest.get('target')}")
    app = (build / manifest["app"]).resolve(strict=True)
    if not app.is_dir() or build not in app.parents:
        raise ValueError(f"The build manifest points outside the build: {app}")
    if tree_files(app) != manifest["appFilesSHA256"]:
        raise ValueError(f"Packaged app content differs from the build manifest: {app}")

    output.mkdir(parents=True)
    logs = output / "logs"
    logs.mkdir()
    payload = output / "Payload"
    payload.mkdir()
    staged = payload / app.name
    capture(["/usr/bin/ditto", str(app), str(staged)], logs / "copy", 600)
    removed = strip_signature(staged, logs)

    ipa = output / f"{app.name.removesuffix('.app')}-unsigned.ipa"
    # --norsrc keeps AppleDouble `__MACOSX/._*` entries out of the archive; they are not
    # part of an IPA and some signing tools reject or duplicate them.
    capture(["/usr/bin/ditto", "-c", "-k", "--norsrc", "--keepParent",
             str(payload), str(ipa)], logs / "zip", 600)
    if not ipa.is_file() or ipa.stat().st_size == 0:
        raise RuntimeError(f"IPA was not written: {ipa}")
    with zipfile.ZipFile(ipa) as archive:
        junk = [name for name in archive.namelist() if name.startswith("__MACOSX")]
    if junk:
        raise RuntimeError(f"IPA carries resource-fork entries: {junk[:3]}")

    info = plistlib.loads((staged / "Info.plist").read_bytes())
    result = {
        "status": "UNSIGNED_IPA_EXPORTED",
        "ipa": str(ipa),
        "sha256": sha256(ipa),
        "bytes": ipa.stat().st_size,
        "build": str(build),
        "buildStatus": manifest["status"],
        "bundleIdentifier": info["CFBundleIdentifier"],
        "bundleVersion": info["CFBundleShortVersionString"],
        "buildNumber": info["CFBundleVersion"],
        "minimumOSVersion": info["MinimumOSVersion"],
        "signed": False,
        "removed": removed,
        "deviceRun": "NOT RUN",
        "created": datetime.now(timezone.utc).isoformat(),
    }
    write_json(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True,
                        help="Completed mcfao build directory (result.json present)")
    parser.add_argument("--output", type=Path, required=True,
                        help="New directory for the IPA and its manifest")
    args = parser.parse_args()
    result = run(args.build, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
