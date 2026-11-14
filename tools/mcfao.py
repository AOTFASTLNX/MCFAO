"""Build and verify local MCFAO research packages."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
from uuid import uuid4

from bootstrap_toolchain import sha256
from build_c0_harness import binary_platform, validate_dylib, validate_shader_bundle
from capture import ROOT, capture
from graphics_common import bridge_overlays
from build_glfw_lite import exported_symbols, validate_input_exports
from prepare_fabric_aot import TOOL as FABRIC_TOOL, mod_files
from stage_game_assets import verified_assets

VERSION = "26.1.2"
TARGET = "ios-arm64"
# The Xcode project deliberately ships `DEVELOPMENT_TEAM = ""` so the repository carries no
# personal team identifier. `xcodebuild` normally resolves the team from the signed-in Xcode
# account, but that implicit resolution is not a build input: it disappeared between two
# otherwise identical builds and made packaging fail with "requires a development team".
# Resolve it explicitly from local assets instead (env override, then an installed profile
# that matches the app bundle identifier) and pass it on the command line.
BUNDLE_IDENTIFIER = "org.fabricaot.research.c0.kexin"
PROFILE_DIRECTORIES = (
    "~/Library/Developer/Xcode/UserData/Provisioning Profiles",
    "~/Library/MobileDevice/Provisioning Profiles",
)
TEAM_ENVIRONMENT = "MCFAO_DEVELOPMENT_TEAM"
CONFIG_PATHS = (
    "prepared", "caps", "bootstrapRuntime", "splitter", "versionMetadata",
    "assets", "glfw", "lwjgl", "metal", "openal", "shaders", "b1Evidence",
)
OPTIONAL_CONFIG_PATHS = {"openjdkSource", "graalSource"}
BACKEND_TOOLS = (
    "split_methods", "build_method_splitter", "inject_metal_backend", "probe_client_graph",
    "build_ios_runtime", "link_c0_ios", "stage_device_xcode", "graphics_common",
    "stage_game_assets", "run_b0_reference", "capture", "inspect_ios_candidate",
    "build_c0_harness", "client_graph_diagnostics", "lwjgl_codegen",
    "config_reflection",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict):
    pending = path.with_name(f".{path.name}.{uuid4().hex}")
    pending.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    pending.replace(path)


def command(*argv) -> str:
    return subprocess.run(list(map(str, argv)), check=True, capture_output=True,
                          text=True, timeout=60).stdout.strip()


def tree_files(directory: Path) -> dict:
    files = {}
    for item in sorted(directory.rglob("*")):
        if item.is_symlink():
            raise ValueError(f"Unexpected symbolic link in build input or output: {item}")
        if item.is_file():
            files[str(item.relative_to(directory))] = sha256(item)
    return files


def toolchain(home: Path) -> dict:
    native_image = command(home / "bin/native-image", "--version")
    if platform.machine() != "arm64" or "GraalVM CE 25.0.2" not in native_image:
        raise ValueError("Apple Silicon and GraalVM CE 25.0.2 are required")
    return {
        "host": command("/usr/bin/sw_vers"),
        "python": sys.version,
        "java": command(home / "bin/java", "--version"),
        "nativeImage": native_image,
        "xcode": command("/usr/bin/xcodebuild", "-version"),
        "clang": command("/usr/bin/xcrun", "--sdk", "iphoneos", "clang", "--version"),
        "sdk": command("/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-version"),
        "sdkPath": command("/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-path"),
        "hostSDKPath": command("/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"),
    }


def load_config(path: Path) -> dict:
    config = read_json(path)
    if not set(CONFIG_PATHS) <= config.keys() or config.keys() - set(CONFIG_PATHS) - OPTIONAL_CONFIG_PATHS:
        raise ValueError("Config requires " + ", ".join(CONFIG_PATHS) + ". Optional paths are openjdkSource and graalSource.")
    return {name: (path.parent / Path(value).expanduser()).resolve(strict=True)
            for name, value in config.items()}


def runtime_sources(config):
    paths = {}
    for tool, name in (("jdk", "openjdkSource"), ("graal", "graalSource")):
        if name in config:
            paths[tool] = config[name]
        else:
            descriptor = ROOT / ".cache/upstream" / f"{tool}.json"
            paths[tool] = Path(read_json(descriptor)["path"]).resolve(strict=True)
    return paths


def asset_files(assets: Path, metadata: Path) -> dict:
    _, index, objects = verified_assets(assets, read_json(metadata))
    expected = {str(index.relative_to(assets)), *map(str, objects)}
    actual = tree_files(assets)
    if actual.keys() != expected:
        raise ValueError(f"Asset directory must contain only the indexed asset set: {assets}")
    return actual


def inputs(config: dict) -> tuple[dict, Path, list[Path]]:
    prepared = read_json(config["prepared"] / "result.json")
    if prepared["status"] != "PREPARED":
        raise ValueError("Expected a verified PREPARED client reference")
    home = Path(prepared["javaHome"]).resolve(strict=True)
    metadata = read_json(config["versionMetadata"])
    libraries = [Path(row["path"]) for row in prepared["referenceLibraries"]]
    fingerprints = {}

    def add(path: Path, expected=None):
        path = path.resolve(strict=True)
        digest = sha256(path)
        if expected is not None and digest != expected:
            raise ValueError(f"Input hash changed: {path}")
        fingerprints[str(path)] = digest

    for row in prepared["referenceLibraries"] + prepared["engineLibraries"]:
        add(Path(row["path"]), row["sha256"])
    clients = [p for p in libraries if p.name == f"{VERSION}.jar" and p.parent.name == VERSION]
    if len(clients) != 1 or metadata["id"] != VERSION:
        raise ValueError(f"Expected exactly one Minecraft {VERSION} client")
    with clients[0].open("rb") as stream:
        if hashlib.file_digest(stream, "sha1").hexdigest() != metadata["downloads"]["client"]["sha1"]:
            raise ValueError(f"Client hash differs from version metadata: {clients[0]}")
    add(home / "bin/java", prepared["javaSHA256"])
    for file in (home / "release", home / "bin/javac", home / "bin/native-image",
                 home / "lib/modules", home / "lib/libjava.dylib",
                 home / "lib/server/libjvm.dylib"):
        add(file)
    for file in sorted((home / "lib/svm").rglob("*")):
        if file.is_file():
            add(file)
    for file in sorted((home / "include").rglob("*.h")):
        add(file)
    for name in ("result.json", "driver.jar"):
        add(config["prepared"] / name, prepared["binaries"][name]["sha256"] if name == "driver.jar" else None)
    for name in ("versionMetadata", "b1Evidence"):
        add(config[name])
    # Existing graphics builds are immutable inputs. Their report checks and the target
    # checks are repeated by the packaging step.
    for name in ("caps", "glfw", "lwjgl", "metal", "openal", "shaders"):
        directory = config[name]
        selected = {"glfw": ["libglfw.dylib"], "lwjgl": ["liblwjgl.dylib"],
                    "metal": ["libfaot_metal.dylib", "metal-backend.jar", "fabricaot-present.metallib"],
                    "openal": ["libopenal.dylib"], "shaders": []}
        if name == "caps":
            files = tree_files(directory)
        else:
            files = {"result.json": sha256(directory / "result.json")}
            for filename in selected[name]:
                files[filename] = sha256(directory / filename)
            if name == "lwjgl":
                files.update({p.name: sha256(p) for p in directory.glob("*-ios.jar")})
            if name == "shaders":
                files.update({f"bundle/{p}": h for p, h in tree_files(directory / "bundle").items()})
        fingerprints.update({str(directory / p): h for p, h in files.items()})
    bridge_overlays(config["lwjgl"])
    # A valid historical report can still predate a required Mod input API.
    # Inspect the actual binary and bind the Java overlays to that GLFW input.
    glfw_binary = config["glfw"] / "libglfw.dylib"
    validate_input_exports(exported_symbols(subprocess.check_output(
        ["xcrun", "nm", "-gUj", str(glfw_binary)], text=True)))
    if read_json(config["lwjgl"] / "result.json").get("glfwLibrarySHA256") != sha256(glfw_binary):
        raise ValueError("LWJGL overlays were generated against another GLFW library; rebuild LWJGL")
    validate_shader_bundle(config["shaders"] / "bundle", simulator=False)
    for key, filename, status in (
        ("glfw", "libglfw.dylib", "NATIVE_SUBSET_BUILT"),
        ("lwjgl", "liblwjgl.dylib", "STATIC_JNI_BRIDGE_BUILT"),
        ("metal", "libfaot_metal.dylib", "METAL_BOOTSTRAP_BUILT"),
        ("openal", "libopenal.dylib", "OPENAL_SOFT_BUILT"),
    ):
        report = read_json(config[key] / "result.json")
        if (report["status"] != status
                or validate_dylib(config[key] / filename)["sha256"] != report["binarySHA256"]):
            raise ValueError(f"Invalid graphics input: {config[key] / filename}")
    runtime = config["bootstrapRuntime"]
    add(runtime / "result.json")
    for row in read_json(runtime / "result.json")["archives"].values():
        archive = Path(row["path"])
        if archive.resolve().parent != runtime:
            raise ValueError(f"Runtime archive is outside its declared directory: {archive}")
        add(archive, row["sha256"])
    splitter = config["splitter"]
    add(splitter / "result.json")
    split = read_json(splitter / "result.json")
    add(Path(split["source"]), split["sourceSHA256"])
    if Path(split["javaHome"]).resolve() != home or Path(split["classesDirectory"]).resolve() != splitter / "classes":
        raise ValueError("Splitter must use the selected JDK and its own classes directory")
    for row in split["asmJars"]:
        add(Path(row["path"]), row["sha256"])
    for relative, digest in tree_files(splitter / "classes").items():
        fingerprints[str(splitter / "classes" / relative)] = digest

    for name in BACKEND_TOOLS:
        add(ROOT / "tools" / f"{name}.py")
    for directory in ("compiler", "ios/C0Harness"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "build" not in path.parts and "xcuserdata" not in path.parts and path.name != ".DS_Store":
                add(path)
    sources = runtime_sources(config)
    for name, source in sources.items():
        roots = {
            "jdk": ("src/java.base", "src/jdk.net", "src/hotspot/share/include",
                    "src/hotspot/os/posix/include", "build/fabricaot-host/support/headers/java.base",
                    "build/fabricaot-host/jdk/include"),
            "graal": ("substratevm/src/com.oracle.svm.native.jvm.posix",
                      "substratevm/src/com.oracle.svm.native.darwin",
                      "substratevm/src/com.oracle.svm.native.libchelper"),
        }
        for relative in roots[name]:
            for file in sorted((source / relative).rglob("*")):
                if file.is_file():
                    add(file)
    return {
        "schema": 1, "version": VERSION, "loader": "vanilla", "mappingNamespace": "official",
        "target": TARGET, "config": {key: str(p) for key, p in config.items()},
        "toolchain": toolchain(home), "filesSHA256": fingerprints,
        "runtimeSources": {key: str(path) for key, path in sources.items()},
        "assetsSHA256": asset_files(config["assets"], config["versionMetadata"]),
    }, clients[0], libraries


class Build:
    def __init__(self, root: Path, key: str):
        self.root = root
        self.key = key

    def step(self, name, argv, *, timeout=600, outputs=lambda path: path / "product"):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        checkpoint = folder / "checkpoint.json"
        command_args = list(map(str, argv))
        if checkpoint.is_file():
            old = read_json(checkpoint)
            product = outputs(folder / old["attempt"])
            if (old["key"] == self.key and old["argv"] == command_args
                    and product.is_dir() and tree_files(product) == old["filesSHA256"]):
                print(f"{name}: reused verified {product}", flush=True)
                return product
        attempt = folder / uuid4().hex
        attempt.mkdir()
        product = outputs(attempt)
        cmd = [arg.replace("{product}", str(attempt / "product")) for arg in command_args]
        print(f"{name}: {attempt / 'command'}", flush=True)
        log = attempt / "command"
        result = capture(cmd, log, timeout)
        if result["exitCode"] != 0 or result["timedOut"]:
            tail = (log / "stderr.log").read_text(errors="replace").splitlines()[-8:]
            tail += (log / "stdout.log").read_text(errors="replace").splitlines()[-8:]
            raise RuntimeError(f"{name} failed (exit {result['exitCode']}, timeout={result['timedOut']}). "
                               f"Logs: {log}\n" + "\n".join(tail))
        if not product.is_dir():
            raise RuntimeError(f"{name} did not produce {product}. Logs: {log}")
        write_json(checkpoint, {"key": self.key, "argv": command_args, "attempt": attempt.name,
                                "filesSHA256": tree_files(product)})
        return product


def script(name, *args):
    return [sys.executable, "-B", ROOT / "tools" / f"{name}.py", *args]


def loader_client(pipeline, args, config, client, inputs):
    if args.loader == "vanilla":
        return client, None
    # Every incompatible class makes the driver run Knot again without the offending Mod, so a
    # pack whose exclusions are only discovered by the class audit needs two full passes. pack-70
    # needed ~4 min + ~6 min and was killed by the old 10-minute default right after writing its
    # final client.jar; the budget now covers two Knot passes with headroom.
    prepared = pipeline.step("fabric", script(
        "prepare_fabric_aot", "--prepared", config["prepared"], "--client", client,
        "--mods", args.mods.resolve(), "--output", "{product}",
        "--audited-mods" if args.audited_mods else "--inspect"), timeout=1800)
    report = prepared / "result.json"
    facts = read_json(report)
    if facts["modSHA256"] != inputs["modsSHA256"]:
        raise ValueError(f"Mod JARs changed after input resolution: {report}")
    if args.prepare_only:
        return client, report
    jar = prepared / "client.jar"
    if facts["status"] != "FABRIC_AOT_INPUT_PREPARED" or sha256(jar) != facts["outputJarSHA256"]:
        raise ValueError(f"Fabric preparation did not yield a verified AOT input: {report}")
    return jar, report


def app_facts(app: Path, requested_device: str | None, logs: Path) -> dict:
    info = plistlib.loads((app / "Info.plist").read_bytes())
    executable = app / info["CFBundleExecutable"]
    facts = binary_platform(executable)
    if facts["platform"] != "IOS" or command("/usr/bin/lipo", "-archs", executable) != "arm64":
        raise ValueError(f"Expected an arm64 iPhoneOS executable: {facts}")
    libraries = [validate_dylib(path) for path in sorted((app / "Frameworks").glob("*.dylib"))]
    if {Path(row["path"]).name for row in libraries} != {
        "client-graph.dylib", "libglfw.dylib", "liblwjgl.dylib", "libopenal.dylib", "libfaot_metal.dylib",
    }:
        raise ValueError("Expected the game and all four device graphics/audio libraries")
    for library in libraries:
        if command("/usr/bin/lipo", "-archs", library["path"]) != "arm64":
            raise ValueError(f"Expected a single arm64 slice: {library['path']}")
    abi = {"_run_main", "_graal_create_isolate", "_graal_tear_down_isolate"}
    symbols = command("/usr/bin/xcrun", "nm", "-gUj", app / "Frameworks/client-graph.dylib")
    if abi - set(symbols.splitlines()):
        raise ValueError("Packaged image is missing the Native Image entry/isolate ABI")
    codesign = capture(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
                       logs / "codesign", 60)
    if codesign["exitCode"] or codesign["timedOut"]:
        raise ValueError(f"Signature verification failed. Logs: {logs / 'codesign'}")
    signed = command("/usr/bin/codesign", "-d", "--entitlements", "-", app)
    forbidden = {"com.apple.security.cs.allow-jit", "com.apple.security.cs.allow-unsigned-executable-memory",
                 "dynamic-codesigning", "com.apple.private.cs.allow-jit"}
    if signed.startswith("[Dict]"):
        if any(re.search(r"(?m)^\s*\[Key\] " + re.escape(key) + r"$", signed) for key in forbidden):
            raise ValueError("Unexpected dynamic code entitlement")
        match = re.search(r"(?m)^\s*\[Key\] application-identifier\n\s*\[Value\]\n\s*\[String\] (\S+)$", signed)
        identifier = match[1] if match else None
    else:
        entitlements = plistlib.loads(signed.encode())
        if forbidden & entitlements.keys():
            raise ValueError("Unexpected dynamic code entitlement")
        identifier = entitlements.get("application-identifier")
    profile = plistlib.loads(command("/usr/bin/security", "cms", "-D", "-i",
                                     app / "embedded.mobileprovision").encode())
    expiration = profile["ExpirationDate"].replace(tzinfo=timezone.utc)
    devices = profile.get("ProvisionedDevices", [])
    if expiration <= datetime.now(timezone.utc) or not devices:
        raise ValueError("Provisioning profile expired or has no registered devices")
    if requested_device and requested_device.casefold() not in {d.casefold() for d in devices}:
        raise ValueError("Requested device is absent from the embedded provisioning profile")
    profile_id = profile["Entitlements"]["application-identifier"]
    if (not identifier or not identifier.endswith("." + info["CFBundleIdentifier"])
            or (profile_id != identifier and not (profile_id.endswith(".*") and identifier.startswith(profile_id[:-1])))):
        raise ValueError("Signed application identifier does not match provisioning profile")
    return {"executable": facts, "libraries": libraries, "bundleID": info["CFBundleIdentifier"],
            "profileExpiresUTC": expiration.isoformat(), "provisionedDeviceCount": len(devices),
            "requestedDeviceCovered": True if requested_device else None,
            "dynamicCodeEntitlements": "ABSENT", "imageExports": sorted(abi), "deviceRun": "NOT RUN"}


def validate_package(app, staged, asset_hashes):
    frameworks = app / "Frameworks"
    present = "fabricaot-present.metallib"
    if sha256(frameworks / present) != sha256(staged / present):
        raise ValueError(f"Packaged resource changed: {present}")
    if tree_files(frameworks / "fabricaot-shaders") != tree_files(staged / "fabricaot-shaders"):
        raise ValueError("Packaged shader bundle changed")
    if tree_files(app / "assets") != asset_hashes:
        raise ValueError("Packaged game assets changed")
    # Codesign modifies dylib bytes. Compare the Mach-O UUIDs to establish provenance.
    for library in staged.glob("*.dylib"):
        packaged = frameworks / library.name
        before = command("/usr/bin/xcrun", "dwarfdump", "--uuid", library).split()[:3]
        after = command("/usr/bin/xcrun", "dwarfdump", "--uuid", packaged).split()[:3]
        if len(before) != 3 or before != after:
            raise ValueError(f"Embedded image UUID differs: {library.name}")


def read_provisioning_profile(path: Path) -> dict | None:
    """Decode a `.mobileprovision` CMS blob into the few facts packaging needs."""
    try:
        decoded = subprocess.run(["/usr/bin/security", "cms", "-D", "-i", str(path)],
                                 check=True, capture_output=True, timeout=60).stdout
        payload = plistlib.loads(decoded)
    except (subprocess.SubprocessError, plistlib.InvalidFileException, ValueError, OSError):
        return None
    entitlements = payload.get("Entitlements") or {}
    identifier = str(entitlements.get("application-identifier", ""))
    teams = payload.get("TeamIdentifier") or []
    if not identifier or not teams:
        return None
    return {
        "name": str(payload.get("Name", path.name)),
        "team": str(teams[0]),
        "application": identifier.split(".", 1)[1] if "." in identifier else identifier,
        "expires": payload.get("ExpirationDate"),
    }


def installed_provisioning_profiles(directories=PROFILE_DIRECTORIES) -> list:
    profiles = []
    for directory in directories:
        for path in sorted(Path(directory).expanduser().glob("*.mobileprovision")):
            profile = read_provisioning_profile(path)
            if profile:
                profiles.append(profile)
    return profiles


def select_development_team(profiles, bundle_identifier: str, now: datetime) -> str | None:
    """Pick the team whose installed profile actually covers this bundle identifier."""
    usable = [
        profile for profile in profiles
        if profile.get("team")
        and profile.get("application") in (bundle_identifier, "*")
        and (profile.get("expires") is None
             or profile["expires"].replace(tzinfo=timezone.utc) > now)
    ]
    if not usable:
        return None
    usable.sort(key=lambda profile: (profile["expires"] or datetime.min.replace(tzinfo=timezone.utc),
                                     profile["team"], profile["name"]))
    return usable[-1]["team"]


def resolve_development_team(bundle_identifier: str = BUNDLE_IDENTIFIER,
                             profiles=None) -> str:
    """Resolve the signing team without relying on Xcode's implicit account state."""
    override = os.environ.get(TEAM_ENVIRONMENT, "").strip()
    if override:
        if not re.fullmatch(r"[A-Z0-9]{10}", override):
            raise ValueError(f"{TEAM_ENVIRONMENT} must be a 10-character Apple team identifier")
        return override
    source = installed_provisioning_profiles() if profiles is None else profiles
    team = select_development_team(source, bundle_identifier, datetime.now(timezone.utc))
    if not team:
        raise ValueError(
            f"No installed provisioning profile covers {bundle_identifier}. Sign in to Xcode and "
            f"install a development profile, or set {TEAM_ENVIRONMENT} to your team identifier.")
    return team


def device_xcode(staged: Path, assets: Path, team: str | None = None) -> list:
    team = resolve_development_team() if team is None else team
    return [
        "/usr/bin/xcodebuild", "-project", ROOT / "ios/C0Harness/C0Harness.xcodeproj",
        "-scheme", "WorldDevice", "-destination", "generic/platform=iOS",
        f"FAOT_GRAPHICS_NATIVE_DIR={staged}", f"FAOT_CLIENT_LIBRARY={staged / 'client-graph.dylib'}",
        f"FAOT_GAME_ASSETS_DIR={assets}", f"DEVELOPMENT_TEAM={team}",
    ]


def verify(output: Path, device: str | None) -> dict:
    report = read_json(output / "result.json")
    if report["target"] != TARGET or report["status"] != "SIGNED_DEVICE_APP":
        raise ValueError("No completed iPhoneOS app manifest")
    if sha256(output / "inputs.json") != report["inputsSHA256"]:
        raise ValueError("Build input manifest changed")
    for key in ("aotCommand", "linkReport"):
        path = Path(report[key]).resolve(strict=True)
        if not path.is_relative_to(output) or (report.get(key + "SHA256") and sha256(path) != report[key + "SHA256"]):
            raise ValueError(f"Build evidence changed: {key}")
    flags = read_json(Path(report["aotCommand"]))["argv"]
    if "--no-fallback" not in flags or "-H:+ExitAfterRelocatableImageWrite" not in flags:
        raise ValueError("Missing no-fallback relocatable AOT build evidence")
    if read_json(Path(report["linkReport"]))["target"] != "arm64-apple-ios17.0":
        raise ValueError("Incorrect native link target")
    app = output / report["app"]
    if not app.resolve().is_relative_to(output) or tree_files(app) != report["appFilesSHA256"]:
        raise ValueError(f"Packaged app content differs from the build manifest: {app}")
    logs = output / "verify" / uuid4().hex
    return app_facts(app, device, logs)


def export_ipa(args) -> dict:
    build = args.build.resolve(strict=True)
    output = args.output.resolve()
    options = args.export_options.resolve(strict=True)
    if plistlib.loads(options.read_bytes()).get("method") != "debugging":
        raise ValueError("A local development export plist with method=debugging is required")
    manifest = read_json(build / "result.json")
    if manifest["target"] != TARGET or manifest["status"] != "SIGNED_DEVICE_APP":
        raise ValueError("Expected a completed iPhoneOS build")
    inputs = build / "inputs.json"
    if sha256(inputs) != manifest["inputsSHA256"]:
        raise ValueError("Build input manifest changed")
    evidence = read_json(inputs)
    assets = Path(evidence["config"]["assets"])
    if tree_files(assets) != evidence["assetsSHA256"]:
        raise ValueError("Game assets changed since the build")
    stage = build / "stage"
    checkpoint = read_json(stage / "checkpoint.json")
    staged = (stage / checkpoint["attempt"] / "product").resolve(strict=True)
    if (checkpoint["key"] != manifest["buildKey"] or not staged.is_relative_to(stage)
            or tree_files(staged) != checkpoint["filesSHA256"]):
        raise ValueError("Staged iPhone build inputs changed")
    output.mkdir(parents=True, exist_ok=False)

    def step(name, argv, timeout=300):
        log = output / name
        print(f"{name}: {log}", flush=True)
        result = capture(list(map(str, argv)), log, timeout)
        if result["exitCode"] or result["timedOut"]:
            raise RuntimeError(f"{name} failed. Logs: {log}")

    archive = output / "WorldDevice.xcarchive"
    step("archive", [*device_xcode(staged, assets), "-derivedDataPath", output / "DerivedData",
                     "-archivePath", archive, "archive"])
    step("export-log", ["/usr/bin/xcodebuild", "-exportArchive", "-archivePath", archive,
                        "-exportOptionsPlist", options, "-exportPath", output / "export"])
    ipas = list((output / "export").glob("*.ipa"))
    if len(ipas) != 1:
        raise ValueError(f"Expected one exported IPA: {output / 'export'}")
    ipa = ipas[0]
    unpacked = output / "unpacked"
    step("unpack", ["/usr/bin/ditto", "-x", "-k", ipa, unpacked])
    apps = list((unpacked / "Payload").glob("*.app"))
    if len(apps) != 1:
        raise ValueError("Expected one exported iPhoneOS app")
    validate_package(apps[0], staged, evidence["assetsSHA256"])
    result = {"status": "DEVELOPMENT_IPA_VERIFIED", "target": TARGET, "ipa": str(ipa),
              "sha256": sha256(ipa), "bytes": ipa.stat().st_size, "build": str(build),
              "exportOptionsSHA256": sha256(options),
              "verification": app_facts(apps[0], args.device, output / "verify")}
    write_json(output / "result.json", result)
    return result


def build(args, config):
    output = args.output.resolve()
    if output.is_dir() and any(output.iterdir()) and not (
            (output / "inputs.json").is_file() or {p.name for p in output.iterdir()} == {".lock"}):
        raise ValueError(f"Use a new output directory or an MCFAO build workspace: {output}")
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (output / "result.json").exists():
            raise ValueError("Completed build is immutable. Use verify or select a new output.")
        manifest, client, libraries = inputs(config)
        manifest["loader"] = args.loader
        if args.loader == "fabric":
            lock = read_json(ROOT / "compiler/fabric.lock.json")
            manifest["fabricLoaderVersion"] = lock["fabricLoader"]
            manifest["modsSHA256"] = {str(p): sha256(p) for p in mod_files(args.mods.resolve())}
            manifest["auditedMods"] = args.audited_mods
            manifest["prepareOnly"] = args.prepare_only
            manifest["filesSHA256"].update({str(p): sha256(p) for p in (
                ROOT / "tools/prepare_fabric_aot.py", ROOT / "tools/prepare_b0.py",
                *FABRIC_TOOL.rglob("*.java"),
            )})
        manifest["requestedDevice"] = args.device
        key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        saved = output / "inputs.json"
        if saved.exists() and read_json(saved) != manifest:
            raise ValueError(f"Build inputs changed. Use a new output. Previous inputs: {saved}")
        if not saved.exists():
            write_json(saved, manifest)
        pipeline = Build(output, key)
        client, loader_report = loader_client(pipeline, args, config, client, manifest)
        if args.prepare_only:
            return loader_report
        split = pipeline.step("split", script(
            "split_methods", "--jar", client, "--output-jar", "{product}/client.jar",
            "--report", "{product}/split-report.json", "--tool", config["splitter"],
            "--classpath", *libraries))
        home = Path(read_json(config["prepared"] / "result.json")["javaHome"])
        asm = [row["path"] for row in read_json(config["splitter"] / "result.json")["asmJars"]
               if row["name"] in {"asm-9.9.jar", "asm-tree-9.9.jar"}]
        injected = pipeline.step("metal-injection", script(
            "inject_metal_backend", "--client", split / "client.jar", "--output", "{product}",
            "--graalvm-home", home, "--asm-jars", *asm))
        aot = pipeline.step("aot", script(
            "probe_client_graph", "--prepared", config["prepared"], "--runtime", config["bootstrapRuntime"],
            "--caps", config["caps"], "--b1-evidence", config["b1Evidence"],
            "--client-jar", injected / "client-26.1.2-metal.jar", "--graphics-bridge", config["lwjgl"],
            "--metal-bootstrap", config["metal"], "--full-build", "--relocatable",
            # pack-60 restored Sodium's real config registration path (9 previously stubbed
            # methods became reachable) and the 7 GiB image builder heap OOMed with 5117M live
            # old-gen against a 5438M old-gen capacity. 8 GiB carried packs 61-68 (live set
            # ~4.96 GB after a full GC). pack-69, the first pack without Iris, reached 7087M
            # live against a 7337M capacity and sat in full-GC thrash (->7087M, nothing
            # reclaimed), so the reachable image heap is now above what 8 GiB can hold.
            # 9 GiB is the largest setting the 50%-of-physical-memory ceiling allows on this
            # 18 GiB host; probe_client_graph.py rejects anything larger before analysis starts.
            "--include-game-resources", "--heap-gib", "9", "--simulator-thread-dumps",
            "--output", "{product}"),
            timeout=3800)
        image = read_json(aot / "result.json")
        image_object = Path(image["imageObject"]["path"])
        flags = read_json(aot / "analysis/command.json")["argv"]
        if (image["targetCodeGeneration"] != "RELOCATABLE_OBJECT"
                or sha256(image_object) != image["imageObject"]["sha256"]
                or "--no-fallback" not in flags or "-H:+ExitAfterRelocatableImageWrite" not in flags):
            raise ValueError(f"Invalid AOT object or arguments. Logs: {aot / 'analysis'}")
        runtime = pipeline.step("runtime", script(
            "build_ios_runtime", "--sdk", "iphoneos", "--with-extnet",
            "--graalvm-home", home, "--jdk-source", manifest["runtimeSources"]["jdk"],
            "--graal-source", manifest["runtimeSources"]["graal"],
            "--aot-object", image_object, "--output", "{product}"))
        linked = pipeline.step("link", script(
            "link_c0_ios", "--sdk", "iphoneos", "--image", aot, "--runtime", runtime,
            "--stub-unsupported-jni", "--output", "{product}"))
        validate_dylib(linked / "client-graph.dylib")
        staged = pipeline.step("stage", script(
            "stage_device_xcode", "--client", linked,
            *(argument for name in ("glfw", "lwjgl", "metal", "openal", "shaders")
              for argument in (f"--{name}", config[name])),
            "--output", "{product}"))
        app = pipeline.step("package", [
            *device_xcode(staged, config["assets"]), "-derivedDataPath", "{product}", "build"],
            outputs=lambda attempt: attempt / "product/Build/Products/World Device-iphoneos/C0Harness.app")
        validate_package(app, staged, manifest["assetsSHA256"])
        facts = app_facts(app, args.device, output / "verify" / uuid4().hex)
        write_json(output / "result.json", {
            "status": "SIGNED_DEVICE_APP", "target": TARGET, "buildKey": key,
            "loader": args.loader, "loaderReport": str(loader_report) if loader_report else None,
            "inputsSHA256": sha256(saved), "aotCommand": str(aot / "analysis/command.json"),
            "linkReport": str(linked / "result.json"), "app": str(app.relative_to(output)),
            "aotCommandSHA256": sha256(aot / "analysis/command.json"),
            "linkReportSHA256": sha256(linked / "result.json"),
            "appFilesSHA256": tree_files(app), "verification": facts,
        })
        return output / "result.json"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mcfao", description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--config", type=Path, required=True)
    compile_command = commands.add_parser("build")
    compile_command.add_argument("--version", choices=(VERSION,), required=True)
    compile_command.add_argument("--loader", choices=("vanilla", "fabric"), required=True)
    compile_command.add_argument("--config", type=Path, required=True)
    compile_command.add_argument("--mods", type=Path)
    compile_command.add_argument("--prepare-only", action="store_true",
                                 help="Stop after Fabric metadata inspection or audited transformation")
    compile_command.add_argument("--audited-mods", action="store_true",
                                 help="Confirm these mod JARs have been audited for host build execution")
    exporter = commands.add_parser("export", help="Archive, export and verify a development IPA")
    exporter.add_argument("--build", type=Path, required=True)
    exporter.add_argument("--export-options", type=Path, required=True)
    for sub in (compile_command, commands.add_parser("verify"), exporter):
        sub.add_argument("--target", choices=(TARGET,), required=True)
        sub.add_argument("--output", type=Path, required=True)
        sub.add_argument("--device", help="Require this hardware UDID in the embedded profile")
    args = parser.parse_args(argv)
    if args.action == "build":
        if args.loader == "fabric":
            if not args.mods or not (args.prepare_only or args.audited_mods):
                compile_command.error("Fabric requires --mods and either --prepare-only or --audited-mods")
        elif args.mods or args.prepare_only or args.audited_mods:
            compile_command.error("Mod options are only valid for Fabric")
    try:
        if args.action == "doctor":
            config = load_config(args.config.resolve())
            manifest, client, _ = inputs(config)
            result = {"status": "INPUTS_VERIFIED", "client": str(client),
                      "inputCount": len(manifest["filesSHA256"]), "toolchain": manifest["toolchain"]}
        elif args.action == "build":
            result = {"manifest": str(build(args, load_config(args.config.resolve())))}
        elif args.action == "export":
            result = export_ipa(args)
        else:
            result = verify(args.output.resolve(), args.device)
        print(json.dumps(result, indent=2))
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"mcfao {args.action}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
