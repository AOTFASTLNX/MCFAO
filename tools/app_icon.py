#!/usr/bin/env python3
"""Turn the user's own artwork into the iOS app icon Xcode packages.

The iPhone bundle previously had no icon asset at all, so Xcode shipped a blank
square. This module compiles the chosen icon for the WorldDevice target, either
an Icon Composer document (.icon) or a single image. Images are decoded by a
small AppKit helper, which covers SVG, HEIC, WebP and the other ImageIO formats
in addition to plain PNG/JPEG.

The result is an asset catalog compiled by actool plus the Info.plist icon
keys. Xcode's Custom App Icon build phase installs that directory into the
staged app before signing. Nothing is uploaded; the source file is only read.
See docs/DESKTOP.md for the UI contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import subprocess
import sys

from mcfao import ROOT, sha256, write_json
from mod_file_policy import is_metadata

IMAGE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp", ".gif", ".tif",
    ".tiff", ".bmp", ".svg", ".pdf", ".icns", ".ico",
}
ICON_NAME = "AppIcon"
ICON_POINT_SIZE = 1024
MAX_ICON_BYTES = 32 * 1024 ** 2
RENDERER = ROOT / "tools" / "app_icon_render.m"
MINIMUM_TARGET = "17.0"


def icon_path(value) -> Path:
    """Resolve a user-supplied icon path and reject anything unsupported."""
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("请选择图标文件")
    if len(value) > 4096 or any(ord(c) in (0, 10, 13) for c in value):
        raise ValueError("图标路径无效")
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise ValueError("找不到图标文件：" + str(path))
    suffix = path.suffix.lower()
    if suffix == ".icon":
        if not path.is_dir() or not (path / "icon.json").is_file():
            raise ValueError("图标文档需要包含 icon.json：" + str(path))
        return path
    if suffix not in IMAGE_SUFFIXES:
        raise ValueError("图标需要 .icon 文档或 PNG / JPEG / HEIC / WebP / GIF / TIFF / BMP / SVG / PDF / ICNS / ICO 图片")
    if not path.is_file():
        raise ValueError("找不到图标文件：" + str(path))
    if path.stat().st_size > MAX_ICON_BYTES:
        raise ValueError("图标图片不能超过 32 MiB")
    if path.stat().st_size == 0:
        raise ValueError("图标图片为空")
    return path


def source_facts(path: Path) -> dict:
    """Fingerprint the chosen icon so a build can detect a changed file."""
    if path.suffix.lower() == ".icon":
        files = {}
        for item in sorted(path.rglob("*")):
            if item.is_symlink():
                raise ValueError("图标文档不能包含符号链接：" + str(item))
            if item.is_file():
                files[str(item.relative_to(path))] = sha256(item)
        if not files:
            raise ValueError("图标文档为空")
        return {"kind": "icon", "name": path.name, "files": files,
                "sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}
    return {"kind": "image", "name": path.name, "bytes": path.stat().st_size,
            "sha256": sha256(path)}


def icon_document_name(document: Path) -> str:
    """Icon Composer names the compiled asset after the document itself."""
    try:
        facts = json.loads((document / "icon.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("图标文档的 icon.json 无法读取：" + str(error)) from error
    if not isinstance(facts, dict):
        raise ValueError("图标文档的 icon.json 不是对象")
    name = document.stem
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
        raise ValueError("图标文档名称只能包含字母、数字、下划线、点和连字符")
    return name


def renderer() -> Path:
    """Build the AppKit helper once per source revision; it is not shipped."""
    from storage_config import cache_path
    cache = cache_path("app-icon")
    cache.mkdir(parents=True, exist_ok=True)
    binary = cache / "app_icon_render"
    stamp = cache / "app_icon_render.sha256"
    digest = sha256(RENDERER)
    if binary.is_file() and stamp.is_file() and stamp.read_text().strip() == digest:
        return binary
    result = subprocess.run(
        ["/usr/bin/xcrun", "--sdk", "macosx", "clang", "-fobjc-arc", "-O2",
         "-framework", "AppKit", "-framework", "Foundation",
         str(RENDERER), "-o", str(binary)],
        capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError("无法编译图标渲染辅助程序：\n" + (result.stderr or result.stdout)[-2000:])
    stamp.write_text(digest + "\n")
    return binary


def render_image(source: Path, output: Path, fit="fit", background="transparent", padding=0):
    """Normalise any supported image to a 1024 px PNG via AppKit/ImageIO."""
    if fit not in ("fit", "fill"):
        raise ValueError("图标缩放方式无效")
    if background != "transparent" and not re.fullmatch(r"#[0-9A-Fa-f]{6}", background):
        raise ValueError("图标背景色无效")
    if not isinstance(padding, int) or not 0 <= padding <= 30:
        raise ValueError("图标留白需要在 0 到 30% 之间")
    result = subprocess.run(
        [str(renderer()), "--input", str(source), "--output", str(output),
         "--size", str(ICON_POINT_SIZE), "--fit", fit, "--background", background,
         "--padding", str(padding)],
        capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise ValueError("无法读取图标图片：\n" + (result.stderr or result.stdout)[-2000:])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def render_preview(value, output: Path, fit="fit", background="transparent", padding=0) -> dict:
    """Render a 1024 px PNG preview for either an image or an .icon document."""
    source = icon_path(value)
    output = Path(output)
    if source.suffix.lower() != ".icon":
        render_image(source, output, fit=fit, background=background, padding=padding)
        return {"kind": "image", "preview": str(output)}
    work = output.parent / (".preview-" + output.stem)
    if work.exists():
        raise ValueError("预览目录已存在：" + str(work))
    work.mkdir(parents=True)
    result = subprocess.run(
        ["/usr/bin/xcrun", "actool", "--compile", str(work),
         "--platform", "macosx", "--minimum-deployment-target", "11.0",
         "--app-icon", icon_document_name(source), "--standalone-icon-behavior", "all",
         "--output-partial-info-plist", str(work / "partial.plist"),
         "--warnings", "--errors", str(source)],
        capture_output=True, text=True, timeout=900)
    icns = next(iter(sorted(
        path for path in work.glob("*.icns") if not is_metadata(path.name))), None)
    try:
        if result.returncode or icns is None:
            raise ValueError("图标预览编译失败：" + (result.stderr or result.stdout)[-1200:])
        # actool writes the macOS representation as an .icns whose members are
        # indexed PNGs; sips cannot always re-read that container, so unpack it.
        # ExFAT volumes add AppleDouble sidecars, so skip macOS metadata above.
        members = icns_members(icns)
        if not members:
            raise ValueError("图标预览编译结果中没有可用的 PNG")
        output.write_bytes(max(members, key=len))
        if not output.is_file() or output.stat().st_size == 0:
            raise ValueError("图标预览写入失败：" + str(output))
    finally:
        # The preview is a cache entry, not evidence: drop the intermediate
        # bundle. actool may remove its own AppleDouble sidecars while this
        # runs, so an entry that already vanished is not an error.
        for leftover in sorted(work.rglob("*"), reverse=True):
            try:
                if leftover.is_dir() and not leftover.is_symlink():
                    leftover.rmdir()
                else:
                    leftover.unlink()
            except FileNotFoundError:
                pass
        try:
            work.rmdir()
        except FileNotFoundError:
            pass
    return {"kind": "icon", "preview": str(output)}


def icns_members(path: Path) -> list:
    """Return the PNG payloads embedded in an ICNS file."""
    data = path.read_bytes()
    if len(data) < 8 or data[:4] != b"icns":
        return []
    found, offset = [], 8
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        length = int.from_bytes(data[offset + 4:offset + 8], "big")
        if length < 8 or offset + length > len(data):
            break
        payload = data[offset + 8:offset + length]
        if payload[:8] == b"\x89PNG\r\n\x1a\n":
            found.append(payload)
        offset += length
    return found


def appiconset(source: Path, destination: Path, *, fit="fit", background="transparent", padding=0):
    """Write an AppIcon.appiconset for either an image or a compiled .icon."""
    destination.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".icon":
        name = icon_document_name(source)
        rendered = None
    else:
        name = ICON_NAME
        rendered = render_image(source, destination / "icon-1024.png",
                                fit=fit, background=background, padding=padding)
    images = [{"filename": "icon-1024.png", "idiom": "universal", "platform": "ios",
               "size": "1024x1024"}] if rendered else []
    write_json(destination / "Contents.json", {
        "images": images,
        "info": {"author": "xcode", "version": 1},
    })
    write_json(destination.parent / "Contents.json",
               {"info": {"author": "xcode", "version": 1}})
    return name, rendered


def icon_artifacts(name: str) -> tuple:
    return ("Assets.car", name + "60x60@2x.png", name + "76x76@2x~ipad.png")


def compile_icon(source: Path, output: Path, name: str, *, log: Path | None = None) -> dict:
    """Run actool for either input form and return the partial Info.plist keys."""
    output.mkdir(parents=True, exist_ok=True)
    partial = output / "partial.plist"
    target = source if source.suffix.lower() == ".icon" else output / "Assets.xcassets"
    argv = ["/usr/bin/xcrun", "actool", "--compile", str(output),
            "--platform", "iphoneos", "--minimum-deployment-target", MINIMUM_TARGET,
            "--app-icon", name, "--output-partial-info-plist", str(partial),
            "--warnings", "--errors", str(target)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=900)
    if log is not None:
        log.write_text((result.stdout or "") + "\n" + (result.stderr or ""))
    if result.returncode:
        errors = []
        if partial.is_file():
            try:
                errors = [row.get("description", "") for row in
                          plistlib.loads(partial.read_bytes()).get("com.apple.actool.errors", [])]
            except (OSError, plistlib.InvalidFileException, ValueError):
                errors = []
        detail = "\n".join(filter(None, errors)) or (result.stderr or result.stdout)[-1200:]
        raise ValueError("图标编译失败：\n" + detail)
    if not partial.is_file():
        raise ValueError("图标编译未生成 Info.plist 片段")
    keys = plistlib.loads(partial.read_bytes())
    if "CFBundleIcons" not in keys:
        raise ValueError("图标编译结果未声明 iOS 图标")
    for artifact in icon_artifacts(name):
        if not (output / artifact).is_file():
            raise ValueError("图标编译缺少 " + artifact)
    return keys


def prepare(value, output: Path, *, fit="fit", background="transparent", padding=0) -> dict:
    """Compile the icon into a fresh directory and describe the result.

    The caller passes the compiled directory to Xcode as FAOT_APP_ICON_DIR, so
    the same catalog is installed by the build phase for signed and unsigned
    builds alike.
    """
    source = icon_path(value)
    output = Path(output)
    if output.exists():
        raise ValueError("图标输出目录已存在：" + str(output))
    output.mkdir(parents=True)
    compiled = output / "compiled"
    catalog = compiled / "Assets.xcassets"
    name, rendered = appiconset(source, catalog / "AppIcon.appiconset",
                                fit=fit, background=background, padding=padding)
    keys = compile_icon(source, compiled, name, log=output / "actool.log")
    facts = source_facts(source)
    facts.update(assetName=name, catalog=str(catalog), compiled=str(compiled),
                 rendered=rendered, fit=fit, background=background, padding=padding,
                 info=keys)
    write_json(output / "result.json", facts)
    return facts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icon", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="Write the compiled catalog and its manifest here")
    parser.add_argument("--fit", choices=("fit", "fill"), default="fit")
    parser.add_argument("--background", default="transparent")
    parser.add_argument("--padding", type=int, default=0)
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.icon, args.output, fit=args.fit,
                             background=args.background, padding=args.padding),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
