#!/usr/bin/env python3
"""Compile the audited first-party B0 fixture with annotation processing disabled; never run it."""
from __future__ import annotations

import argparse
import io
import json
import os
import zipfile
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT, capture
from mod_file_policy import content_paths, is_metadata


def jar_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                raise ValueError("unsafe JAR entry")
            if is_metadata(name):
                continue
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def select_libraries(inventory: dict, lock: dict) -> list[dict]:
    selected = []
    for expected in lock["engineLibraries"]:
        matches = [entry for entry in inventory["jars"] if Path(entry["path"]).name == expected["file"]]
        if len(matches) != 1:
            raise ValueError("ambiguous/missing pinned engine library: " + expected["file"])
        entry = matches[0]
        path = Path(entry["path"])
        if path.is_symlink() or path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
            raise ValueError("engine hash mismatch: " + str(path))
        selected.append(entry)
    return selected


def preparation_inputs(client_dir=None, baseline=None):
    baseline = Path(baseline or os.environ.get('MCFAO_A0') or ROOT / 'artifacts/evidence/a0-desktop-reference')
    if client_dir:
        client_dir = Path(client_dir).resolve(strict=True)
        inventory = json.loads((client_dir / 'client-inputs.json').read_text())
        if inventory.get('status') != 'OWNED_CLIENT_INPUTS_VERIFIED':
            raise ValueError('Expected a verified external client directory')
        shared_meta = client_dir / 'meta'
        for row in inventory['jars']:
            path = Path(row['path'])
            if path.is_symlink() or not path.resolve().is_relative_to(shared_meta) or sha256(path) != row['sha256']:
                raise ValueError('External client library changed or escaped its directory')
        return inventory, shared_meta
    inventory = json.loads((baseline / 'dependencies.json').read_text())
    result = json.loads((baseline / 'result.json').read_text())
    if result['gateA0'] != 'PASS': raise ValueError('A0 is not passed')
    return inventory, Path(result['profile']).parent.parent / 'meta'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graalvm-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--client-dir', type=Path, help='External hash-verified client input directory; does not assert A0 PASS')
    parser.add_argument('--baseline', type=Path, help='Existing real A0 evidence directory (or MCFAO_A0)')
    args = parser.parse_args(argv)
    home = args.graalvm_home.resolve(strict=True)
    lock = json.loads((ROOT / "compiler/fabric.lock.json").read_text())
    inventory, shared_meta = preparation_inputs(args.client_dir, args.baseline)
    engine = select_libraries(inventory, lock)
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    classes = output / "classes"
    classes.mkdir()
    fixture = ROOT / "interop/b0"
    sources = sorted(p for p in content_paths(fixture) if p.suffix == ".java"
                     and p.relative_to(fixture).parts[0] in ("src", "bootstrap"))
    command = [str(home / "bin/javac"), "--release", "25", "-proc:none", "-cp",
               os.pathsep.join(entry["path"] for entry in engine), "-d", str(classes), *map(str, sources)]
    result = capture(command, output / "compile", 180)
    if result["exitCode"] or result["timedOut"]:
        print(json.dumps(result, indent=2))
        return 1
    compiled = {str(path.relative_to(classes)): path.read_bytes()
                for path in content_paths(classes) if path.suffix == ".class"}
    nested = {name: data for name, data in compiled.items() if name.startswith("fabricaot/b0/nested/")}
    nested.update({str(path.relative_to(fixture / "nested-resources")): path.read_bytes()
                   for path in content_paths(fixture / "nested-resources") if path.is_file()})
    nested_data = jar_bytes(nested)
    (output / "nested.jar").write_bytes(nested_data)
    parent = {name: data for name, data in compiled.items()
              if not name.startswith(("fabricaot/b0/nested/", "fabricaot/b0/bootstrap/"))}
    parent.update({str(path.relative_to(fixture / "resources")): path.read_bytes()
                   for path in content_paths(fixture / "resources") if path.is_file()})
    parent["META-INF/jars/fabricaot-b0-nested.jar"] = nested_data
    (output / "fixture.jar").write_bytes(jar_bytes(parent))
    bootstrap = {name: data for name, data in compiled.items() if name.startswith("fabricaot/b0/bootstrap/")}
    bootstrap["META-INF/MANIFEST.MF"] = b"Manifest-Version: 1.0\r\nPremain-Class: fabricaot.b0.bootstrap.CaptureAgent\r\n\r\n"
    (output / "driver.jar").write_bytes(jar_bytes(bootstrap))
    libraries = []
    for entry in inventory["jars"]:
        path = Path(entry["path"])
        if path.is_relative_to(shared_meta):
            if not path.is_file() or sha256(path) != entry["sha256"]:
                raise ValueError("baseline library changed: " + str(path))
            libraries.append(entry)
    inputs = {str(p.relative_to(ROOT)): sha256(p) for p in content_paths(fixture) if p.is_file()}
    for name in ("tools/prepare_b0.py", "tools/run_b0_reference.py", "compiler/fabric.lock.json"):
        inputs[name] = sha256(ROOT / name)
    manifest = {"status": "PREPARED", "gateB0": "BLOCKED", "gateB1": "BLOCKED",
                "scope": "compiled first-party fixture only; no Loader/Mod initializer/test run",
                "javaHome": str(home), "javaSHA256": sha256(home / "bin/java"),
                "engineLibraries": engine, "referenceLibraries": libraries,
                "binaries": {name: {"bytes": (output / name).stat().st_size, "sha256": sha256(output / name)}
                             for name in ("fixture.jar", "nested.jar", "driver.jar")},
                "inputsSHA256": inputs}
    (output / "result.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": "PREPARED", "classFiles": len(compiled), "testExecution": "NONE"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
