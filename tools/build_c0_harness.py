#!/usr/bin/env python3
"""Build the C0 iOS harness around a Native Image dylib, and optionally install it on a device.

The harness (`ios/C0Harness`) loads `client-graph.dylib` with dlopen, creates one Graal
isolate, and calls `run_main`. This tool does the surrounding work so a rebuild after a new
image is one command:

    python3 -B tools/build_c0_harness.py                       # archive + export IPA
    python3 -B tools/build_c0_harness.py --device <UDID> --install --launch
    python3 -B tools/build_c0_harness.py --device <UDID> --pull-logs artifacts/c0/harness/logs

It never invents success: the recorded status reflects what xcodebuild and devicectl
actually returned, and a missing/unregistered device is reported as such instead of being
retried silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "ios/C0Harness/C0Harness.xcodeproj"
SCHEME = "C0Harness"
BUNDLE_ID = "org.fabricaot.research.c0.kexin"
DEFAULT_DYLIB = ROOT / "artifacts/c0/client-link-02/client-graph.dylib"

def validate_shader_bundle(directory: Path,simulator: bool)->dict:
    if directory.is_symlink():raise ValueError("Shader bundle must not be a symlink")
    directory=directory.resolve(strict=True);report=json.loads((directory.parent/'result.json').read_text());index=directory/'index.json'
    if report.get('status')!='VANILLA_SHADERS_PRECOMPILED' or report.get('sdk')!=('iphonesimulator' if simulator else 'iphoneos') or sha256(index)!=report.get('indexSHA256'):
        raise ValueError("A verified shader bundle for the selected SDK is required")
    data=json.loads(index.read_text());files={'index.json':sha256(index)}
    if data.get('schema')!=1 or not data.get('programs'):raise ValueError("Invalid shader index")
    for entry in data['programs']:
        key=entry['key'];name=key+'.metallib'
        if not re.fullmatch('[0-9a-f]{64}',key) or name in files or entry.get('status')!='TRANSLATED':raise ValueError("Invalid or duplicate Metal program")
        path=directory/name
        if path.is_symlink() or sha256(path)!=entry['metallibSHA256']:raise ValueError("Shader library fingerprint changed: "+name)
        files[name]=entry['metallibSHA256']
    if any(p.is_symlink() for p in directory.rglob('*')) or {p.name for p in directory.iterdir()}!=set(files):raise ValueError("Unexpected shader bundle content")
    return {'path':str(directory),'filesSHA256':files,'programs':len(data['programs'])}
HARNESS_DIR = ROOT / "artifacts/c0/harness"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run(argv: list[str], *, timeout: int = 3600) -> dict:
    """Run a command and keep both streams; callers decide what counts as success."""
    completed = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    return {"argv": argv, "exitCode": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr}


def parse_platform(vtool_stdout: str, lipo_stdout: str) -> dict:
    """Turn `vtool -show-build` / `lipo -info` text into the two facts that matter here."""
    platform = re.search(r"platform\s+(\w+)", vtool_stdout)
    minimum = re.search(r"minos\s+([\d.]+)", vtool_stdout)
    return {"platform": platform.group(1) if platform else None,
            "minos": minimum.group(1) if minimum else None,
            "architectures": lipo_stdout.strip() or None}


def binary_platform(dylib: Path) -> dict:
    """Read the Mach-O build version so a macOS object can never be signed into an iOS app."""
    vtool = subprocess.run(["/usr/bin/xcrun", "vtool", "-show-build", str(dylib)],
                           capture_output=True, text=True)
    lipo = subprocess.run(["/usr/bin/lipo", "-info", str(dylib)], capture_output=True, text=True)
    return parse_platform(vtool.stdout, lipo.stdout)


def validate_dylib(dylib: Path, simulator: bool = False) -> dict:
    if not dylib.is_file():
        raise SystemExit(f"missing image dylib: {dylib}")
    facts = binary_platform(dylib)
    # A device binary is platform IOS, a simulator one is IOSSIMULATOR; mixing them makes dyld
    # refuse the load, so the expected value is checked against the requested run destination.
    expected = "IOSSIMULATOR" if simulator else "IOS"
    if facts["platform"] != expected:
        raise SystemExit(f"{dylib} targets platform {facts['platform']} but a {expected} binary is "
                         "required here; rebuild with tools/link_c0_ios.py for the matching --sdk")
    if "arm64" not in (facts["architectures"] or ""):
        raise SystemExit(f"{dylib} is not arm64 ({facts['architectures']})")
    facts.update({"path": str(dylib), "bytes": dylib.stat().st_size, "sha256": sha256(dylib)})
    return facts


def archive(dylib: Path, configuration: str, timeout: int, native_dir: Path | None = None) -> dict:
    path = HARNESS_DIR / "C0Harness.xcarchive"
    if path.exists():raise RuntimeError("Archive output exists; choose a new --output directory")
    outcome = run(["/usr/bin/xcodebuild", "-project", str(PROJECT), "-scheme", SCHEME,
                   "-configuration", configuration, "-destination", "generic/platform=iOS",
                   "-archivePath", str(path), f"FAOT_CLIENT_LIBRARY={dylib}",
                   f"FAOT_GRAPHICS_NATIVE_DIR={native_dir or ''}",
                   "-allowProvisioningUpdates", "archive"], timeout=timeout)
    outcome["archivePath"] = str(path)
    outcome["succeeded"] = outcome["exitCode"] == 0 and (path / "Info.plist").exists()
    return outcome


def export_archive(timeout: int) -> dict:
    out = HARNESS_DIR / "export"
    if out.exists():raise RuntimeError("Export output exists; choose a new --output directory")
    outcome = run(["/usr/bin/xcodebuild", "-exportArchive",
                   "-archivePath", str(HARNESS_DIR / "C0Harness.xcarchive"),
                   "-exportOptionsPlist", str(ROOT / "ios/C0Harness/ExportOptions.plist"),
                   "-exportPath", str(out), "-allowProvisioningUpdates"], timeout=timeout)
    ipas = sorted(out.glob("*.ipa")) if out.is_dir() else []
    outcome.update({"exportPath": str(out), "succeeded": outcome["exitCode"] == 0 and bool(ipas),
                    "ipa": str(ipas[0]) if ipas else None})
    if ipas:
        outcome["ipaBytes"] = ipas[0].stat().st_size
        outcome["ipaSHA256"] = sha256(ipas[0])
    return outcome


def parse_profile_devices(plist_text: str) -> list[str]:
    """Extract the UDIDs listed under ProvisionedDevices.

    An empty list is the normal result for a freshly created Team profile when the account has
    no registered devices; the IPA then exports fine but cannot be installed anywhere.
    """
    block = re.search(r"<key>ProvisionedDevices</key>\s*<array>(.*?)</array>", plist_text, re.S)
    if not block:
        return []
    # UDIDs appear as either 24 hex digits or 8+16 with a dash.
    return sorted(set(re.findall(r"<string>([0-9A-Fa-f]{16,40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16})</string>",
                                block.group(1))))


def provisioned_devices(archive_path: Path) -> list[str]:
    """Read the device list out of the profile embedded in the archived app."""
    profile = archive_path / "Products/Applications/C0Harness.app/embedded.mobileprovision"
    if not profile.is_file():
        return []
    decoded = run(["/usr/bin/security", "cms", "-D", "-i", str(profile)])
    if decoded["exitCode"] != 0:
        return []
    return parse_profile_devices(decoded["stdout"])


def install(ipa: Path, device: str, timeout: int) -> dict:
    outcome = run(["/usr/bin/xcrun", "devicectl", "device", "install", "app",
                   "--device", device, "--timeout", "120", str(ipa)], timeout=timeout)
    outcome["installed"] = outcome["exitCode"] == 0
    return outcome


def launch(device: str, timeout: int) -> dict:
    outcome = run(["/usr/bin/xcrun", "devicectl", "device", "process", "launch",
                   "--device", device, "--terminate-existing", "--timeout", "60", BUNDLE_ID],
                  timeout=timeout)
    outcome["launched"] = outcome["exitCode"] == 0
    return outcome


def pull_logs(device: str, destination: Path, timeout: int) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    outcome = run(["/usr/bin/xcrun", "devicectl", "device", "copy", "from",
                   "--device", device, "--domain-type", "appDataContainer",
                   "--domain-identifier", BUNDLE_ID, "--source", "Documents/c0-logs",
                   "--destination", str(destination), "--timeout", "120"], timeout=timeout)
    outcome["destination"] = str(destination)
    outcome["files"] = sorted(p.name for p in destination.rglob("*.log")) if destination.is_dir() else []
    return outcome


def build_for_simulator(dylib: Path, udid: str, configuration: str, timeout: int, native_dir: Path | None = None) -> dict:
    """Build an unsigned simulator app; nothing here needs a provisioning profile.

    A physical device has to be unlocked before a foreground app may start, which makes unattended
    iteration impossible. The simulator has no such gate and its container is a plain directory on
    this Mac, so a run log can be read the moment it is written.
    """
    derived = HARNESS_DIR / ("simulator-graphics-build" if native_dir else "simulator-build")
    if native_dir:derived=derived/native_dir.name
    # Not wiped: an existing derived-data tree makes this incremental, and the app bundle's
    # embedded dylib is re-copied by the build phase whenever FAOT_CLIENT_LIBRARY changes.
    derived.mkdir(parents=True, exist_ok=True)
    outcome = run(["/usr/bin/xcodebuild", "-project", str(PROJECT), "-scheme", SCHEME,
                   "-configuration", configuration, "-sdk", "iphonesimulator",
                   "-destination", f"platform=iOS Simulator,id={udid}",
                   "-derivedDataPath", str(derived),
                   f"FAOT_CLIENT_LIBRARY={dylib}",
                   f"FAOT_GRAPHICS_NATIVE_DIR={native_dir or ''}",
                   "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO", "build"], timeout=timeout)
    app = derived / "Build/Products" / f"{configuration}-iphonesimulator" / "C0Harness.app"
    outcome.update({"app": str(app), "succeeded": outcome["exitCode"] == 0 and app.is_dir()})
    return outcome


def simulator_install_and_launch(app: Path, udid: str, timeout: int) -> dict:
    installed = run(["/usr/bin/xcrun", "simctl", "install", udid, str(app)], timeout=timeout)
    installed["installed"] = installed["exitCode"] == 0
    launched = {"launched": False}
    if installed["installed"]:
        launched = run(["/usr/bin/xcrun", "simctl", "launch", "--terminate-running-process",
                        udid, BUNDLE_ID], timeout=timeout)
        launched["launched"] = launched["exitCode"] == 0
    return {"install": installed, "launch": launched}


def simulator_container(udid: str, timeout: int) -> Path | None:
    """Return the app's data container on the host so logs can be read without copying."""
    outcome = run(["/usr/bin/xcrun", "simctl", "get_app_container", udid, BUNDLE_ID, "data"],
                  timeout=timeout)
    path = outcome["stdout"].strip().splitlines()
    if outcome["exitCode"] != 0 or not path:
        return None
    return Path(path[-1])


def verify_simulator_embedded_libraries(app:Path,records:list[dict])->dict:
    verified={}
    for record in records:
        name=Path(record['path']).name;embedded=app/'Frameworks'/name
        if not embedded.is_file() or sha256(embedded)!=record['sha256']:
            raise ValueError('Simulator bundle is missing or changed native library: '+name)
        verified[name]=record['sha256']
    return verified


def main(argv=None) -> int:
    global HARNESS_DIR
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dylib", type=Path, default=DEFAULT_DYLIB,
                        help="arm64 iOS dylib produced by tools/link_c0_ios.py")
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    parser.add_argument("--device", help="device UDID from: xcrun devicectl list devices")
    parser.add_argument("--simulator", help="simulator UDID from: xcrun simctl list devices booted")
    parser.add_argument("--install", action="store_true", help="install the exported IPA")
    parser.add_argument("--launch", action="store_true", help="launch the app after installing")
    parser.add_argument("--pull-logs", type=Path, help="copy Documents/c0-logs off the device")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--output",type=Path,default=HARNESS_DIR,help="Dedicated harness output directory; existing device archives are preserved")
    parser.add_argument("--native-library",type=Path,action="append",default=[],help="Explicit iOS graphics dylib to validate and embed; repeat for libglfw/liblwjgl")
    parser.add_argument("--metal-library",type=Path,help="Precompiled fabricaot-present.metallib for this SDK")
    parser.add_argument("--shader-bundle",type=Path,help="Verified translate_shaders bundle directory for this SDK")
    args = parser.parse_args(argv)
    HARNESS_DIR=args.output.resolve()

    if (args.install or args.launch or args.pull_logs) and not args.device and not args.simulator:
        parser.error("--device is required with --install/--launch/--pull-logs unless --simulator is used")

    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    dylib = args.dylib.resolve()
    result: dict = {"status": "INCOMPLETE", "gateC0": "BLOCKED",
                    "scope": "host App that loads the C0 image; not a playable client",
                    "bundleID": BUNDLE_ID, "dylib": validate_dylib(dylib, bool(args.simulator))}
    native_dir=None
    if args.native_library:
        names=[path.name for path in args.native_library]
        if not {"libglfw.dylib","liblwjgl.dylib"}.issubset(names) or not set(names).issubset({"libglfw.dylib","liblwjgl.dylib","libfaot_metal.dylib","libopenal.dylib"}) or len(set(names))!=len(names):
            parser.error("Provide libglfw.dylib and liblwjgl.dylib, optionally libfaot_metal.dylib and libopenal.dylib")
        result["graphicsNativeLibraries"]=[validate_dylib(path.resolve(),bool(args.simulator)) for path in args.native_library]
        metal_library=None
        if args.metal_library:
            metal_library=args.metal_library.resolve(strict=True)
            if metal_library.name!="fabricaot-present.metallib" or not metal_library.is_file():parser.error("Expected fabricaot-present.metallib")
            result["metalShaderLibrary"]={"path":str(metal_library),"sha256":sha256(metal_library)}
        fingerprints=[f["sha256"] for f in result["graphicsNativeLibraries"]]
        if metal_library:fingerprints.append(result["metalShaderLibrary"]["sha256"])
        if args.shader_bundle:
            result['shaderBundle']=validate_shader_bundle(args.shader_bundle,bool(args.simulator));fingerprints.extend(result['shaderBundle']['filesSHA256'].values())
        identity=hashlib.sha256(''.join(sorted(fingerprints)).encode()).hexdigest()[:12]
        native_dir=HARNESS_DIR/(("native-simulator-" if args.simulator else "native-device-")+identity)
        native_dir.mkdir(exist_ok=True)
        for path in args.native_library:shutil.copy2(path,native_dir/path.name)
        if metal_library:shutil.copy2(metal_library,native_dir/metal_library.name)
        if args.shader_bundle:shutil.copytree(args.shader_bundle,native_dir/'fabricaot-shaders',dirs_exist_ok=True)
    elif args.metal_library or args.shader_bundle:parser.error("Shader libraries require explicit graphics native libraries")

    if args.simulator:
        built = build_for_simulator(dylib, args.simulator, args.configuration, args.timeout,native_dir)
        result["simulator"] = args.simulator
        result["build"] = {k: built[k] for k in ("argv", "exitCode", "succeeded", "app")}
        if not built["succeeded"]:
            result["status"] = "BUILD_FAILED"
            result["error"] = (built["stderr"] or built["stdout"]).strip().splitlines()[-8:]
            (HARNESS_DIR / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
            return 1
        result["status"] = "SIMULATOR_BUILT"
        result['embeddedNativeLibrariesSHA256']=verify_simulator_embedded_libraries(Path(built['app']),result.get('graphicsNativeLibraries',[]))
        if args.install or args.launch:
            result["simulatorRun"] = simulator_install_and_launch(Path(built["app"]),
                                                                 args.simulator, args.timeout)
            result["status"] = "SIMULATOR_LAUNCHED" if result["simulatorRun"]["launch"]["launched"] \
                else "SIMULATOR_INSTALL_FAILED"
        container = simulator_container(args.simulator, args.timeout)
        result["container"] = str(container) if container else None
        if args.pull_logs and container:
            target = args.pull_logs
            shutil.rmtree(target, ignore_errors=True)
            source = container / "Documents/c0-logs"
            if source.is_dir():
                shutil.copytree(source, target)
            result["logs"] = sorted(p.name for p in target.glob("*.log")) if target.is_dir() else []
        (HARNESS_DIR / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0 if result["status"] in ("SIMULATOR_BUILT", "SIMULATOR_LAUNCHED") else 1


    built = archive(dylib, args.configuration, args.timeout,native_dir)
    result["archive"] = {k: built[k] for k in ("argv", "exitCode", "succeeded", "archivePath")}
    if not built["succeeded"]:
        result["status"] = "ARCHIVE_FAILED"
        result["error"] = (built["stderr"] or built["stdout"]).strip().splitlines()[-8:]
        (HARNESS_DIR / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 1

    result["provisionedDevices"] = provisioned_devices(Path(built["archivePath"]))

    exported = export_archive(args.timeout)
    result["export"] = {k: exported[k] for k in ("exitCode", "succeeded", "ipa", "ipaBytes", "ipaSHA256")}
    if not exported["succeeded"]:
        result["status"] = "EXPORT_FAILED"
        result["error"] = (exported["stderr"] or exported["stdout"]).strip().splitlines()[-8:]
        (HARNESS_DIR / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 1
    result["status"] = "EXPORTED"

    if args.device:
        if args.device not in result["provisionedDevices"]:
            # Not a hard failure: the IPA is valid, it simply cannot be installed on that
            # device until Xcode registers it (plug in / unlock, then rebuild).
            result["deviceRegistered"] = False
            result["note"] = ("device is absent from the embedded profile; connect and unlock it, "
                              "then rebuild so Xcode can register it")
        else:
            result["deviceRegistered"] = True
        if args.install:
            installed = install(Path(exported["ipa"]), args.device, args.timeout)
            result["install"] = {"exitCode": installed["exitCode"], "installed": installed["installed"]}
            if not installed["installed"]:
                result["install"]["error"] = (installed["stderr"] or installed["stdout"]).strip().splitlines()[-8:]
            else:
                result["status"] = "INSTALLED"
        if args.launch:
            launched = launch(args.device, args.timeout)
            result["launch"] = {"exitCode": launched["exitCode"], "launched": launched["launched"]}
            if not launched["launched"]:
                result["launch"]["error"] = (launched["stderr"] or launched["stdout"]).strip().splitlines()[-8:]
        if args.pull_logs:
            logs = pull_logs(args.device, args.pull_logs.resolve(), args.timeout)
            result["logs"] = {"exitCode": logs["exitCode"], "destination": logs["destination"],
                              "files": logs["files"]}

    (HARNESS_DIR / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
