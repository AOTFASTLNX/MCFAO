#!/usr/bin/env python3
"""Offline, fail-closed *metadata preflight* for FabricAOT Minecraft 26.1.2.

This deliberately does not download files, execute Java, unpack modpacks, resolve
Fabric dependencies or certify that a mod can run on iOS/AOT. Treat all inputs
as untrusted, including local Prism directories and nested JARs.
"""
from __future__ import annotations

import argparse
import io
import ipaddress
import json
import re
import stat
import sys
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

TARGET_MINECRAFT = "26.1.2"
MAX_MANIFEST = 2 * 1024 * 1024
MAX_MOD_METADATA = 512 * 1024
MAX_EMBEDDED_JAR = 64 * 1024 * 1024
MAX_ENTRIES = 10_000
MAX_TOTAL_UNCOMPRESSED = 4 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 500


def finding(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}


def safe_archive_path(raw: object) -> bool:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        return False
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return False
    if any(ord(c) < 32 for c in raw):
        return False
    return all(piece not in ("", ".", "..") for piece in raw.split("/"))


def _json_no_duplicate_keys(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = val
    return result


def _parse_json_bytes(data: bytes, name: str):
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_json_no_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON in {name}: {exc}") from exc


def read_json_limited(archive: zipfile.ZipFile, name: str, size_limit: int):
    item = archive.getinfo(name)
    if item.file_size > size_limit:
        raise ValueError(f"{name} exceeds {size_limit} bytes")
    # Bounded streaming read rather than relying solely on ZIP header values.
    with archive.open(item) as inp:
        content = inp.read(size_limit + 1)
    if len(content) > size_limit:
        raise ValueError(f"{name} expanded beyond the allowed size")
    return _parse_json_bytes(content, name)


def _canonical(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def validate_zip_members(archive: zipfile.ZipFile, findings: list, label: str) -> bool:
    """Inspect ZIP directory entries before reading user-controlled members."""
    fatal = False
    members = archive.infolist()
    if len(members) > MAX_ENTRIES:
        findings.append(finding("error", "ZIP_ENTRY_LIMIT", f"{label}: too many ZIP entries"))
        return False
    seen = set()
    total = 0
    for item in members:
        name = item.filename[:-1] if item.is_dir() else item.filename
        if not safe_archive_path(name):
            findings.append(finding("error", "UNSAFE_PATH", f"{label}: {item.filename!r}"))
            fatal = True
            continue
        key = _canonical(name)
        if key in seen:
            findings.append(finding("error", "ZIP_PATH_COLLISION", f"{label}: {item.filename!r}"))
            fatal = True
        seen.add(key)
        if stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK:
            findings.append(finding("error", "ZIP_SYMLINK", f"{label}: {item.filename!r}"))
            fatal = True
        total += item.file_size
        if (not item.is_dir() and item.file_size > 1024 * 1024
                and item.file_size / max(item.compress_size, 1) > MAX_COMPRESSION_RATIO):
            findings.append(finding("error", "SUSPICIOUS_COMPRESSION", f"{label}: {item.filename!r}"))
            fatal = True
    if total > MAX_TOTAL_UNCOMPRESSED:
        findings.append(finding("error", "ZIP_SIZE_LIMIT", f"{label}: total expanded bytes too large"))
        fatal = True
    return not fatal


def _check_download_url(value: object) -> bool:
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        return False
    try:
        url = urlsplit(value)
        if url.scheme.lower() != "https" or not url.hostname or url.username or url.password:
            return False
        if url.port is not None and url.port != 443:
            return False
        hostname = url.hostname
        if hostname in ("localhost",) or hostname.endswith((".local", ".localhost", ".internal")):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            return True  # The downloader MUST still verify DNS/redirect targets.
        return ip.is_global
    except ValueError:
        return False


def _validate_manifest_files(files: object, findings: list) -> list:
    if not isinstance(files, list):
        findings.append(finding("error", "INVALID_FILE_LIST", "Manifest files must be a list"))
        return []
    if len(files) > MAX_ENTRIES:
        findings.append(finding("error", "MANIFEST_ENTRY_LIMIT", "Too many manifest entries"))
        return []
    seen = set()
    result = []
    for idx, entry in enumerate(files):
        if not isinstance(entry, dict):
            findings.append(finding("error", "INVALID_MANIFEST_ENTRY", f"files[{idx}] must be an object"))
            continue
        name = entry.get("path")
        if not safe_archive_path(name):
            findings.append(finding("error", "UNSAFE_MANIFEST_PATH", f"files[{idx}]: {name!r}"))
            continue
        canonical = _canonical(name)
        if canonical in seen:
            findings.append(finding("error", "MANIFEST_PATH_COLLISION", f"files[{idx}]: {name!r}"))
        seen.add(canonical)
        hashes = entry.get("hashes")
        if not isinstance(hashes, dict) or not (isinstance(hashes.get("sha1"), str) and re.fullmatch(r"[a-fA-F0-9]{40}", hashes["sha1"]) and isinstance(hashes.get("sha512"), str) and re.fullmatch(r"[a-fA-F0-9]{128}", hashes["sha512"])):
            findings.append(finding("error", "INVALID_HASH_METADATA", f"files[{idx}]: require sha1 and sha512"))
        urls = entry.get("downloads")
        if not isinstance(urls, list) or not urls or not all(_check_download_url(url) for url in urls):
            findings.append(finding("error", "UNSAFE_DOWNLOAD_URL", f"files[{idx}]: missing or unsafe HTTPS URL"))
        if "fileSize" in entry and (type(entry["fileSize"]) is not int or entry["fileSize"] < 0):
            findings.append(finding("error", "INVALID_FILE_SIZE", f"files[{idx}]: invalid fileSize"))
        env = entry.get("env", {})
        if not isinstance(env, dict) or any(side in env and env[side] not in ("required", "optional", "unsupported") for side in ("client", "server")):
            findings.append(finding("error", "INVALID_ENV", f"files[{idx}]: invalid env"))
        if isinstance(env, dict) and env.get("client") == "unsupported":
            findings.append(finding("info", "SERVER_ONLY_DOWNLOAD", f"files[{idx}]: skip on iOS client"))
        result.append(entry)
    return result


def scan_mod_bytes(content: bytes, jar_name: str, findings: list, mods: list):
    if len(content) > MAX_EMBEDDED_JAR:
        findings.append(finding("warning", "JAR_TOO_LARGE", jar_name))
        return
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if not validate_zip_members(archive, findings, jar_name):
                return
            if "fabric.mod.json" not in archive.namelist():
                findings.append(finding("warning", "NO_FABRIC_META", f"{jar_name}: fabric.mod.json not found"))
                return
            meta = read_json_limited(archive, "fabric.mod.json", MAX_MOD_METADATA)
            if not isinstance(meta, dict):
                raise ValueError("fabric.mod.json must be an object")
            mod_id, version = meta.get("id"), meta.get("version")
            if not isinstance(mod_id, str) or not mod_id or not isinstance(version, str) or not version:
                raise ValueError("fabric.mod.json lacks valid id/version")
            nested = meta.get("jars", [])
            if not isinstance(nested, list):
                raise ValueError("fabric.mod.json jars must be a list")
            if any(not isinstance(j, dict) or not safe_archive_path(j.get("file")) for j in nested):
                raise ValueError("fabric.mod.json has invalid nested JAR path")
            native_names = [n for n in archive.namelist() if n.lower().endswith((".dylib", ".dll", ".so", ".jnilib"))]
            mod = {
                "path": jar_name, "id": mod_id, "version": version,
                "environment": meta.get("environment", "*"),
                "has_mixins": bool(meta.get("mixins")),
                "has_entrypoints": bool(meta.get("entrypoints")),
                "has_class_tweaker": bool(meta.get("accessWidener")),
                "has_language_adapters": bool(meta.get("languageAdapters")),
                "nested_jar_count": len(nested), "bundled_native_count": len(native_names),
                "declared_depends": meta.get("depends", {}),
                "aot_compatibility": "NOT_TESTED"
            }
            mods.append(mod)
            if mod["environment"] == "server":
                findings.append(finding("info", "SERVER_MOD", f"{jar_name}: skip on physical iOS client"))
            for key, code in (("has_mixins", "MIXIN_REQUIRES_AOT_WORK"),
                              ("has_class_tweaker", "CLASS_TWEAKER_REQUIRES_AOT_WORK"),
                              ("has_language_adapters", "LANGUAGE_ADAPTER_UNVERIFIED")):
                if mod[key]:
                    findings.append(finding("warning", code, jar_name))
            if nested:
                findings.append(finding("warning", "NESTED_JARS_NOT_SCANNED", f"{jar_name}: {len(nested)} nested JAR(s) require recursive analysis"))
            if native_names:
                findings.append(finding("warning", "NATIVE_LIBRARIES_UNVERIFIED", f"{jar_name}: {len(native_names)} native library file(s)"))
            if mod["has_entrypoints"]:
                findings.append(finding("info", "ENTRYPOINTS_NOT_EXECUTED", jar_name))
    except (ValueError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, OSError) as exc:
        findings.append(finding("error", "INVALID_MOD_JAR", f"{jar_name}: {exc}"))


def scan_pack(path: Path) -> dict:
    findings: list[dict] = []
    mods: list[dict] = []
    result = {
        "source": str(path), "target_minecraft": TARGET_MINECRAFT,
        "status": "STATIC_PREFLIGHT_ONLY", "source_type": "unknown",
        "mods": mods, "findings": findings, "aot_ios_verified": False,
        "fatal": True,
    }
    if not path.exists():
        findings.append(finding("error", "NOT_FOUND", "File or folder not found"))
        return result

    if path.is_file() and path.suffix.lower() == ".mrpack":
        result["source_type"] = "mrpack"
        try:
            with zipfile.ZipFile(path) as archive:
                if not validate_zip_members(archive, findings, str(path)):
                    return result
                manifest = read_json_limited(archive, "modrinth.index.json", MAX_MANIFEST)
                if not isinstance(manifest, dict):
                    raise ValueError("modrinth.index.json must be a JSON object")
                if manifest.get("formatVersion") != 1:
                    findings.append(finding("error", "INVALID_FORMAT_VERSION", "Expected mrpack formatVersion=1"))
                if manifest.get("game") != "minecraft":
                    findings.append(finding("error", "WRONG_GAME", "Expected Minecraft pack"))
                for required in ("name", "versionId"):
                    if not isinstance(manifest.get(required), str) or not manifest[required]:
                        findings.append(finding("error", "INVALID_MANIFEST", f"Missing {required}"))
                deps = manifest.get("dependencies", {})
                if not isinstance(deps, dict):
                    raise ValueError("Manifest dependencies must be object")
                result["pack_name"] = manifest.get("name")
                result["pack_version"] = manifest.get("versionId")
                if deps.get("minecraft") != TARGET_MINECRAFT:
                    findings.append(finding("error", "WRONG_MC_VERSION", f"Expected {TARGET_MINECRAFT}, got {deps.get('minecraft')!r}"))
                if not isinstance(deps.get("fabric-loader"), str) or not deps["fabric-loader"]:
                    findings.append(finding("error", "NOT_FABRIC", "No Fabric loader declared"))
                else:
                    result["fabric_loader_version"] = deps["fabric-loader"]
                    findings.append(finding("warning", "LOADER_VERSION_UNVERIFIED", "Actual Loader/Minecraft compatibility requires Fabric metadata resolution"))
                if any(k in deps for k in ("forge", "neoforge", "quilt-loader")):
                    findings.append(finding("error", "OTHER_LOADER", "Only Fabric is supported"))
                files = _validate_manifest_files(manifest.get("files"), findings)
                result["manifest_files"] = len(files)
                jar_entries = [m for m in archive.infolist() if not m.is_dir() and m.filename.startswith(("overrides/mods/", "client-overrides/mods/")) and m.filename.lower().endswith(".jar")]
                if len(jar_entries) > 2500:
                    findings.append(finding("error", "TOO_MANY_EMBEDDED_MODS", str(len(jar_entries))))
                    jar_entries = jar_entries[:2500]
                for item in jar_entries:
                    if item.file_size > MAX_EMBEDDED_JAR:
                        findings.append(finding("warning", "JAR_TOO_LARGE", item.filename))
                        continue
                    scan_mod_bytes(archive.read(item), item.filename, findings, mods)
                remote = sum(1 for f in files if isinstance(f.get("path"), str) and f["path"].lower().endswith(".jar") and (not isinstance(f.get("env"), dict) or f["env"].get("client") != "unsupported"))
                if remote:
                    findings.append(finding("warning", "REMOTE_MOD_METADATA_NOT_FETCHED", f"{remote} remotely listed JARs: actual Mod IDs/dependencies/AOT compatibility UNKNOWN"))
        except (ValueError, zipfile.BadZipFile, KeyError, RuntimeError, OSError, MemoryError) as exc:
            findings.append(finding("error", "INVALID_PACK", str(exc)))

    elif path.is_dir():
        result["source_type"] = "prism_or_folder"
        root = path.resolve()
        cfg = path / "mmc-pack.json"
        if cfg.is_symlink():
            findings.append(finding("error", "UNSAFE_PRISM_SYMLINK", str(cfg)))
        elif cfg.exists():
            try:
                if cfg.stat().st_size > MAX_MANIFEST:
                    raise ValueError("Prism manifest too large")
                manifest = _parse_json_bytes(cfg.read_bytes(), str(cfg))
                if not isinstance(manifest, dict) or not isinstance(manifest.get("components"), list):
                    raise ValueError("Prism manifest missing components list")
                components = {str(item.get("uid")): str(item.get("version")) for item in manifest["components"] if isinstance(item, dict)}
                if components.get("net.minecraft") != TARGET_MINECRAFT:
                    findings.append(finding("error", "WRONG_MC_VERSION", f"Expected {TARGET_MINECRAFT}, got {components.get('net.minecraft')!r}"))
                loader = components.get("net.fabricmc.fabric-loader")
                if not loader or loader == "None":
                    findings.append(finding("error", "NOT_FABRIC", "Prism instance has no Fabric loader"))
                else:
                    result["fabric_loader_version"] = loader
                    findings.append(finding("warning", "LOADER_VERSION_UNVERIFIED", "Loader/Minecraft compatibility not resolved offline"))
                if any(uid in components for uid in ("net.minecraftforge", "net.neoforged", "org.quiltmc.quilt-loader")):
                    findings.append(finding("error", "OTHER_LOADER", "Other loader declared"))
            except (ValueError, OSError) as exc:
                findings.append(finding("error", "INVALID_PRISM_METADATA", str(exc)))
        else:
            findings.append(finding("error", "NO_PRISM_META", "Cannot establish Minecraft version or loader"))
        candidates = [path / ".minecraft" / "mods", path / "minecraft" / "mods", path / "mods"]
        selected = next((candidate for candidate in candidates if candidate.is_dir() or candidate.is_symlink()), None)
        if selected:
            if selected.is_symlink() or not selected.resolve().is_relative_to(root):
                findings.append(finding("error", "UNSAFE_MOD_DIRECTORY", str(selected)))
            else:
                jar_paths = sorted(selected.glob("*.jar"))
                if len(jar_paths) > 2500:
                    findings.append(finding("error", "TOO_MANY_MODS", str(len(jar_paths))))
                    jar_paths = jar_paths[:2500]
                for jar in jar_paths:
                    if jar.is_symlink() or not jar.resolve().is_relative_to(root):
                        findings.append(finding("error", "UNSAFE_MOD_SYMLINK", str(jar)))
                        continue
                    try:
                        if jar.stat().st_size > MAX_EMBEDDED_JAR:
                            findings.append(finding("warning", "JAR_TOO_LARGE", jar.name))
                        else:
                            scan_mod_bytes(jar.read_bytes(), jar.name, findings, mods)
                    except OSError as exc:
                        findings.append(finding("error", "MOD_READ_ERROR", f"{jar.name}: {exc}"))
        else:
            findings.append(finding("info", "NO_MOD_DIRECTORY", "No mods folder"))
    else:
        findings.append(finding("error", "UNSUPPORTED_SOURCE", "Expected .mrpack or Prism instance directory"))

    # Static scans are never proof of a playable iOS build or mod compatibility.
    result["fatal"] = any(f["severity"] == "error" for f in findings)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline FabricAOT 26.1.2 metadata preflight (not AOT compatibility certification)")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    report = scan_pack(args.path)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if report["fatal"] else 0


if __name__ == "__main__":
    sys.exit(main())
