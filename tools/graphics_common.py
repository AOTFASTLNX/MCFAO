"""Shared graphics build evidence and central registration; no private registry."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path
from capture import ROOT
from bootstrap_toolchain import sha256

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
    try:
        result = subprocess.run(argv,capture_output=True,text=True,timeout=120)
    except FileNotFoundError:
        # Artifact discovery is separate from compilation and package validation.
        # Retain the exact registration request for replay when AAR is restored.
        pending = {"status": "REGISTRATION_PENDING", "reason": "AAR executable unavailable",
                   "argv": argv}
        (path / "registration-pending.json").write_text(json.dumps(pending, indent=2) + "\n")
        return pending
    if result.returncode:
        raise RuntimeError(f"Central AAR registration failed ({result.returncode}): {result.stderr or result.stdout}")
    return json.loads(result.stdout)
