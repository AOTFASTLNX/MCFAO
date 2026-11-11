#!/usr/bin/env python3
"""Register research artifacts with the user's single central AAR; never clean."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from capture import ROOT


def escaping_symlinks(path: Path) -> list[Path]:
    """Symlinks whose resolved target leaves the registered tree.

    Xcode leaves relative links inside its build products (BuildProductsPath ->
    InstallationBuildProductsLocation). Those stay inside the evidence tree and are harmless; a link that
    points out of it would silently register a host file, so that is still refused.
    """
    root = path.resolve()
    escaped = []
    for entry in path.rglob("*"):
        if entry.is_symlink():
            target = Path(os.path.realpath(entry))
            if not target.is_relative_to(root):
                escaped.append(entry)
    return escaped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-modified", action="store_true",
                        help="Use only after inspecting changed artifacts and verifying their hashes")
    parser.add_argument("--external-build-root", type=Path, action="append", default=[],
                        help="Explicit dedicated generated test directory outside the project; no recursive deletion authority")
    args = parser.parse_args(argv)
    if os.environ.get("AAR_HOME"):
        parser.error("AAR_HOME must be unset; only the configured central registry is allowed")
    aar = shutil.which("aar") or str(Path.home() / "Documents/Codex/monitor/bin/aar")
    specs = [
        (".cache/toolchains", "CACHE", False, None, ["python3", "-B", "tools/bootstrap_toolchain.py"], True),
        # Register downloaded archives and the extracted JDK directory separately.
        # JDK internal symlinks are deliberately not traversed by AAR.
        (".cache/toolchains", "CACHE", False, "*", ["python3", "-B", "tools/bootstrap_toolchain.py"], True),
        (".cache/upstream", "CACHE", False, None, ["python3", "-B", "tools/fetch_upstream.py"], False),
        (".cache/upstream", "CACHE", False, "*.tar.gz", ["python3", "-B", "tools/fetch_upstream.py"], True),
        (".cache/apple-metal", "CACHE", True, None,
         ["xcodebuild", "-downloadComponent", "MetalToolchain", "-buildVersion", "27B47", "-exportPath", ".cache/apple-metal"], True),
        ("artifacts/a1", "BUILD", True, None, [], False),
        # C0 real-client diagnostics: analysis rounds, split jars, the relocatable image object and the
        # linked iOS dylib. Each directory carries its own result.json/command.json.
        ("artifacts/c0", "BUILD", True, None, [], False),
        ("artifacts/evidence", "GENERATED", True, None, [], False),
    ]
    entries = [(ROOT / relative, ROOT, kind, recursive, pattern, command, regenerable)
               for relative, kind, recursive, pattern, command, regenerable in specs]
    for external in args.external_build_root:
        path = external.resolve()
        if path in (Path("/"), Path.home()) or len(path.parts) < 5:
            parser.error("External project must be a dedicated generated test directory")
        if not path.exists():
            print(f"External generated directory no longer present: {path}", flush=True)
            continue
        entries.append((path, path, "BUILD", False, None, [], False))
    failures = []
    for path, project, kind, recursive, pattern, command, regenerable in entries:
        if not path.exists():
            parser.error(f"Missing artifact path: {path}")
        if recursive and (escaped := escaping_symlinks(path)):
            # One unregistrable tree must not stop the rest from being recorded. The prior behaviour
            # aborted here, so nothing after the first symlinked path was ever registered.
            print(f"Refusing recursive registration with escaping symlinks: {path}", flush=True)
            failures.append({"path": str(path),
                             "error": "symbolic links escape the tree",
                             "symlinks": [str(p) for p in escaped[:5]]})
            continue
        argv = [aar, "register", "--path", str(path), "--project", str(project), "--type", kind,
                "--source", "FabricAOT Gate A experiments; per-step argv in command.json; docs/BUILDING.md", "--json"]
        # Historical experiment logs are retained as evidence. Their original
        # timestamps/results are not reproducible, so they get no regeneration
        # or deletion flags. Downloaded pinned toolchains are reproducible.
        if regenerable:
            argv.append("--regenerable")
        argv += ["--argv-json", json.dumps(command)]
        if recursive:
            argv.append("--include-files")
        if pattern:
            argv += ["--pattern", pattern]
        if args.accept_modified:
            argv.append("--accept-modified")
        print(f"Registering {path} ({kind}{', selected children' if pattern else ''})", flush=True)
        completed = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
        if completed.returncode:
            print(completed.stdout)
            print(completed.stderr)
            failures.append({"path": str(path), "error": completed.stderr.strip() or completed.stdout.strip()})
            continue
        result = json.loads(completed.stdout)
        if not result.get("ok"):
            print(completed.stdout)
            failures.append({"path": str(path), "error": result.get("error", "not ok")})
            continue
        records = result["data"]
        print(json.dumps({"path": str(path), "registered": len(records),
                          "types": sorted({r["type"] for r in records}),
                          "safeToDelete": sorted({r["safe_to_delete"] for r in records}),
                          "rootIDs": [r["id"] for r in records if r["path"] == str(path)]}), flush=True)
    if failures:
        print(json.dumps({"failures": failures}, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
