#!/usr/bin/env python3
"""Stage verified local iPhone binaries for the WorldDevice Xcode scheme."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from build_c0_harness import sha256, validate_dylib, validate_shader_bundle
from capture import ROOT
from graphics_common import register_tree


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("client", "glfw", "lwjgl", "metal", "openal", "shaders"):
        parser.add_argument(f"--{name}", required=True, type=Path, help="Build report directory")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/graphics/world-device-input-01")
    args = parser.parse_args(argv)
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
    add(args.client / "client-graph.dylib", client["binary"]["sha256"], dylib=True)
    for directory, name, status in (
        (args.glfw, "libglfw.dylib", "NATIVE_SUBSET_BUILT"),
        (args.lwjgl, "liblwjgl.dylib", "STATIC_JNI_BRIDGE_BUILT"),
        (args.metal, "libfaot_metal.dylib", "METAL_BOOTSTRAP_BUILT"),
        (args.openal, "libopenal.dylib", "OPENAL_SOFT_BUILT"),
    ):
        report = read_report(directory, {status})
        add(directory / name, report["binarySHA256"], dylib=True)
        if directory == args.metal:
            add(directory / "fabricaot-present.metallib", report["metallibSHA256"])

    read_report(args.shaders, {"VANILLA_SHADERS_PRECOMPILED"})
    shaders = validate_shader_bundle(args.shaders / "bundle", simulator=False)
    for name, fingerprint in shaders["filesSHA256"].items():
        files[f"fabricaot-shaders/{name}"] = Path(shaders["path"]) / name, fingerprint

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for name, (source, fingerprint) in files.items():
        destination = out / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, destination)
        if sha256(destination) != fingerprint:
            raise ValueError(f"Staged copy fingerprint changed: {name}")
    result = {"status": "WORLD_DEVICE_XCODE_INPUT_STAGED", "reportsSHA256": reports,
              "filesSHA256": {name: item[1] for name, item in files.items()}}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    register_tree(out, [sys.executable, "-B", str(Path(__file__).resolve()),
                        *(sys.argv[1:] if argv is None else argv)])
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
