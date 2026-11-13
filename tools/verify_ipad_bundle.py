#!/usr/bin/env python3
"""Verify that a built .app or .ipa is a native iPad bundle.

This is deliberately independent of the Xcode build log. It reads the final
Info.plist and, when available, the Mach-O platform of the executable. The
WorldDevice build phase runs the same contract on the exact bundle it embeds.
"""
from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

EXPECTED_FAMILY = {1, 2}


def check_info(info: dict, *, processed: bool = False) -> list[str]:
    errors: list[str] = []
    family = info.get("UIDeviceFamily")
    if not isinstance(family, list) or {int(value) for value in family} != EXPECTED_FAMILY:
        errors.append(f"UIDeviceFamily must be [1, 2], got {family!r}")
    if info.get("UIRequiresFullScreen") is not True:
        errors.append("UIRequiresFullScreen must be true")
    if info.get("UIApplicationSupportsIndirectInputEvents") is not True:
        errors.append("UIApplicationSupportsIndirectInputEvents must be true")
    ipad_orientations = info.get("UISupportedInterfaceOrientations~ipad")
    if not isinstance(ipad_orientations, list) or not any(
        value in {"UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"}
        for value in ipad_orientations
    ):
        errors.append("UISupportedInterfaceOrientations~ipad must include a landscape orientation")
    if processed:
        platforms = info.get("CFBundleSupportedPlatforms")
        if not isinstance(platforms, list) or "iPhoneOS" not in platforms:
            errors.append(f"CFBundleSupportedPlatforms must contain iPhoneOS, got {platforms!r}")
    minimum = info.get("MinimumOSVersion")
    if processed and isinstance(minimum, str):
        try:
            if float(minimum.split(".")[0]) < 17:
                errors.append(f"MinimumOSVersion must be at least 17.0, got {minimum}")
        except ValueError:
            errors.append(f"MinimumOSVersion is not a version string: {minimum!r}")
    if not isinstance(info.get("CFBundleIdentifier"), str) or not info["CFBundleIdentifier"]:
        errors.append("CFBundleIdentifier is missing")
    return errors


def check_binary(executable: Path) -> list[str]:
    errors: list[str] = []
    if not executable.is_file():
        return [f"executable is missing: {executable}"]
    lipo = subprocess.run(["/usr/bin/xcrun", "lipo", "-info", str(executable)],
                          capture_output=True, text=True)
    if lipo.returncode != 0 or "arm64" not in lipo.stdout:
        errors.append(f"executable is not arm64: {lipo.stdout.strip() or lipo.stderr.strip()}")
    vtool = subprocess.run(["/usr/bin/xcrun", "vtool", "-show-build", str(executable)],
                           capture_output=True, text=True)
    if vtool.returncode != 0 or "platform IOS\n" not in vtool.stdout:
        errors.append(f"executable does not target the IOS platform: {vtool.stdout.strip() or vtool.stderr.strip()}")
    return errors


def load_app(app: Path, check_executable: bool = True) -> tuple[dict, list[str]]:
    info_path = app / "Info.plist"
    if not info_path.is_file():
        raise SystemExit(f"missing Info.plist: {info_path}")
    info = plistlib.loads(info_path.read_bytes())
    errors = check_info(info, processed=True)
    if check_executable:
        executable_name = info.get("CFBundleExecutable")
        if not isinstance(executable_name, str) or not executable_name:
            errors.append("CFBundleExecutable is missing")
        else:
            errors.extend(check_binary(app / executable_name))
    return info, errors


def app_from_ipa(ipa: Path, destination: Path) -> Path:
    with zipfile.ZipFile(ipa) as archive:
        names = [name for name in archive.namelist() if name.startswith("Payload/") and ".app/" in name]
        if not names:
            raise SystemExit(f"IPA has no Payload/*.app: {ipa}")
        archive.extractall(destination)
    apps = sorted((destination / "Payload").glob("*.app"))
    if len(apps) != 1:
        raise SystemExit(f"expected one app in IPA, found {len(apps)}")
    return apps[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--app", type=Path, help="Path to a built .app")
    source.add_argument("--ipa", type=Path, help="Path to an exported .ipa")
    parser.add_argument("--skip-binary", action="store_true",
                        help="Only validate Info.plist (for packaging fixtures)")
    parser.add_argument("--json", action="store_true", help="Print a JSON report")
    args = parser.parse_args(argv)
    if args.app:
        app = args.app.resolve(strict=True)
        temporary = None
    else:
        temporary = tempfile.TemporaryDirectory(prefix="mcfao-ipa-verify-")
        app = app_from_ipa(args.ipa.resolve(strict=True), Path(temporary.name))
    info, errors = load_app(app, check_executable=not args.skip_binary)
    report = {
        "status": "IPAD_BUNDLE_CONTRACT_FAIL" if errors else "IPAD_BUNDLE_CONTRACT_PASS",
        "app": str(app),
        "bundleID": info.get("CFBundleIdentifier"),
        "UIDeviceFamily": info.get("UIDeviceFamily"),
        "UIRequiresFullScreen": info.get("UIRequiresFullScreen"),
        "UIApplicationSupportsIndirectInputEvents": info.get(
            "UIApplicationSupportsIndirectInputEvents"
        ),
        "UISupportedInterfaceOrientations~ipad": info.get(
            "UISupportedInterfaceOrientations~ipad"
        ),
        "errors": errors,
    }
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    elif errors:
        print("\n".join(f"error: {error}" for error in errors), file=sys.stderr)
    else:
        print(
            "IPAD_BUNDLE_CONTRACT_PASS "
            f"bundle={report['bundleID']} family={report['UIDeviceFamily']} "
            f"fullScreen={report['UIRequiresFullScreen']}"
        )
    if temporary is not None:
        temporary.cleanup()
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
