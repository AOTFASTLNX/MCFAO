#!/usr/bin/env python3
"""Inventory and reclaim local build storage without touching evidence or user data.

The builder keeps three very different kinds of bytes on disk:

* regenerable caches (toolchain archives, extracted sources, Rust `target`);
* per-build intermediate stages (`aot`, `split`, `link`, `package`, ...) that can be
  rebuilt from the same inputs;
* the artefacts that must survive a cleanup: `result.json`, IPAs, source snapshots and
  every hand-written log under `artifacts/evidence`.

`plan()` only reads. `apply()` refuses to delete anything that is not part of the plan
it was given, refuses while a desktop build is running, and never follows symlinks.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import storage_scan  # noqa: E402  (local tool module)

# Stage directories written by `tools/mcfao.py` for every build attempt.
INTERMEDIATE_STAGES = (
    "fabric", "split", "metal-injection", "gl41-patch", "aot", "runtime",
    "link", "stage", "package", "verify",
)

# Never deleted, at any depth, by any group.
PROTECTED_NAMES = {"result.json", "inputs.json", "job.json", "source.json",
                   "import.json", "checkpoint.json", "archive.json"}
PROTECTED_SUFFIXES = (".ipa", ".xcarchive")

CACHE_CHILDREN = ("upstream", "graphics", "toolchains", "apple-metal", "libs")


def human(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def tree_bytes(path: Path) -> int:
    """Allocated bytes, without following links.

    Uses the shared iterative scanner so one traversal reports the size, the
    file count and the ``.ipa`` presence that the planner needs, instead of
    three separate recursive walks. An unreadable tree returns its partial
    total; callers that must not under-report use ``measure_tree``.
    """
    return measure_tree(Path(path)).bytes


def measure_tree(path: Path) -> "storage_scan.ScanResult":
    return storage_scan.scan(path)


def free_bytes(path: Path) -> int:
    try:
        stats = os.statvfs(path)
        return stats.f_bavail * stats.f_frsize
    except OSError:
        return 0


def active_jobs(jobs_root: Path) -> list[dict]:
    """Running desktop builds; their directories must not move underneath them."""
    found = []
    if not jobs_root.is_dir():
        return found
    for job_file in sorted(jobs_root.glob("*/job.json")):
        try:
            job = json.loads(job_file.read_text())
        except (OSError, ValueError):
            continue
        if job.get("state") not in ("queued", "running", "cancelling", "awaiting-exclusions"):
            continue
        pid = job.get("pid")
        alive = False
        if isinstance(pid, int):
            try:
                args = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "args="],
                                      capture_output=True, text=True, timeout=3).stdout
                alive = "desktop_workbench.py" in args
            except (OSError, subprocess.SubprocessError):
                alive = False
        found.append({"id": job_file.parent.name, "state": job.get("state"),
                      "pid": pid, "alive": alive, "build": job.get("build")})
    return found


def build_directories(artifacts_root: Path) -> list[Path]:
    """Directories that look like a mcfao build: they own a result.json.

    Builds live under `artifacts/mcfao/` for the CLI and under whatever directory the
    user picked for the workbench, so both layouts are scanned one level deep.
    """
    roots = [artifacts_root / "mcfao", artifacts_root]
    found = []
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if entry.is_symlink() or not entry.is_dir():
                continue
            if entry in found:
                continue
            if (entry / "result.json").is_file():
                found.append(entry)
    return found


def build_status(build: Path) -> str:
    try:
        return str(json.loads((build / "result.json").read_text()).get("status", "?"))
    except (OSError, ValueError):
        return "?"


def has_ipa(build: Path) -> bool:
    """A finished IPA inside the build is the deliverable, not a cache.

    This is the safety check that runs on its own, without a plan; it must never
    trust a cached size. Unreadable trees count as containing an IPA.
    """
    result = storage_scan.scan(build)
    if not result.complete:
        return True
    return result.ipa > 0


def stage_paths(build: Path) -> list[Path]:
    """Only the first level of known stage names, never a recursive search."""
    return [build / name for name in INTERMEDIATE_STAGES
            if (build / name).is_dir() and not (build / name).is_symlink()]


class _Measured:
    """One scanner pass per directory; reused by every later query in a plan."""

    def __init__(self):
        self.cache = {}

    def get(self, path: Path):
        key = str(path)
        result = self.cache.get(key)
        if result is None:
            result = storage_scan.scan(path)
            self.cache[key] = result
        return result

    def bytes(self, path: Path) -> int:
        return self.get(path).bytes

    def ipa(self, path: Path) -> bool:
        result = self.get(path)
        return (not result.complete) or result.ipa > 0

    def stages(self, build: Path) -> int:
        total = 0
        for stage in stage_paths(build):
            total += self.bytes(stage)
        return total


def plan(*, data_root: Path, keep_builds: int = 2, include_cache: bool = True,
         include_builds: bool = True, include_intermediates: bool = True,
         measured: _Measured | None = None) -> dict:
    artifacts = data_root / "artifacts"
    cache = data_root / "cache"
    if not cache.exists():
        cache = data_root / ".cache"
    jobs = data_root / "artifacts/desktop-jobs"
    measured = measured or _Measured()
    groups = []
    running = active_jobs(jobs)
    busy = [job for job in running if job["alive"]]

    if include_cache:
        items = []
        for name in CACHE_CHILDREN:
            path = cache / name
            if path.is_dir() and not path.is_symlink():
                items.append({"path": str(path), "bytes": measured.bytes(path),
                              "reason": "工具链与源码缓存，可重新下载或编译"})
        if items:
            groups.append({"id": "cache", "label": "编译缓存",
                           "detail": "删除后下次构建需要重新下载并解压，首次准备约 30–60 分钟。",
                           "items": items})

    rust_target = data_root / "desktop/src-tauri/target"
    if include_cache and rust_target.is_dir() and not rust_target.is_symlink():
        groups.append({"id": "rust", "label": "Rust 编译缓存",
                       "detail": "Tauri 工作台自身的 cargo 产物，可重新编译。",
                       "items": [{"path": str(rust_target), "bytes": measured.bytes(rust_target),
                                   "reason": "cargo target，可重新编译"}]})

    builds = build_directories(artifacts)
    if include_intermediates and builds:
        items = []
        for build in builds:
            if measured.ipa(build) or build_status(build) in ("DEVELOPMENT_IPA_VERIFIED", "UNSIGNED_IPA_EXPORTED"):
                continue
            if any(job.get("build") and str(build) in str(job.get("build")) for job in busy):
                continue
            for stage in stage_paths(build):
                items.append({"path": str(stage), "bytes": measured.bytes(stage),
                              "reason": f"{build.name} 的中间阶段，保留 result.json"})
        if items:
            groups.append({"id": "intermediates", "label": "构建中间产物",
                           "detail": "AOT 对象、拆分类、链接与打包目录。保留 result.json、日志与 IPA；同参数重跑可复用检查点，删除后需要重新编译。",
                           "items": items})

    if include_builds and builds:
        ordered = sorted(builds, key=lambda p: p.stat().st_mtime, reverse=True)
        keep = set(ordered[:max(0, keep_builds)])
        items = []
        for build in ordered:
            if build in keep or measured.ipa(build):
                continue
            if any(job.get("build") and str(build) in str(job.get("build")) for job in busy):
                continue
            # A build keeps its manifest, inputs and logs; only its stages go.
            items.append({"path": str(build), "bytes": measured.stages(build),
                          "reason": f"旧构建（{build_status(build)}），保留最近 {keep_builds} 个"})
        if items:
            groups.append({"id": "builds", "label": "旧构建目录",
                           "detail": f"保留最近 {keep_builds} 个构建以及所有带 IPA 的目录。",
                           "items": items})

    # Old-build stages otherwise also appear under intermediates, overstating
    # reclaimable bytes and making a combined selection try deleting twice.
    old_builds = {Path(item['path']) for group in groups if group['id'] == 'builds'
                  for item in group['items']}
    for group in groups:
        if group['id'] == 'intermediates':
            group['items'] = [item for item in group['items'] if Path(item['path']).parent not in old_builds]
        group["bytes"] = sum(item["bytes"] for item in group["items"])
        group["count"] = len(group["items"])
    groups = [group for group in groups if group['items']]
    return {
        "status": "STORAGE_PLAN",
        "dataRoot": str(data_root),
        "freeBytes": free_bytes(data_root if data_root.exists() else ROOT),
        "groups": groups,
        "reclaimBytes": sum(group["bytes"] for group in groups),
        "activeJobs": running,
        "blocked": bool(busy),
    }


def _remove(path: Path) -> None:
    if path.is_symlink() or not path.exists():
        raise ValueError(f"Refusing to remove missing or linked path: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _remove_build(build: Path, measured: _Measured) -> int:
    """Remove a build's stages but keep its manifest, inputs and logs."""
    freed = 0
    for entry in stage_paths(build):
        freed += measured.bytes(entry)
        _remove(entry)
    return freed


def apply(*, data_root: Path, groups: list[str], keep_builds: int = 2) -> dict:
    """Delete exactly the planned paths; recompute so a stale request cannot widen scope."""
    # A cached size is never an input here: every path below is re-validated on
    # the live filesystem in this call, and its size is measured again.
    measured = _Measured()
    current = plan(data_root=data_root, keep_builds=keep_builds, measured=measured)
    if current["blocked"]:
        raise ValueError("有构建任务正在运行，请先完成或取消后再清理")
    allowed = {group["id"]: group for group in current["groups"]}
    unknown = set(groups) - set(allowed)
    if unknown:
        raise ValueError("未知的清理分组：" + ", ".join(sorted(unknown)))
    root = data_root.resolve()
    freed = 0
    removed = []
    for name in groups:
        for item in allowed[name]["items"]:
            target = Path(item["path"])
            resolved_parent = target.parent.resolve()
            if root not in resolved_parent.parents and resolved_parent != root:
                raise ValueError(f"Path escapes the data root: {target}")
            if target.name in PROTECTED_NAMES or target.suffix in PROTECTED_SUFFIXES:
                raise ValueError(f"Protected artefact: {target}")
            if target.is_symlink() or not target.exists():
                raise ValueError(f"清理目标已变化，请重新扫描：{target}")
            if name == "builds":
                if has_ipa(target):
                    raise ValueError(f"构建目录包含 IPA，已跳过：{target}")
                # Keep result.json/inputs.json: they are the record of what was built.
                freed += _remove_build(target, measured)
                size = measured.stages(target)
            else:
                size = measured.bytes(target)
                _remove(target)
                freed += size
            removed.append({"path": str(target), "bytes": size})
    return {"status": "STORAGE_CLEANED", "removed": removed, "freedBytes": freed,
            "freeBytes": free_bytes(data_root), "groups": groups}


def default_data_root() -> Path:
    """Follow the existing external-storage mapping when it is available."""
    config = ROOT / "external-storage.json"
    try:
        data = json.loads(config.read_text())["data"]
        if Path(data).is_dir():
            return Path(data)
    except (OSError, ValueError, KeyError):
        pass
    return ROOT


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--keep-builds", type=int, default=2)
    parser.add_argument("--groups", default="",
                        help="Comma separated group ids from the plan (cache,rust,intermediates,builds)")
    args = parser.parse_args(argv)
    data_root = (args.data_root or default_data_root()).expanduser()
    if not data_root.is_dir():
        print(json.dumps({"status": "BLOCKED", "error": "数据目录不存在: " + str(data_root)}))
        return 2
    if args.action == "plan":
        print(json.dumps(plan(data_root=data_root, keep_builds=args.keep_builds), indent=2))
        return 0
    groups = [name.strip() for name in args.groups.split(",") if name.strip()]
    if not groups:
        print(json.dumps({"status": "BLOCKED", "error": "请选择要清理的分组"}))
        return 2
    try:
        result = apply(data_root=data_root, groups=groups, keep_builds=args.keep_builds)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "BLOCKED", "error": str(error)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
