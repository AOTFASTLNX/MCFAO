#!/usr/bin/env python3
"""Apply strictly checked, CI-only host portability fixes to a disposable source checkout.

Never modify the actual Git checkout or omit a required patch on a mismatch.
This script intentionally does not revert the integrated AOT/Metal/pointer implementations.
"""
from __future__ import annotations

import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: python3 ci/patch_src.py <disposable-source-checkout>")
ROOT = Path(sys.argv[1]).resolve(strict=True)
if not (ROOT / "compiler/fabric.lock.json").is_file():
    raise SystemExit("Not an MCFAO source checkout")


def replace(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    original = path.read_text(encoding="utf-8")
    if original.count(old) != 1:
        if original.count(new) == 1:
            print(f"already adapted: {rel}")
            return
        raise SystemExit(f"CI portability patch drift: {rel}, expected 1 exact source anchor, found {original.count(old)}")
    path.write_text(original.replace(old, new), encoding="utf-8")
    print(f"adapted: {rel}")


def replace_all(rel: str, old: str, new: str, expected: int) -> None:
    path = ROOT / rel
    original = path.read_text(encoding="utf-8")
    count = original.count(old)
    if count == 0 and original.count(new) == expected:
        print(f"already adapted: {rel}")
        return
    if count != expected:
        raise SystemExit(f"CI portability patch drift: {rel}, expected {expected} occurrences, found {count}")
    path.write_text(original.replace(old, new), encoding="utf-8")
    print(f"adapted: {rel} ({expected} replacements)")


# The Gradle distribution is absent in CircleCI; build_method_splitter.py can
# download the pinned ASM jars into the local cache and use those exact files.
replace(
    "tools/build_method_splitter.py",
    "    found = {}\n    for pattern in patterns:",
    '    found = {}\n'
    '    for artifact in ("asm", "asm-tree"):\n'
    '        name = "%s-%s.jar" % (artifact, ASM_VERSION)\n'
    '        cached = CACHE / name\n'
    '        if cached.is_file():\n'
    '            found[name] = cached\n'
    '    for pattern in patterns:'
)
replace(
    "tools/build_method_splitter.py",
    'for artifact in ("asm-analysis", "asm-util"):',
    'for artifact in ("asm", "asm-tree", "asm-analysis", "asm-util"):'
)

# Only CI gets the AAR shim. Toolchain downloads still use the lockfile hashes.
replace(
    "tools/prepare_shader_toolchain.py",
    "aar=str(Path.home() / 'Documents/Codex/monitor/bin/aar');command=[sys.executable,'-B',str(Path(__file__).resolve()),'--cache-only']",
    "aar=shutil.which('aar');\n    if not aar:raise RuntimeError('CI AAR shim missing');\n    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--cache-only']"
)
replace(
    "tools/prepare_shader_toolchain.py",
    "'/Library/Apple/System','/Applications/Xcode.app',CACHE,work",
    "'/Library/Apple/System','/Applications',CACHE,work"
)
replace(
    "tools/prepare_shader_toolchain.py",
    "env={'PYTHONDONTWRITEBYTECODE':'1','DEVELOPER_DIR':'/Applications/Xcode.app/Contents/Developer'}",
    "env={'PYTHONDONTWRITEBYTECODE':'1','DEVELOPER_DIR':'/Applications/Xcode.app/Contents/Developer','TMPDIR':str(work/'tmp')}"
)
replace(
    "tools/build_openal_soft.py",
    "env={'SDKROOT':sdk,'DEVELOPER_DIR':'/Applications/Xcode.app/Contents/Developer','PYTHONDONTWRITEBYTECODE':'1'}",
    "env={'SDKROOT':sdk,'DEVELOPER_DIR':'/Applications/Xcode.app/Contents/Developer','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(work)}"
)
replace(
    "tools/prepare_b0.py",
    '    baseline = ROOT / "artifacts/evidence/a0-desktop-reference"',
    '    baseline = Path(__import__("os").environ.get("MCFAO_A0") or ROOT / "artifacts/evidence/a0-desktop-reference")'
)
replace_all(
    "ios/glfw-lite/uikit_surface.m",
    "NSThread.isMainThread",
    "[NSThread isMainThread]",
    4,
)

# The AOT branch ALREADY implements SharedArenaSupport, auto reflection,
# constructor-safe method splitting and unique helper names. Do not override them
# with stale patches designed for an older source branch.
graph=(ROOT / "tools/probe_client_graph.py").read_text()
assert '-H:+SharedArenaSupport' in graph and 'reflection_from_jar' in graph
assert 'MCFAO_OPT_LEVEL' in graph
print("CI patches applied: original integrated AOT and pointer paths retained")
