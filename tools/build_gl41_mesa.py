#!/usr/bin/env python3
"""Build hash-pinned Mesa 25.0.7 with checked OSMesa readback and Vulkan diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

from capture import ROOT
from verified_download import fetch, TOOL_HOSTS

PATCHES = ROOT / "compiler/gl41/patches"
MESA = {"url": "https://archive.mesa3d.org/mesa-25.0.7.tar.xz", "size": 46849080,
        "sha256": "592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6"}
MVK_HEADERS = {"url": "https://codeload.github.com/KhronosGroup/MoltenVK/tar.gz/refs/tags/v1.3.0",
               "size": 1121237,
               "sha256": "9476033d49ef02776ebab288fffae3e28fd627a3e29b7ae5975a1e1c785bf912"}
REQUIREMENTS = ["meson==1.7.2", "ninja==1.11.1.4", "mako==1.3.10", "PyYAML==6.0.2", "packaging==25.0"]
OPTIONS = ["-Dosmesa=true", "-Dgallium-drivers=zink,softpipe", "-Dvulkan-drivers=",
           "-Dvulkan-layers=", "-Dplatforms=", "-Dglx=disabled", "-Degl=disabled",
           "-Dgbm=disabled", "-Dgles1=disabled", "-Dgles2=disabled", "-Dopengl=true",
           "-Dshared-glapi=disabled", "-Dllvm=disabled", "-Dshared-llvm=disabled",
           "-Dexpat=disabled", "-Dxmlconfig=disabled", "-Dvalgrind=disabled",
           "-Dzstd=disabled", "-Dshader-cache=enabled", "-Dbuild-tests=false",
           "-Dvideo-codecs=", "-Dtools=", "-Dlibunwind=disabled"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_identity() -> str:
    h = hashlib.sha256(Path(__file__).read_bytes())
    for p in sorted(PATCHES.iterdir()):
        if p.is_file():
            h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()


def unpack(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as tar:
        # Python's data filter rejects escaping links and absolute/traversal paths.
        tar.extractall(destination, filter="data")


def run(argv: list[str], out: Path, name: str, **kwargs) -> None:
    (out / (name + ".argv.json")).write_text(json.dumps(argv, indent=2) + "\n")
    with (out / (name + ".log")).open("w") as log:
        subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True, **kwargs)


def build(output: Path, jobs: int = 8) -> Path:
    output = output.resolve()
    identity = patch_identity()
    binary = output / "libOSMesa.8.dylib"
    manifest = output / "result.json"
    if manifest.exists():
        result = json.loads(manifest.read_text())
        if (binary.is_file() and result.get("patchIdentity") == identity
                and digest(binary) == result.get("sha256")):
            return binary
        raise ValueError("Mesa cache inputs or binary changed; use a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    # Meson scans *.wrap and Python scans *.dist-info; AppleDouble siblings on
    # exFAT are not valid inputs. Build in disposable OS-local scratch space.
    workspace = Path(tempfile.gettempdir()) / "ncl-mesa-work" / hashlib.sha256(str(output).encode()).hexdigest()[:20]
    source = workspace / "source"
    source.mkdir(parents=True, exist_ok=True)
    downloads = output / "downloads"
    downloads.mkdir(exist_ok=True)
    for name, spec in [("mesa.tar.xz", MESA), ("mvk.tar.gz", MVK_HEADERS)]:
        archive = downloads / name
        fetch(spec, archive, hosts=TOOL_HOSTS | {"archive.mesa3d.org"})
        unpack(archive, source)
    mesa = source / "mesa-25.0.7"
    run(["patch", "-p1", "-i", str(PATCHES / "mesa-25.0.7-safe-readback.patch")], output, "patch", cwd=mesa)
    for name in ["ncl_diag.h", "ncl_diag_impl.h"]:
        shutil.copy2(PATCHES / name, mesa / "src/gallium/drivers/zink" / name)
    sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
    cross = output / "ios.ini"
    lines = ["[binaries]"]
    for language, compiler in [("c", "clang"), ("cpp", "clang++"), ("objc", "clang")]:
        lines.append(f"{language} = " + repr([compiler, "-target", "arm64-apple-ios17.0", "-isysroot", sdk]))
    lines += ["ar = 'ar'", "strip = 'strip'", "pkg-config = 'pkg-config'", "[host_machine]",
              "system = 'darwin'", "cpu_family = 'aarch64'", "cpu = 'aarch64'", "endian = 'little'",
              "[properties]", "needs_exe_wrapper = true", "pkg_config_libdir = ['/nonexistent']",
              "[built-in options]",
              "c_args = ['-DVK_USE_PLATFORM_METAL_EXT=1', '-DVK_USE_PLATFORM_IOS_MVK=1']",
              "cpp_args = ['-DVK_USE_PLATFORM_METAL_EXT=1', '-DVK_USE_PLATFORM_IOS_MVK=1']"]
    cross.write_text("\n".join(lines) + "\n")
    # Python package metadata is not safe on AppleDouble-producing filesystems.
    # Keep only disposable build tools in the OS temporary directory; artifacts
    # and source remain at the caller-selected storage location.
    tools_key = hashlib.sha256("\n".join(REQUIREMENTS).encode()).hexdigest()[:16]
    venv = Path(tempfile.gettempdir()) / "ncl-mesa-tools" / tools_key
    if not (venv / "ncl-ready.json").exists():
        run([sys.executable, "-m", "venv", str(venv)], output, "venv")
        run([str(venv / "bin/pip"), "install", *REQUIREMENTS], output, "dependencies")
        (venv / "ncl-ready.json").write_text(json.dumps(REQUIREMENTS))
    env = dict(os.environ, PATH=str(venv / "bin") + os.pathsep + os.environ["PATH"])
    for name in ("CFLAGS", "CXXFLAGS", "OBJCFLAGS", "CPPFLAGS", "LDFLAGS", "PKG_CONFIG_PATH"):
        env.pop(name, None)
    builddir = workspace / "mesa-build"
    run([str(venv / "bin/meson"), "setup", str(builddir), str(mesa), "--cross-file", str(cross),
         "--buildtype=release", *OPTIONS,
         "-Dmoltenvk-dir=" + str(source / "MoltenVK-1.3.0/MoltenVK")], output, "setup", env=env)
    # Build only the requested runtime; no bundled third-party Mod build scripts execute.
    run([str(venv / "bin/ninja"), "-C", str(builddir), "-j", str(jobs),
         "src/gallium/targets/osmesa/libOSMesa.8.dylib"], output, "compile", env=env)
    shutil.copy2(builddir / "src/gallium/targets/osmesa/libOSMesa.8.dylib", binary)
    run(["xcrun", "install_name_tool", "-id", "@rpath/libOSMesa.8.dylib", str(binary)], output, "install-name")
    symbols = subprocess.check_output(["xcrun", "nm", "-gUj", str(binary)], text=True)
    if "_OSMesaGetLastReadbackError" not in symbols.split():
        raise RuntimeError("Patched OSMesa safety ABI missing")
    shutil.copy2(mesa / "docs/license.rst", output / "LICENSE-Mesa.rst")
    manifest.write_text(json.dumps({"status": "MESA_IOS_BUILT", "version": "25.0.7",
                                   "patchIdentity": identity, "sha256": digest(binary),
                                   "source": MESA, "headers": MVK_HEADERS,
                                   "buildWorkspace": str(workspace),
                                   "scope": "iOS arm64 build; device acceptance recorded separately"}, indent=2) + "\n")
    return binary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args(argv)
    print(build(args.output, args.jobs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
