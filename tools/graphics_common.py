"""Shared graphics build evidence and central registration; no private registry."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path
from capture import ROOT
from bootstrap_toolchain import sha256

def metal_source_hashes():
    sources=sorted((ROOT/"compiler/metal-backend/src").rglob("*.java"))
    sources.extend(ROOT/path for path in (
        "interop/graphics/MetalProbe.java",
        "interop/graphics/MetalResourceProbe.java",
        "interop/graphics/NativeImageProbe.java",
        "interop/graphics/MetalDrawProbe.java",
        "ios/metal-bridge/metal_bridge.m",
        "ios/metal-bridge/present.metal",
        "ios/metal-bridge/texture_transfer.h",
        "interop/graphics/TextureSpecProbe.java",
        "interop/graphics/texture_transfer_test.c",
    ))
    return {str(path.relative_to(ROOT)):sha256(path) for path in sources}

def verify_source_manifest(recorded: dict, current: dict):
    if not isinstance(recorded,dict) or recorded!=current:
        missing=sorted(set(current)-(set(recorded) if isinstance(recorded,dict) else set()))
        stale=sorted(key for key,value in (recorded.items() if isinstance(recorded,dict) else ())
                     if current.get(key)!=value)
        extra=sorted(set(recorded)-set(current)) if isinstance(recorded,dict) else []
        details=[]
        if stale:details.append("changed: "+", ".join(stale))
        if missing:details.append("unrecorded: "+", ".join(missing))
        if extra:details.append("unknown: "+", ".join(extra))
        raise ValueError("Metal source fingerprints do not match current sources ("+"; ".join(details)+")")

def verify_metal_artifact(directory: Path) -> dict:
    directory=directory.resolve(strict=True)
    report=json.loads((directory/"result.json").read_text())
    if report.get("status")!="METAL_BOOTSTRAP_BUILT":
        raise ValueError("A successfully built Metal backend is required")
    verify_source_manifest(report.get("sourcesSHA256"),metal_source_hashes())
    for filename,key in (("metal-backend.jar","jarSHA256"),
                         ("libfaot_metal.dylib","binarySHA256"),
                         ("fabricaot-present.metallib","metallibSHA256")):
        if sha256(directory/filename)!=report.get(key):
            raise ValueError("Metal build artifact hash mismatch: "+str(directory/filename))
    return report

def bridge_overlays(directory: Path) -> list[Path]:
    directory=directory.resolve(strict=True)
    report=json.loads((directory/"result.json").read_text())
    if report.get("status")!="STATIC_JNI_BRIDGE_BUILT":
        raise ValueError("A successfully built static JNI bridge is required")
    paths=[directory/"lwjgl-ios.jar",directory/"lwjgl-glfw-ios.jar"]
    for name in ('lwjgl-stb-ios.jar','lwjgl-openal-ios.jar'):
        if str(directory/name) in report["overlaysSHA256"]:paths.append(directory/name)
    for path in paths:
        if sha256(path)!=report["overlaysSHA256"].get(str(path)):
            raise ValueError("Modified graphics overlay: "+str(path))
    return paths

def register_tree(path: Path, command: list[str], *, regenerable: bool = True, kind: str = "BUILD", recursive: bool = True) -> dict:
    if os.environ.get("AAR_HOME"):
        raise RuntimeError("AAR_HOME must be unset: the central registry is mandatory")
    aar = shutil.which("aar") or str(Path.home() / "Documents/Codex/monitor/bin/aar")
    argv = [aar,"register","--path",str(path.resolve()),"--project",str(ROOT),"--type",kind,
            "--source","First-party graphics build; source and command fingerprints in result.json",
            "--argv-json",json.dumps(command),"--json"]
    if recursive:argv.append("--include-files")
    if regenerable: argv.append("--regenerable")
    result = subprocess.run(argv,capture_output=True,text=True,timeout=120)
    if result.returncode:
        raise RuntimeError(f"Central AAR registration failed ({result.returncode}): {result.stderr or result.stdout}")
    return json.loads(result.stdout)
