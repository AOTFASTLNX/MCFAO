#!/usr/bin/env python3
"""Build the first-party method splitter (`compiler/splitter`) with a pinned ASM classpath.

The splitter is first-party Java source. Its only dependencies are the ASM bytecode libraries,
which are **not** vendored into this repository: all five come from checksum-pinned Maven Central
downloads (compiler/asm.lock.json), and every jar is recorded with
its SHA-256 in the build record so a later run can detect a substituted library.

This tool only compiles. It does not transform any jar and it is not Gate evidence.
"""
from __future__ import annotations
from storage_config import cache_path

import argparse
import json
import shutil
from pathlib import Path

from bootstrap_toolchain import sha256
from verified_download import fetch
from capture import ROOT, capture
from run_b0_reference import execute  # noqa: F401  (imported for parity with other tools)

SOURCE = ROOT / "compiler/splitter/src/fabricaot/split/MethodSplitter.java"
ASM_VERSION = "9.9"

# All five ASM dependencies are fetched by
# `python3 -B tools/build_method_splitter.py --fetch-missing` from Maven Central.
CACHE = cache_path("libs/asm-" + ASM_VERSION)
MAVEN = "https://repo1.maven.org/maven2/org/ow2/asm"


def gradle_asm() -> dict:
    """Compatibility name: all five dependencies now come from checksum-pinned Maven files."""
    lock = json.loads((ROOT / 'compiler/asm.lock.json').read_text())
    libraries = {}
    for spec in lock.values():
        path = CACHE / spec['file']
        if not path.is_file() or path.stat().st_size != spec['size'] or sha256(path) != spec['sha256']:
            raise ValueError('Missing or modified ASM dependency; run --fetch-missing: ' + str(path))
        libraries[spec['file']] = path
    return libraries


def build(java_home: Path, output: Path, extra: list | None = None) -> dict:
    """Compile the splitter into `output/classes` and return a build record."""
    libraries = gradle_asm()
    classpath = ":".join(str(path) for path in libraries.values())
    classes = output / "classes"
    if classes.exists():
        shutil.rmtree(classes)
    for stale in ("compile",):
        if (output / stale).exists():
            shutil.rmtree(output / stale)
    classes.mkdir(parents=True)
    run = capture([str(java_home / "bin/javac"), "--release", "25", "-proc:none", "-Xlint:all",
                   "-cp", classpath, "-d", str(classes), str(SOURCE)], output / "compile", 300)
    record = {
        "status": "BUILT" if run["exitCode"] == 0 else "FAILED",
        "source": str(SOURCE),
        "sourceSHA256": sha256(SOURCE),
        "javaHome": str(java_home),
        "javaVersion": "25",
        "asmVersion": ASM_VERSION,
        "asmJars": [{"name": name, "path": str(path.resolve()), "sha256": sha256(path)}
                    for name, path in sorted(libraries.items())],
        "classesDirectory": str(classes),
        "classFiles": sorted(p.name for p in classes.rglob("*.class")),
        "exitCode": run["exitCode"],
        "scope": "compile only; the splitter is not run and no artifact is transformed here",
    }
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    if run["exitCode"] != 0:
        raise SystemExit("javac failed, see " + str(output / "compile"))
    return record


def fetch_missing() -> list:
    """Fetch all five pinned ASM artifacts, independent of Gradle installations."""
    fetched = []
    for spec in json.loads((ROOT / 'compiler/asm.lock.json').read_text()).values():
        target = CACHE / spec['file']
        existed = target.is_file()
        fetch(spec, CACHE.resolve() / spec["file"])
        if not existed: fetched.append({'path': str(target), **spec})
    return fetched


def java_home() -> Path:
    manifest = json.loads((ROOT / "artifacts/b0/prepared-04/result.json").read_text())
    home = Path(manifest["javaHome"])
    if not (home / "bin/javac").exists():
        raise SystemExit("javac missing from the verified Java 25 home")
    return home


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--java-home", type=Path)
    parser.add_argument("--fetch-missing", action="store_true")
    args = parser.parse_args(argv)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    if args.fetch_missing:
        fetched = fetch_missing()
        if fetched:
            (output / "fetched.json").write_text(json.dumps(fetched, indent=2) + "\n")
    record = build(args.java_home or java_home(), output)
    print(json.dumps({key: record[key] for key in ("status", "sourceSHA256", "classesDirectory")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
