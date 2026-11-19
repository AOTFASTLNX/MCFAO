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
import sys

from capture import ROOT, capture
from mcfao import read_json, sha256, tree_files, write_json, write_payload_ipa
from mod_file_policy import content_paths, copy_content_file, local_build_temp

TARGET = "ios-arm64"
STATUS = "SIGNED_DEVICE_APP"


def macho_files(app: Path) -> list[Path]:
    """Every Mach-O inside the bundle: the executable and its bundled dylibs."""
    found = []
    for item in sorted(content_paths(app)):
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
        log = logs / f"strip-{binary.name}"
        result = capture(["/usr/bin/codesign", "--remove-signature", str(binary)], log, 120)
        if result["exitCode"] or result["timedOut"]:
            raise ValueError(f"Could not remove the Mach-O signature: {binary.name}. Logs: {log}")
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
    ipa = output / f"{app.name.removesuffix('.app')}-unsigned.ipa"
    with local_build_temp("mcfao-unsigned-ipa-") as scratch:
        staged = scratch / app.name
        for source in content_paths(app):
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Unexpected entry in the app payload: {source}")
            destination = staged / source.relative_to(app)
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy_content_file(source, destination)
        if tree_files(staged) != manifest["appFilesSHA256"]:
            raise ValueError("Staged app differs from the build manifest")
        removed = strip_signature(staged, logs)
        write_payload_ipa(staged, ipa)
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
