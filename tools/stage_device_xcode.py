#!/usr/bin/env python3
"""Stage verified local iPhone binaries for the WorldDevice Xcode scheme."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from build_c0_harness import sha256, validate_dylib, validate_shader_bundle
from artifact_copy import copy_artifact
from capture import ROOT
from graphics_common import register_tree
from glfw_runtime_contract import validate_glfw_renderer
from renderer_profile import BUILD_PROVENANCE, DEFAULT_RENDERER, RENDERERS, dylib_uuid, libraries
from mod_file_policy import is_metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renderer", choices=RENDERERS, default=DEFAULT_RENDERER)
    for name in ("client", "glfw", "lwjgl", "openal"):
        parser.add_argument(f"--{name}", required=True, type=Path, help="Build report directory")
    for name in ("metal", "shaders"):
        parser.add_argument(f"--{name}", type=Path, help="Native Metal build report directory")
    parser.add_argument("--gl41", type=Path, help="Verified GL41 runtime (OSMesa/MoltenVK) report directory")
    parser.add_argument("--lwjgl-opengl", type=Path, help="Verified liblwjgl_opengl shim report directory")
    parser.add_argument("--build-key", help="NCL build input fingerprint")
    parser.add_argument("--source-commit", help="Source revision to embed in the app")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/graphics/world-device-input-01")
    args = parser.parse_args(argv)
    required = ("metal", "shaders") if args.renderer == "metal" else ("gl41", "lwjgl_opengl")
    if any(getattr(args, name) is None for name in required):
        parser.error("Missing renderer inputs: " + ", ".join(required))
    forbidden = ("gl41", "lwjgl_opengl") if args.renderer == "metal" else ("metal", "shaders")
    if any(getattr(args, name) is not None for name in forbidden):
        parser.error("Inputs belong to the other renderer: " + ", ".join(forbidden))
    reports = {}
    files = {}

    def read_report(directory, statuses):
        manifest = directory.resolve(strict=True) / "result.json"
        report = json.loads(manifest.read_text())
        if report.get("status") not in statuses:
            parser.error(f"Build did not succeed: {manifest}")
        reports[str(manifest)] = sha256(manifest)
        return report

    def add(path, fingerprint, *, dylib=False):
        actual = validate_dylib(path)["sha256"] if dylib else sha256(path)
        if actual != fingerprint:
            parser.error(f"Build input fingerprint changed: {path}")
        files[path.name] = path, actual

    client = read_report(args.client, {"LINKED", "LINKED_WITH_UNSUPPORTED_ENTRYPOINTS"})
    if client.get("renderer") and client["renderer"] != args.renderer:
        parser.error("Native Image was compiled for another renderer")
    add(args.client / "client-graph.dylib", client["binary"]["sha256"], dylib=True)
    for directory, name, status in (
        (args.glfw, "libglfw.dylib", "NATIVE_SUBSET_BUILT"),
        (args.lwjgl, "liblwjgl.dylib", "STATIC_JNI_BRIDGE_BUILT"),
        (args.metal, "libfaot_metal.dylib", "METAL_BOOTSTRAP_BUILT"),
        (args.openal, "libopenal.dylib", "OPENAL_SOFT_BUILT"),
    ):
        if directory is None:
            continue
        report = read_report(directory, {status})
        add(directory / name, report["binarySHA256"], dylib=True)
        if directory == args.glfw:
            validate_glfw_renderer(directory / name, args.renderer)
        if directory == args.metal:
            add(directory / "fabricaot-present.metallib", report["metallibSHA256"])

    if args.renderer == "metal":
        read_report(args.shaders, {"VANILLA_SHADERS_PRECOMPILED"})
        shaders = validate_shader_bundle(args.shaders / "bundle", simulator=False)
        for name, fingerprint in shaders["filesSHA256"].items():
            files[f"fabricaot-shaders/{name}"] = Path(shaders["path"]) / name, fingerprint

    if args.gl41:
        runtime = read_report(args.gl41, {"GL41_RUNTIME_FETCHED"})
        for name, fingerprint in runtime["filesSHA256"].items():
            if name.endswith(".dylib") and not is_metadata(name):
                add(args.gl41 / name, fingerprint, dylib=True)
    if args.lwjgl_opengl:
        shim = read_report(args.lwjgl_opengl, {"LWJGL_OPENGL_SHIM_BUILT"})
        add(args.lwjgl_opengl / "liblwjgl_opengl.dylib", shim["binarySHA256"], dylib=True)
    expected_libraries = set(libraries(args.renderer))
    if {name for name in files if name.endswith(".dylib")} != expected_libraries:
        parser.error(f"Unexpected staged library list for {args.renderer}")

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for name, (source, fingerprint) in files.items():
        destination = out / name
        destination.parent.mkdir(exist_ok=True)
        copy_artifact(source, destination)
        if sha256(destination) != fingerprint:
            raise ValueError(f"Staged copy fingerprint changed: {name}")
    result = {"status": "WORLD_DEVICE_XCODE_INPUT_STAGED", "renderer": args.renderer, "reportsSHA256": reports,
              "filesSHA256": {name: item[1] for name, item in files.items()}}
    if args.source_commit:
        provenance = dict(schemaVersion=1, sourceCommit=args.source_commit, renderer=args.renderer,
                          dylibUUIDs={name: dylib_uuid(out / name) for name in sorted(expected_libraries)})
        fingerprint_inputs = {**provenance, "filesSHA256": result["filesSHA256"]}
        provenance["buildKey"] = args.build_key or hashlib.sha256(
            json.dumps(fingerprint_inputs, sort_keys=True).encode()).hexdigest()
        embedded = out / BUILD_PROVENANCE
        embedded.write_text(json.dumps(provenance, sort_keys=True) + "\n")
        result["filesSHA256"][BUILD_PROVENANCE] = sha256(embedded)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    register_tree(out, [sys.executable, "-B", str(Path(__file__).resolve()),
                        *(sys.argv[1:] if argv is None else argv)])
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
