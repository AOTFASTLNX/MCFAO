#!/usr/bin/env python3
"""Disable Minecraft's 4.5 direct-state path for the OpenGL 4.1 renderer."""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

from bootstrap_toolchain import sha256
from build_method_splitter import java_home
from capture import ROOT, capture
from graphics_common import register_tree


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--graalvm-home", type=Path)
    parser.add_argument("--asm-jars", type=Path, nargs=2, metavar=("ASM_CORE", "ASM_TREE"))
    args = parser.parse_args(argv)
    client = args.client.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    home = args.graalvm_home.resolve(strict=True) if args.graalvm_home else java_home()
    asm = [path.resolve(strict=True) for path in (args.asm_jars or (ROOT / ".cache/libs/asm-9.9/asm-9.9.jar", ROOT / ".cache/libs/asm-9.9/asm-tree-9.9.jar"))]
    classes = out / "classes"
    classes.mkdir()
    source = ROOT / "compiler/gl41/tools/fabricaot/gl41/PatchDevice.java"
    classpath = os.pathsep.join(map(str, asm))
    compiled = capture([str(home / "bin/javac"), "--release", "25", "-proc:none", "-cp", classpath,
                        "-d", str(classes), str(source)], out / "compile", 120)
    if compiled["exitCode"]:
        raise RuntimeError("PatchDevice compilation failed")
    target = out / "client.jar"
    run = capture([str(home / "bin/java"), "-cp", str(classes) + os.pathsep + classpath,
                   "fabricaot.gl41.PatchDevice", str(client), str(target)], out / "transform", 120)
    if run["exitCode"] or "GL41_DIRECT_STATE_DISABLED" not in (out / "transform/stdout.log").read_text():
        raise RuntimeError("GlDevice patch failed")
    with zipfile.ZipFile(client) as before, zipfile.ZipFile(target) as after:
        names_before = before.namelist()
        names_after = after.namelist()
        if names_before != names_after:
            raise ValueError("GlDevice patch changed the entry list")
        changed = [name for name in names_before if before.read(name) != after.read(name)]
        if changed != ["com/mojang/blaze3d/opengl/GlDevice.class",
                       "net/minecraft/client/multiplayer/LevelLoadTracker$WaitingForServer.class",
                       "net/minecraft/client/multiplayer/LevelLoadTracker.class"]:
            raise ValueError("Unexpected patched entries: " + repr(changed))
    result = {"status": "GL41_CLIENT_PATCHED", "client": str(client), "clientSHA256": sha256(client),
              "outputJar": str(target), "outputJarSHA256": sha256(target),
              "changedEntries": changed, "directStateAccess": "disabled for the 4.1 OSMesa surface",
              "scope": "build-time bytecode adaptation; no game execution"}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    register_tree(out, [sys.executable, "-B", str(Path(__file__).resolve()),
                        *(sys.argv[1:] if argv is None else argv)])
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
