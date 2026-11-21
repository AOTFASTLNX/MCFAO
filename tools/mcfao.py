"""Build and verify local Native Craft Launcher research packages."""
from __future__ import annotations
from storage_config import cache_path

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
import shutil
import subprocess
import sys
from uuid import uuid4
import zipfile
from renderer_profile import (BUILD_PROVENANCE, DEFAULT_RENDERER, RENDERERS, config_names,
                              dylib_uuid, libraries as renderer_libraries, validate_runtime)
from external_storage import ExternalStorageUnavailable, require_mount
import aot_cache

from bootstrap_toolchain import sha256
from build_c0_harness import binary_platform, validate_dylib, validate_shader_bundle
from capture import ROOT, capture
from bundle_source import source_identity
from test_version import test_version, ipa_filename
from graphics_common import bridge_overlays, verify_gl41_bridge
from native_game_checks import verify_game_image
from build_glfw_lite import exported_symbols, validate_input_exports
from glfw_runtime_contract import validate_glfw_renderer
from prepare_fabric_aot import TOOL as FABRIC_TOOL, mod_files
from aot_compatibility import add_bytecode_results, issue, publish, record_build_pass, transform_report
from mdaf import AGENT_FILES
from stage_game_assets import verified_assets
from mod_file_policy import content_paths, copy_ignore, is_metadata

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
    "mcfao", "import_instance", "mod_file_policy", "native_image_home",
    "split_methods", "build_method_splitter", "inject_metal_backend", "probe_client_graph",
    "build_ios_runtime", "link_c0_ios", "stage_device_xcode", "graphics_common",
    "stage_game_assets", "run_b0_reference", "capture", "inspect_ios_candidate",
    "build_c0_harness", "client_graph_diagnostics", "lwjgl_codegen",
    "config_reflection", "mdaf", "verify_aot_classpath", "patch_gl41_client", "renderer_profile",
    "cleanup_storage",
    "storage_config", "bundle_source", "host_tools", "verified_download", "glfw_runtime_contract",
    "native_game_checks", "app_icon", "aot_cache", "test_version",
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
    for item in sorted(content_paths(directory)):
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


def load_config(path: Path, renderer: str = DEFAULT_RENDERER) -> dict:
    config = read_json(path)
    required = (set(CONFIG_PATHS) - {"metal", "shaders"}) | set(config_names(renderer))
    allowed = set(CONFIG_PATHS) | OPTIONAL_CONFIG_PATHS | {"gl41", "lwjglOpengl"}
    if not required <= config.keys() or config.keys() - allowed:
        raise ValueError("Config requires " + ", ".join(CONFIG_PATHS) + ". Optional paths are openjdkSource and graalSource.")
    return {name: (path.parent / Path(value).expanduser()).resolve(strict=True)
            for name, value in config.items() if name in required or name in OPTIONAL_CONFIG_PATHS}


def runtime_sources(config):
    paths = {}
    for tool, name in (("jdk", "openjdkSource"), ("graal", "graalSource")):
        if name in config:
            paths[tool] = config[name]
        else:
            descriptor = cache_path('upstream') / f"{tool}.json"
            paths[tool] = Path(read_json(descriptor)["path"]).resolve(strict=True)
    return paths


def asset_files(assets: Path, metadata: Path) -> dict:
    _, index, objects = verified_assets(assets, read_json(metadata))
    expected = {str(index.relative_to(assets)), *map(str, objects)}
    actual = tree_files(assets)
    if actual.keys() != expected:
        raise ValueError(f"Asset directory must contain only the indexed asset set: {assets}")
    return actual


def inputs(config: dict, renderer: str = DEFAULT_RENDERER) -> tuple[dict, Path, list[Path]]:
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
    for file in sorted(content_paths(home / "lib/svm")):
        if file.is_file():
            add(file)
    for file in sorted((home / "jmods").glob("*.jmod")):
        if not is_metadata(file.name):
            add(file)
    for file in sorted(content_paths(home / "include")):
        if file.suffix == ".h":
            add(file)
    for name in ("result.json", "driver.jar"):
        add(config["prepared"] / name, prepared["binaries"][name]["sha256"] if name == "driver.jar" else None)
    for name in ("versionMetadata", "b1Evidence"):
        add(config[name])
    # Existing graphics builds are immutable inputs. Their report checks and the target
    # checks are repeated by the packaging step.
    for name in ("caps", *config_names(renderer)):
        directory = config[name]
        selected = {"glfw": ["libglfw.dylib"], "lwjgl": ["liblwjgl.dylib"],
                    "metal": ["libfaot_metal.dylib", "metal-backend.jar", "fabricaot-present.metallib"],
                    "openal": ["libopenal.dylib"], "shaders": [],
                    "gl41": ["libOSMesa.8.dylib", "libMoltenVK.dylib"],
                    "lwjglOpengl": ["liblwjgl_opengl.dylib"]}
        if name == "caps":
            files = tree_files(directory)
        else:
            files = {"result.json": sha256(directory / "result.json")}
            for filename in selected[name]:
                files[filename] = sha256(directory / filename)
            if name == "lwjgl":
                files.update({p.name: sha256(p) for p in directory.glob("*-ios.jar") if not is_metadata(p.name)})
            if name == "shaders":
                files.update({f"bundle/{p}": h for p, h in tree_files(directory / "bundle").items()})
        fingerprints.update({str(directory / p): h for p, h in files.items()})
    bridge_overlays(config["lwjgl"])
    # A valid historical report can still predate a required Mod input API.
    # Inspect the actual binary and bind the Java overlays to that GLFW input.
    glfw_binary = config["glfw"] / "libglfw.dylib"
    validate_glfw_renderer(glfw_binary, renderer)
    validate_input_exports(exported_symbols(subprocess.check_output(
        ["xcrun", "nm", "-gUj", str(glfw_binary)], text=True)))
    if read_json(config["lwjgl"] / "result.json").get("glfwLibrarySHA256") != sha256(glfw_binary):
        raise ValueError("LWJGL overlays were generated against another GLFW library; rebuild LWJGL")
    if renderer == "metal":
        validate_shader_bundle(config["shaders"] / "bundle", simulator=False)
    else:
        verify_gl41_bridge(config["lwjgl"])
        from fetch_gl41_runtime import FILES, macho_platform
        runtime_report = read_json(config["gl41"] / "result.json")
        if runtime_report.get("status") != "GL41_RUNTIME_FETCHED":
            raise ValueError("GL41 runtime report is not verified")
        for row in FILES:
            binary = config["gl41"] / row["name"]
            macho_platform(binary)
            if sha256(binary) != row["sha256"]:
                raise ValueError("GL41 runtime fingerprint changed: " + str(binary))
    for key, filename, status in (
        ("glfw", "libglfw.dylib", "NATIVE_SUBSET_BUILT"),
        ("lwjgl", "liblwjgl.dylib", "STATIC_JNI_BRIDGE_BUILT"),
        ("metal", "libfaot_metal.dylib", "METAL_BOOTSTRAP_BUILT"),
        ("openal", "libopenal.dylib", "OPENAL_SOFT_BUILT"),
    ):
        if key not in config_names(renderer):
            continue
        report = read_json(config[key] / "result.json")
        if (report["status"] != status
                or validate_dylib(config[key] / filename)["sha256"] != report["binarySHA256"]):
            raise ValueError(f"Invalid graphics input: {config[key] / filename}")
    if renderer == "gl41":
        shim = read_json(config["lwjglOpengl"] / "result.json")
        if shim.get("status") != "LWJGL_OPENGL_SHIM_BUILT" or validate_dylib(config["lwjglOpengl"] / "liblwjgl_opengl.dylib")["sha256"] != shim["binarySHA256"]:
            raise ValueError("Invalid GL41 JNI shim")
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
        for path in sorted(content_paths(ROOT / directory)):
            if path.is_file() and "build" not in path.parts and "xcuserdata" not in path.parts:
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
                if file.is_file() and not is_metadata(file.relative_to(source / relative)):
                    add(file)
    return {
        "schema": 1, "version": VERSION, "loader": "vanilla", "mappingNamespace": "official",
        "renderer": renderer, **source_identity(ROOT),
        "target": TARGET, "config": {key: str(p) for key, p in config.items()},
        "toolchain": toolchain(home), "filesSHA256": fingerprints,
        "runtimeSources": {key: str(path) for key, path in sources.items()},
        "assetsSHA256": asset_files(config["assets"], config["versionMetadata"]),
    }, clients[0], libraries


CRITICAL_FAILURE = re.compile(
    r"OutOfMemoryError|ran out of memory|NativeImage\$NativeImageError|"
    r"UnsatisfiedLinkError|NoClassDefFoundError|Exception in thread|"
    r"^error:|\bFATAL\b|^Error:")


def failure_summary(log: Path, limit=14):
    """Pick the lines that name the failure, not just the last lines written.

    A native-image run prints diagnostics and a report path after its error, so
    the final lines of stdout often say nothing about the cause. Prefer the first
    recognisable error lines and fall back to the tail when none match.
    """
    text = "\n".join((log / name).read_text(errors="replace") for name in ("stderr.log", "stdout.log"))
    lines = [line for line in text.splitlines() if line.strip()]
    picked = []
    for line in lines:
        if CRITICAL_FAILURE.search(line) and line not in picked:
            picked.append(line.strip())
            if len(picked) == limit: break
    return picked or lines[-8:]


def aot_failure_summary(product: Path):
    """Read the current probe's structured failure if it reached Native Image."""
    try:
        image = read_json(product / "result.json")
        failure = image["analysisFailure"]
        details = [
            f"Native Image builder: {image['builderGC']} GC, -Xmx{image['heapGiB']}g",
        ]
        phase = failure.get("lastCompletedPhase")
        if phase is not None:
            details.append(f"Native Image last completed phase: {phase}/8")
        return details + failure["lines"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


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
            tail = (aot_failure_summary(product) if name == "aot" else []) or failure_summary(log)
            raise RuntimeError(f"{name} failed (exit {result['exitCode']}, timeout={result['timedOut']}). "
                               f"Logs: {log}\n" + "\n".join(tail))
        if not product.is_dir():
            raise RuntimeError(f"{name} did not produce {product}. Logs: {log}")
        write_json(checkpoint, {"key": self.key, "argv": command_args, "attempt": attempt.name,
                                "filesSHA256": tree_files(product)})
        return product


def script(name, *args):
    return [sys.executable, "-B", ROOT / "tools" / f"{name}.py", *args]


def icon_options(args):
    """Forward only the icon options the user actually set."""
    options = []
    if getattr(args, "icon_fit", "fit") == "fill":
        options += ["--fit", "fill"]
    if getattr(args, "icon_background", "transparent") != "transparent":
        options += ["--background", args.icon_background]
    if getattr(args, "icon_padding", 0):
        options += ["--padding", str(args.icon_padding)]
    return options


def loader_client(pipeline, args, config, client, inputs):
    if args.loader == "vanilla":
        return client, None
    # Every incompatible class makes the driver run Knot again without the offending Mod, so a
    # pack whose exclusions are only discovered by the class audit needs two full passes. pack-70
    # needed ~4 min + ~6 min and was killed by the old 10-minute default right after writing its
    # final client.jar; the budget now covers two Knot passes with headroom.
    prepare_args = ["--prepared", config["prepared"], "--client", client,
                    "--mods", args.mods.resolve(), "--output", "{product}",
                    "--renderer", args.renderer,
                    "--compatibility-report", pipeline.root / "compatibility.json",
                    "--audited-mods" if args.audited_mods else "--inspect"]
    if args.trace_agent:
        prepare_args.append("--trace-agent")
    prepared = pipeline.step("fabric", script(
        "prepare_fabric_aot", *prepare_args), timeout=1800)
    report = prepared / "result.json"
    facts = read_json(report)
    publish(pipeline.root / "compatibility.json", transform_report(facts))
    if facts["modSHA256"] != inputs["modsSHA256"]:
        raise ValueError(f"Mod JARs changed after input resolution: {report}")
    if args.prepare_only:
        return client, report
    if facts.get("excludedMods") or facts.get("retiredJars"):
        raise ValueError(f"Requested Fabric instance contains excluded Mods; review {report}. Build an explicitly selected subset separately.")
    jar = prepared / "client.jar"
    if (facts["status"] != "FABRIC_AOT_INPUT_PREPARED" or facts.get("renderer") != args.renderer
            or sha256(jar) != facts["outputJarSHA256"]):
        raise ValueError(f"Fabric preparation did not yield a verified AOT input: {report}")
    return jar, report


def app_facts(app: Path, requested_device: str | None, logs: Path, renderer=DEFAULT_RENDERER, signed_app=True) -> dict:
    info = plistlib.loads((app / "Info.plist").read_bytes())
    executable = app / info["CFBundleExecutable"]
    facts = binary_platform(executable)
    if facts["platform"] != "IOS" or command("/usr/bin/lipo", "-archs", executable) != "arm64":
        raise ValueError(f"Expected an arm64 iPhoneOS executable: {facts}")
    libraries = [validate_dylib(path) for path in sorted((app / "Frameworks").glob("*.dylib"))
                 if not is_metadata(path.name)]
    validate_runtime(app, renderer)
    for library in libraries:
        if command("/usr/bin/lipo", "-archs", library["path"]) != "arm64":
            raise ValueError(f"Expected a single arm64 slice: {library['path']}")
    abi = {"_run_main", "_graal_create_isolate", "_graal_tear_down_isolate"}
    symbols = command("/usr/bin/xcrun", "nm", "-gUj", app / "Frameworks/client-graph.dylib")
    if abi - set(symbols.splitlines()):
        raise ValueError("Packaged image is missing the Native Image entry/isolate ABI")
    gameplay = verify_game_image(app / "Frameworks/client-graph.dylib") if renderer == "gl41" else None
    if not signed_app:
        return {"executable": facts, "libraries": libraries, "bundleID": info["CFBundleIdentifier"],
                "signature": "UNSIGNED - cannot install directly", "imageExports": sorted(abi), "gameCode": gameplay, "deviceRun": "NOT RUN"}
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
            "dynamicCodeEntitlements": "ABSENT", "imageExports": sorted(abi), "gameCode": gameplay, "deviceRun": "NOT RUN"}


def validate_package(app, staged, asset_hashes, renderer=DEFAULT_RENDERER):
    frameworks = app / "Frameworks"
    validate_runtime(app, renderer)
    if renderer == "metal":
        present = "fabricaot-present.metallib"
        if sha256(frameworks / present) != sha256(staged / present):
            raise ValueError(f"Packaged resource changed: {present}")
        if tree_files(frameworks / "fabricaot-shaders") != tree_files(staged / "fabricaot-shaders"):
            raise ValueError("Packaged shader bundle changed")
    if tree_files(app / "assets") != asset_hashes:
        raise ValueError("Packaged game assets changed")
    # Codesign modifies dylib bytes. Compare the Mach-O UUIDs to establish provenance.
    for library in staged.glob("*.dylib"):
        if is_metadata(library.name):
            continue
        packaged = frameworks / library.name
        if dylib_uuid(library) != dylib_uuid(packaged):
            raise ValueError(f"Embedded image UUID differs: {library.name}")
    if (staged / BUILD_PROVENANCE).is_file():
        if sha256(app / BUILD_PROVENANCE) != sha256(staged / BUILD_PROVENANCE):
            raise ValueError("Packaged build provenance differs from the staged file")


def validate_build_provenance(app, build_key, commit, renderer):
    report = read_json(app / BUILD_PROVENANCE)
    expected = {name: dylib_uuid(app / "Frameworks" / name) for name in renderer_libraries(renderer)}
    if report != dict(schemaVersion=1, buildKey=build_key, sourceCommit=commit,
                      renderer=renderer, dylibUUIDs=expected):
        raise ValueError("Packaged build provenance does not match the build or its dylibs")
    return report


def write_payload_ipa(app: Path, ipa: Path):
    with zipfile.ZipFile(ipa, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for file in sorted(content_paths(app)):
            if file.is_file():
                archive.write(file, (Path("Payload") / app.name / file.relative_to(app)).as_posix())
    with zipfile.ZipFile(ipa) as archive:
        if archive.testzip() is not None:
            raise ValueError("IPA CRC check failed")


def verify_icon(app: Path, name: str):
    """Require the packaged icon catalog and the Info.plist keys actool emits."""
    info = plistlib.loads((app / "Info.plist").read_bytes())
    primary = info.get("CFBundleIcons", {}).get("CFBundlePrimaryIcon", {})
    if primary.get("CFBundleIconName") != name or not primary.get("CFBundleIconFiles"):
        raise ValueError(f"Packaged app does not declare the {name} icon")
    for artifact in ("Assets.car", f"{name}60x60@2x.png", f"{name}76x76@2x~ipad.png"):
        if not (app / artifact).is_file():
            raise ValueError(f"Packaged app is missing the {artifact} icon asset")


def icon_build_dir(build: Path) -> Path:
    """Locate the verified compiled icon of a completed build."""
    build = Path(build).resolve(strict=True)
    checkpoint = read_json(build / "icon" / "checkpoint.json")
    attempt = checkpoint.get("attempt")
    if not isinstance(attempt, str) or not attempt:
        raise ValueError("The completed build has no compiled app icon")
    product = (build / "icon" / attempt / "product").resolve(strict=True)
    if not product.is_relative_to(build / "icon") or tree_files(product) != checkpoint.get("filesSHA256"):
        raise ValueError("Compiled app icon changed since the build")
    return product / "compiled"


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
            if is_metadata(path.name):
                continue
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


def device_xcode(staged: Path, assets: Path, team: str | None = None, *, renderer=DEFAULT_RENDERER, unsigned=False,
                 bundle_id=BUNDLE_IDENTIFIER, icon: Path | None = None, icon_name: str | None = None,
                 test_version_label="") -> list:
    team = ("" if unsigned else resolve_development_team(bundle_id)) if team is None else team
    icon_settings = ([f"FAOT_APP_ICON_DIR={icon}", f"FAOT_APP_ICON_NAME={icon_name}"]
                     if icon and icon_name else [])
    return [
        "/usr/bin/xcodebuild", "-project", ROOT / "ios/C0Harness/C0Harness.xcodeproj",
        "-scheme", "WorldDevice", "-destination", "generic/platform=iOS",
        f"FAOT_GRAPHICS_NATIVE_DIR={staged}", f"FAOT_CLIENT_LIBRARY={staged / 'client-graph.dylib'}",
        f"FAOT_GAME_ASSETS_DIR={assets}", f"DEVELOPMENT_TEAM={team}", f"FAOT_RENDERER={renderer}",
        f"PRODUCT_BUNDLE_IDENTIFIER={bundle_id}",
        f"FAOT_TEST_VERSION={test_version(test_version_label)}",
        *icon_settings,
        *(["CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO"] if unsigned else []),
    ]


def verify(output: Path, device: str | None) -> dict:
    report = read_json(output / "result.json")
    if report["target"] != TARGET or report["status"] not in ("SIGNED_DEVICE_APP", "UNSIGNED_DEVICE_APP"):
        raise ValueError("No completed iPhoneOS app manifest")
    if sha256(output / "inputs.json") != report["inputsSHA256"]:
        raise ValueError("Build input manifest changed")
    evidence_keys = ["aotCommand", "linkReport"]
    if report.get("compatibilityReport"):
        evidence_keys.append("compatibilityReport")
    for key in evidence_keys:
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
    icon = report.get("appIcon")
    if icon and icon.get("assetName"):
        verify_icon(app, icon["assetName"])
    if test_version(plistlib.loads((app / "Info.plist").read_bytes()).get("FAOTTestVersion", "")) != test_version(report.get("testVersion", "")):
        raise ValueError("Packaged test version differs from recorded build")
    if report.get("buildProvenance") is not None:
        provenance = validate_build_provenance(app, report["buildKey"], report["sourceCommit"], report["renderer"])
        if provenance != report["buildProvenance"]:
            raise ValueError("Build provenance differs from the recorded result")
    logs = output / "verify" / uuid4().hex
    if report.get("ipa") and (sha256(Path(report["ipa"])) != report["sha256"] or Path(report["ipa"]).stat().st_size != report["bytes"]):
        raise ValueError("IPA changed since packaging")
    return app_facts(app, device, logs, report.get("renderer", DEFAULT_RENDERER), report["status"] == "SIGNED_DEVICE_APP")


def export_ipa(args) -> dict:
    from mod_file_policy import is_metadata
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
    icon = manifest.get("appIcon")
    icon_settings = {}
    if icon and icon.get("assetName"):
        icon_settings = dict(icon=icon_build_dir(build), icon_name=icon["assetName"])
    output.mkdir(parents=True, exist_ok=False)

    def step(name, argv, timeout=300):
        log = output / name
        print(f"{name}: {log}", flush=True)
        result = capture(list(map(str, argv)), log, timeout)
        if result["exitCode"] or result["timedOut"]:
            raise RuntimeError(f"{name} failed. Logs: {log}")

    archive = output / "WorldDevice.xcarchive"
    renderer = manifest.get("renderer", DEFAULT_RENDERER)
    bundle_id = evidence.get("bundleID", BUNDLE_IDENTIFIER)
    seed = build / "instance-seed"
    step("archive", [*device_xcode(staged, assets, renderer=renderer, bundle_id=bundle_id,
                                   test_version_label=evidence.get("testVersion", ""), **icon_settings),
                     *([f"FAOT_INSTANCE_DATA_DIR={seed}"] if seed.is_dir() else []), "-derivedDataPath", output / "DerivedData",
                     "-archivePath", archive, "archive"])
    step("export-log", ["/usr/bin/xcodebuild", "-exportArchive", "-archivePath", archive,
                        "-exportOptionsPlist", options, "-exportPath", output / "export"])
    # exFAT volumes (the external build disk) create `._name.ipa` sidecars that
    # match `*.ipa`. They are metadata, not products, and must not count as a
    # second export.
    ipas = [p for p in (output / "export").glob("*.ipa") if not is_metadata(p.name)]
    if len(ipas) != 1:
        raise ValueError(f"Expected one exported IPA: {output / 'export'}")
    ipa = ipas[0]
    label = test_version(evidence.get("testVersion", ""))
    if label:
        named = ipa.with_name(ipa_filename(label))
        if named != ipa:
            if named.exists(): raise ValueError("IPA output already exists")
            ipa.rename(named)
            ipa = named
    unpacked = output / "unpacked"
    step("unpack", ["/usr/bin/ditto", "--norsrc", "--noextattr", "--noqtn", "-x", "-k", ipa, unpacked])
    apps = [p for p in (unpacked / "Payload").glob("*.app") if not is_metadata(p.name)]
    if len(apps) != 1:
        raise ValueError("Expected one exported iPhoneOS app")
    validate_package(apps[0], staged, evidence["assetsSHA256"], renderer)
    provenance = None
    if manifest.get("buildProvenance") is not None:
        provenance = validate_build_provenance(apps[0], manifest["buildKey"], manifest["sourceCommit"], renderer)
    if icon and icon.get("assetName"):
        verify_icon(apps[0], icon["assetName"])
    if test_version(plistlib.loads((apps[0] / "Info.plist").read_bytes()).get("FAOTTestVersion", "")) != label:
        raise ValueError("Exported test version differs from build inputs")
    result = {"status": "DEVELOPMENT_IPA_VERIFIED", "target": TARGET, "ipa": str(ipa),
              "sha256": sha256(ipa), "bytes": ipa.stat().st_size, "build": str(build),
              "exportOptionsSHA256": sha256(options), "testVersion": label,
              "renderer": renderer, "sourceCommit": manifest.get("sourceCommit"),
              "buildProvenance": provenance,
              "verification": app_facts(apps[0], args.device, output / "verify", renderer)}
    write_json(output / "result.json", result)
    return result


def instance_files(root):
    """Require the exact first-party import manifest; never stage accounts or saves."""
    from preflight import safe_archive_path
    root = Path(root).resolve()
    manifest = read_json(root / "import.json")
    files = tree_files(root)
    from mod_file_policy import is_metadata
    declared = {name: facts for name, facts in manifest["files"].items() if not is_metadata(name)}
    if set(files) != set(declared) | {"import.json"}:
        raise ValueError("Imported instance contains undeclared files")
    for name, facts in declared.items():
        if not safe_archive_path(name) or (name != "options.txt" and name.split("/", 1)[0] not in ("mods", "config", "defaultconfigs", "resourcepacks", "shaderpacks", "kubejs", "scripts")):
            raise ValueError("Unsafe imported instance file")
        if files[name] != facts["sha256"] or (root / name).stat().st_size != facts["bytes"]:
            raise ValueError("Imported instance changed: " + name)
    return files


def compile_client_image(pipeline, manifest, config, client, libraries, loader_report, trace_paths):
    renderer = manifest["renderer"]
    gl41 = renderer == "gl41"
    home = Path(read_json(config["prepared"] / "result.json")["javaHome"])
    split = pipeline.step("split", script(
        "split_methods", "--jar", client, "--output-jar", "{product}/client.jar",
        "--report", "{product}/split-report.json", "--tool", config["splitter"],
        "--classpath", *libraries))
    asm = [row["path"] for row in read_json(config["splitter"] / "result.json")["asmJars"]
           if row["name"] in {"asm-9.9.jar", "asm-tree-9.9.jar"}]
    injected = pipeline.step("gl41-patch" if gl41 else "metal-injection", script(
        "patch_gl41_client" if gl41 else "inject_metal_backend", "--client", split / "client.jar", "--output", "{product}",
        "--graalvm-home", home, "--asm-jars", *asm))
    tracing_path = None
    if loader_report:
        tracing = read_json(loader_report).get("tracingAgent", {})
        candidate = Path(tracing["path"]) if tracing.get("path") else None
        if candidate and candidate.is_dir() and any(not is_metadata(p.name) for p in candidate.glob("*.json")):
            tracing_path = candidate
    # 9 GiB is the largest setting the 50%-of-physical-memory ceiling allows on this 18 GiB
    # host; probe_client_graph.py checks current headroom before analysis starts.
    aot_args = ["--prepared", config["prepared"], "--runtime", config["bootstrapRuntime"],
        "--caps", config["caps"], "--b1-evidence", config["b1Evidence"],
        "--client-jar", injected / ("client.jar" if gl41 else "client-26.1.2-metal.jar"), "--graphics-bridge", config["lwjgl"],
        "--renderer", renderer, "--compatibility-report", pipeline.root / "compatibility.json",
        "--preflight-cache", cache_path("aot-preflight"),
        *([] if gl41 else ["--metal-bootstrap", config["metal"]]), "--full-build", "--relocatable",
        "--include-game-resources", "--heap-gib", str(manifest["heapGiB"]),
        "--builder-gc", manifest["builderGC"], f'--optimization={manifest["optimizationLevel"]}',
        "--parallelism", str(manifest["parallelism"]), "--simulator-thread-dumps",
        "--output", "{product}"]
    if manifest.get("exactReachabilityMetadata"):
        aot_args.append("--exact-reachability-metadata")
    if loader_report:
        aot_args.extend(["--fabric-report", loader_report])
    for path in [*trace_paths, *([tracing_path] if tracing_path else [])]:
        aot_args.extend(["--tracing-config", path])
    try:
        aot = pipeline.step("aot", script("probe_client_graph", *aot_args), timeout=3800)
    except (ValueError, RuntimeError):
        summary_path = pipeline.root / "compatibility.json"
        if summary_path.is_file():
            summary = read_json(summary_path)
            if summary["stages"]["aot"] == "UNVERIFIED":
                summary["stages"]["aot"] = "FAIL"
                publish(summary_path, summary)
        raise
    return aot


def build(args, config):
    output = args.output.resolve()
    if output.is_dir() and any(output.iterdir()) and not (
            (output / "inputs.json").is_file() or {p.name for p in output.iterdir()} == {".lock"}):
        raise ValueError(f"Use a new output directory or an NCL build workspace: {output}")
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (output / "result.json").exists():
            raise ValueError("Completed build is immutable. Use verify or select a new output.")
        renderer = getattr(args, "renderer", DEFAULT_RENDERER)
        manifest, client, libraries = inputs(config, renderer)
        # Large Fabric graphs can fill Parallel GC's old generation during method layout,
        # even at the configured heap limit. G1 assigns heap regions to generations as needed.
        builder_gc = getattr(args, "builder_gc", None) or ("g1" if args.loader == "fabric" else "parallel")
        quick_build = getattr(args, "quick_build", False)
        manifest.update({"testVersion": test_version(getattr(args, "test_version", "")),
                         "unsigned": getattr(args, "unsigned", False), "bundleID": getattr(args, "bundle_id", BUNDLE_IDENTIFIER),
                         "heapGiB": getattr(args, "heap_gib", 9), "parallelism": getattr(args, "parallelism", 4),
                         "builderGC": builder_gc, "quickBuild": quick_build,
                         "optimizationLevel": os.environ.get("MCFAO_OPT_LEVEL", "-O1")})
        manifest["loader"] = args.loader
        if getattr(args, "exact_reachability_metadata", False):
            manifest["exactReachabilityMetadata"] = True
        trace_paths = [path.resolve(strict=True) for path in getattr(args, "tracing_config", ())]
        for path in trace_paths:
            if not path.is_dir() or not any((path / name).is_file() for name in AGENT_FILES):
                raise ValueError(f"Tracing metadata directory contains no supported files: {path}")
        if trace_paths:
            manifest["tracingDirectories"] = list(map(str, trace_paths))
            manifest["tracingSHA256"] = {str(path / name): sha256(path / name)
                                         for path in trace_paths for name in sorted(AGENT_FILES)
                                         if (path / name).is_file()}
        for name in ("probe_client_graph.py", "config_reflection.py", "mdaf.py", "aot_compatibility.py",
                     "capture.py", "run_b0_reference.py"):
            source = ROOT / "tools" / name
            manifest["filesSHA256"][str(source)] = sha256(source)
        icon = getattr(args, "icon", None)
        icon_name = None
        if icon:
            from app_icon import icon_path, source_facts, icon_document_name, ICON_NAME as default_icon_name
            icon = icon_path(str(icon))
            icon_name = icon_document_name(icon) if icon.suffix.lower() == ".icon" else default_icon_name
            manifest["appIcon"] = source_facts(icon)
        instance = getattr(args, "instance_data", None)
        if instance:
            instance = instance.resolve()
            if args.loader != "fabric" or args.mods.resolve() != instance / "mods":
                raise ValueError("Imported instance requires Fabric and its matching mods directory")
            manifest["instanceSHA256"] = instance_files(instance)
        if args.loader == "fabric":
            lock = read_json(ROOT / "compiler/fabric.lock.json")
            manifest["fabricLoaderVersion"] = lock["fabricLoader"]
            manifest["modsSHA256"] = {str(p): sha256(p) for p in mod_files(args.mods.resolve())}
            manifest["auditedMods"] = args.audited_mods
            manifest["prepareOnly"] = args.prepare_only
            manifest["traceAgent"] = args.trace_agent
            manifest["filesSHA256"].update({str(p): sha256(p) for p in (
                ROOT / "tools/prepare_fabric_aot.py", ROOT / "tools/prepare_b0.py",
                ROOT / "tools/verify_aot_classpath.py",
                *(p for p in content_paths(FABRIC_TOOL) if p.suffix == ".java"),
            )})
        manifest["requestedDevice"] = args.device
        key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        saved = output / "inputs.json"
        if saved.exists() and read_json(saved) != manifest:
            raise ValueError(f"Build inputs changed. Use a new output. Previous inputs: {saved}")
        if not saved.exists():
            write_json(saved, manifest)
        pipeline = Build(output, key)
        if args.prepare_only:
            _, loader_report = loader_client(pipeline, args, config, client, manifest)
            return loader_report
        cache = cache_path("aot-objects") if quick_build else None
        image_key = aot_cache.cache_key(manifest) if cache is not None else None
        restored = aot_cache.restore(cache, image_key, output, manifest) if cache is not None else None
        if restored is None:
            client, loader_report = loader_client(pipeline, args, config, client, manifest)
            aot = compile_client_image(pipeline, manifest, config, client, libraries, loader_report, trace_paths)
        else:
            aot, loader_report = restored
            if loader_report:
                print(f"fabric: reused verified AOT input report {loader_report}", flush=True)
            print(f"aot: reused verified native object {aot}", flush=True)
            publish(output / "compatibility.json", read_json(aot / "compatibility.json"))
        gl41 = renderer == "gl41"
        home = Path(read_json(config["prepared"] / "result.json")["javaHome"])
        image = read_json(aot / "result.json")
        if image.get("analysisFailure"):
            failure = image["analysisFailure"]
            raise ValueError("Native Image stopped before producing an image (exit "
                             f"{failure['exitCode']}). Logs: {aot / 'analysis'}\n"
                             + "\n".join(failure.get("lines") or []))
        image_object = Path(image["imageObject"]["path"])
        flags = read_json(aot / "analysis/command.json")["argv"]
        if (image["targetCodeGeneration"] != "RELOCATABLE_OBJECT"
                or not image_object.resolve(strict=True).is_relative_to(aot.resolve())
                or sha256(image_object) != image["imageObject"]["sha256"]
                or "--no-fallback" not in flags or "-H:+ExitAfterRelocatableImageWrite" not in flags):
            raise ValueError(f"Invalid AOT object or arguments. Logs: {aot / 'analysis'}")
        if gl41:
            verify_game_image(image_object)
        runtime = pipeline.step("runtime", script(
            "build_ios_runtime", "--sdk", "iphoneos", "--with-extnet",
            "--graalvm-home", home, "--jdk-source", manifest["runtimeSources"]["jdk"],
            "--graal-source", manifest["runtimeSources"]["graal"],
            "--aot-object", image_object, "--output", "{product}"))
        linked = pipeline.step("link", script(
            "link_c0_ios", "--sdk", "iphoneos", "--image", aot, "--runtime", runtime,
            "--stub-unsupported-jni", "--output", "{product}"))
        validate_dylib(linked / "client-graph.dylib")
        if gl41:
            verify_game_image(linked / "client-graph.dylib")
        if cache is not None and restored is None:
            try:
                aot_cache.record(cache, image_key, aot, image_object, loader_report)
            except OSError as error:
                print(f"Could not save the AOT cache reference: {error}", file=sys.stderr)
        compatibility = read_json(aot / "compatibility.json")
        unsupported_jni = read_json(linked / "result.json").get("unsupportedEntrypoints", [])
        if unsupported_jni:
            compatibility = add_bytecode_results(
                compatibility, [issue("NATIVE_LINK_UNSUPPORTED", "warning", name)
                                for name in unsupported_jni],
                compatibility["graph"], compatibility["metadataFiles"])
        compatibility["stages"]["aot"] = "PASS"
        publish(output / "compatibility.json", compatibility)
        staged = pipeline.step("stage", script(
            "stage_device_xcode", "--client", linked,
            *(argument for name in config_names(renderer)
              for argument in ("--lwjgl-opengl" if name == "lwjglOpengl" else f"--{name}", config[name])),
            "--renderer", renderer,
            "--build-key", key, "--source-commit", manifest["sourceCommit"],
            "--output", "{product}"))
        seed = None
        if instance:
            if instance_files(instance) != manifest["instanceSHA256"]:
                raise ValueError("Imported instance changed during build")
            seed = output / "instance-seed"
            seed.mkdir(exist_ok=True)
            for directory in ("config", "defaultconfigs", "resourcepacks", "shaderpacks", "kubejs", "scripts"):
                if (instance / directory).is_dir():
                    shutil.copytree(instance / directory, seed / directory, dirs_exist_ok=True, ignore=copy_ignore)
            if (instance / "options.txt").is_file():
                shutil.copy2(instance / "options.txt", seed / "options.txt")
        pipeline_icon = None
        if icon:
            icon_build = pipeline.step("icon", script(
                "app_icon", "--icon", icon, "--output", "{product}",
                *icon_options(args)), timeout=900)
            pipeline_icon = icon_build / "compiled"
        app = pipeline.step("package", [
            *device_xcode(staged, config["assets"], renderer=renderer, unsigned=manifest["unsigned"],
                          bundle_id=manifest["bundleID"], test_version_label=manifest["testVersion"],
                          icon=pipeline_icon, icon_name=icon_name),
            *([f"FAOT_INSTANCE_DATA_DIR={seed}"] if seed else []), "-derivedDataPath", "{product}", "build"],
            outputs=lambda attempt: attempt / "product/Build/Products/World Device-iphoneos/C0Harness.app")
        validate_package(app, staged, manifest["assetsSHA256"], renderer)
        provenance = validate_build_provenance(app, key, manifest["sourceCommit"], renderer)
        if icon_name:
            verify_icon(app, icon_name)
        if seed and tree_files(seed) != tree_files(app / "instance-seed"):
            raise ValueError("Packaged instance seed changed")
        if test_version(plistlib.loads((app / "Info.plist").read_bytes()).get("FAOTTestVersion", "")) != manifest["testVersion"]:
            raise ValueError("Packaged test version differs from build inputs")
        facts = app_facts(app, args.device, output / "verify" / uuid4().hex, renderer, not manifest["unsigned"])
        ipa = output / ipa_filename(manifest["testVersion"])
        write_payload_ipa(app, ipa)
        record_build_pass(compatibility)
        publish(output / "compatibility.json", compatibility)
        write_json(output / "result.json", {
            "status": "UNSIGNED_DEVICE_APP" if manifest["unsigned"] else "SIGNED_DEVICE_APP", "target": TARGET, "buildKey": key,
            "renderer": renderer, "sourceCommit": manifest["sourceCommit"],
            "buildProvenance": provenance,
            "quickBuild": quick_build, "aotReused": restored is not None,
            "ipa": str(ipa), "bytes": ipa.stat().st_size, "sha256": sha256(ipa),
            "signature": "UNSIGNED" if manifest["unsigned"] else "DEVELOPMENT_SIGNED",
            "testVersion": manifest["testVersion"],
            "appIcon": ({"assetName": icon_name, **manifest["appIcon"]} if icon_name else None),
            "loader": args.loader, "loaderReport": str(loader_report) if loader_report else None,
            "compatibilityReport": str(output / "compatibility.json"),
            "compatibilityReportSHA256": sha256(output / "compatibility.json"),
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
    doctor.add_argument("--renderer", choices=RENDERERS, default=DEFAULT_RENDERER)
    compile_command = commands.add_parser("build")
    compile_command.add_argument("--version", choices=(VERSION,), required=True)
    compile_command.add_argument("--loader", choices=("vanilla", "fabric"), required=True)
    compile_command.add_argument("--config", type=Path, required=True)
    compile_command.add_argument("--mods", type=Path)
    compile_command.add_argument("--instance-data", type=Path, help="Verified first-party import root; seed config/resourcepacks without overwriting device files")
    compile_command.add_argument("--renderer", choices=RENDERERS, default=os.environ.get("FAOT_RENDERER", DEFAULT_RENDERER))
    compile_command.add_argument("--unsigned", action="store_true")
    compile_command.add_argument("--test-version", type=test_version, default="", help="Optional test label shown in the launcher, logs and IPA filename")
    compile_command.add_argument("--bundle-id", default=BUNDLE_IDENTIFIER)
    compile_command.add_argument("--icon", type=Path,
                                 help="Own artwork for the app icon: an .icon document or a supported image")
    compile_command.add_argument("--icon-fit", choices=("fit", "fill"), default="fit",
                                 help="Preserve the whole image (fit) or crop it to the square (fill)")
    compile_command.add_argument("--icon-background", default="transparent",
                                 help="transparent or #RRGGBB behind a non-square image")
    compile_command.add_argument("--icon-padding", type=int, default=0,
                                 help="Percentage of transparent margin around the artwork (0-30)")
    compile_command.add_argument("--heap-gib", type=int, choices=(6,7,8,9), default=9)
    compile_command.add_argument("--builder-gc", choices=("parallel", "g1"),
                                 help="Host Native Image JVM collector (default: G1 for Fabric, Parallel for vanilla)")
    compile_command.add_argument("--quick-build", action="store_true",
                                 help="Reuse matching, verified local AOT objects")
    compile_command.add_argument("--parallelism", type=int, choices=range(1,5), default=4)
    compile_command.add_argument("--prepare-only", action="store_true",
                                 help="Stop after Fabric metadata inspection or audited transformation")
    compile_command.add_argument("--audited-mods", action="store_true",
                                 help="Confirm these mod JARs have been audited for host build execution")
    compile_command.add_argument("--trace-agent", action="store_true",
                                 help="Collect GraalVM tracing metadata during the sandboxed audited Fabric rehearsal")
    compile_command.add_argument("--tracing-config", type=Path, action="append", default=[],
                                 help="Merge metadata from a local, audited tracing-agent rehearsal")
    compile_command.add_argument("--exact-reachability-metadata", action="store_true",
                                 help="Enable strict missing-registration semantics for diagnosis")
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
            if args.trace_agent and not args.audited_mods:
                compile_command.error("--trace-agent requires --audited-mods")
            if not args.mods or not (args.prepare_only or args.audited_mods):
                compile_command.error("Fabric requires --mods and either --prepare-only or --audited-mods")
        elif args.mods or args.prepare_only or args.audited_mods or args.trace_agent:
            compile_command.error("Mod options are only valid for Fabric")
        if not 0 <= args.icon_padding <= 30:
            compile_command.error("--icon-padding must be between 0 and 30")
    # Some checkouts relocate heavy evidence, caches and Rust artifacts through
    # symlinks declared in an untracked external-storage.json. Pause before
    # creating any output when that personal mapping is unavailable.
    try:
        require_mount(f"mcfao {args.action}")
        if args.action == "build":
            from storage_config import require_space, storage_paths
            paths = storage_paths()
            paths["builds"] = args.output.absolute()
            require_space(paths)
        if args.action == "doctor":
            config = load_config(args.config.resolve(), args.renderer)
            manifest, client, _ = inputs(config, args.renderer)
            result = {"status": "INPUTS_VERIFIED", "client": str(client),
                      "inputCount": len(manifest["filesSHA256"]), "toolchain": manifest["toolchain"]}
        elif args.action == "build":
            result = {"manifest": str(build(args, load_config(args.config.resolve(), args.renderer)))}
        elif args.action == "export":
            result = export_ipa(args)
        else:
            result = verify(args.output.resolve(), args.device)
        print(json.dumps(result, indent=2))
    except ExternalStorageUnavailable as error:
        print(error, file=sys.stderr)
        return 3
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"mcfao {args.action}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
