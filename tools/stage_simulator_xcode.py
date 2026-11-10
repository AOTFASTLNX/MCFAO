#!/usr/bin/env python3
"""Stage a verified, local simulator build for the WorldSimulator Xcode scheme."""
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--harness", type=Path, required=True)
    p.add_argument("--output", type=Path, default=ROOT / "artifacts/graphics/world-simulator-input-02")
    args = p.parse_args(argv)
    manifest = args.harness.resolve(strict=True) / "result.json"
    report = json.loads(manifest.read_text())
    if report.get("status") not in {"SIMULATOR_BUILT", "SIMULATOR_LAUNCHED"}:
        p.error("Expected a successful simulator harness build")

    source_files = {}
    for item in [report["dylib"], *report["graphicsNativeLibraries"]]:
        source = Path(item["path"]).resolve(strict=True)
        verified = validate_dylib(source, simulator=True)
        if verified["sha256"] != item["sha256"] or source.name in source_files:
            p.error(f"Changed or duplicate native input: {source.name}")
        source_files[source.name] = source, verified["sha256"]
    required = {"client-graph.dylib", "libglfw.dylib", "liblwjgl.dylib", "libfaot_metal.dylib", "libopenal.dylib"}
    if source_files.keys() != required:
        p.error("Expected the real client and all four graphics/audio libraries")
    present = report["metalShaderLibrary"]
    present_path = Path(present["path"]).resolve(strict=True)
    if present_path.name != "fabricaot-present.metallib" or sha256(present_path) != present["sha256"]:
        p.error("Changed presentation shader library")
    source_files[present_path.name] = present_path, present["sha256"]
    bundle = validate_shader_bundle(Path(report["shaderBundle"]["path"]), simulator=True)
    if bundle["filesSHA256"] != report["shaderBundle"]["filesSHA256"]:
        p.error("Changed vanilla shader bundle")
    for name, fingerprint in bundle["filesSHA256"].items():
        source_files[f"fabricaot-shaders/{name}"] = Path(bundle["path"]) / name, fingerprint

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for name, (source, fingerprint) in source_files.items():
        destination = out / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, destination)
        if sha256(destination) != fingerprint:
            raise ValueError(f"Copy failed fingerprint verification: {name}")
    result = {"status": "WORLD_SIMULATOR_XCODE_INPUT_STAGED", "harnessSHA256": sha256(manifest),
              "filesSHA256": {name: value[1] for name, value in source_files.items()}}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    register_tree(out, [sys.executable, "-B", str(Path(__file__).resolve()),
                        "--harness", str(manifest.parent), "--output", str(out)])
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
