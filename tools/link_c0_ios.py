#!/usr/bin/env python3
"""Link a Native Image relocatable client object for arm64-apple-ios with the iOS SDK.

Native Image's own link step targets the host: it takes libdarwin.a and the macOS system stubs, so a
client image built for the IOS_AARCH64 platform can never be linked that way (round 34: "building for
'macOS', but linking in object file ... built for 'iOS'"). This tool reproduces the B1 recipe
(-H:+ExitAfterRelocatableImageWrite, then link by hand) for the far larger client image.

The object and every archive are verified by SHA-256 before the link; nothing is executed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from bootstrap_toolchain import ROOT, sha256
from capture import capture

RUNTIME_ARCHIVES = ("libjava.a", "libnet.a", "libnio.a", "libzip.a", "libsvm.a", "libfallback.a")
# Same framework set the verified B1 probe used; iOS has no CoreServices-only subset needs here.
FRAMEWORKS = ("Foundation", "CoreFoundation", "CFNetwork", "SystemConfiguration", "Security",
              "MobileCoreServices")
SYSTEM_LIBRARIES = ("z", "iconv", "resolv", "pthread", "dl", "objc")


def validate_runtime(report: dict, sdk: str) -> str:
    """Return the expected target triple, or refuse a runtime built for something else."""
    target = "arm64-apple-ios17.0" + ("-simulator" if sdk == "iphonesimulator" else "")
    if report.get("status") != "COMPILED":
        raise ValueError("Runtime translation units have not all compiled")
    if report.get("target") != target:
        raise ValueError("Runtime target does not match requested SDK; device/simulator archives "
                         "cannot be relabelled")
    return target


def link_command(target: str, objects: list[Path], archives: list[Path], output: Path,
                 sdk: str, install_name: str) -> list[str]:
    command = ["xcrun", "--sdk", sdk, "clang", "-target", target, "-dynamiclib",
               "-Wl,-dead_strip", "-Wl,-install_name," + install_name, "-o", str(output)]
    command += [str(p) for p in objects]
    command += [str(p) for p in archives]
    for framework in FRAMEWORKS:
        command += ["-framework", framework]
    command += ["-l" + name for name in SYSTEM_LIBRARIES]
    return command


def undefined_symbols(log: str) -> list[str]:
    """Pull the symbol names out of ld's undefined-symbol report, deduplicated and sorted."""
    names = set()
    inside = False
    for line in log.splitlines():
        if "Undefined symbols for architecture" in line:
            inside = True
            continue
        if inside:
            if not line.strip():
                break
            match = re.match(r'\s*"?([^\s",]+)"?, referenced from:', line)
            if match:
                names.add(match.group(1))
    return sorted(names)


def jni_entrypoints(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Split unresolved Mach-O symbols into JVM/JNI natives and everything else.

    Only the first group may be stubbed: the iOS runtime deliberately omits some JDK natives
    (libextnet, macOS socket options, management), and those must terminate loudly if reached. Any
    other unresolved symbol is a genuine linking defect.
    """
    stubbable, other = [], []
    for symbol in symbols:
        (stubbable if re.match(r"^_(Java_|JNI_)", symbol) else other).append(symbol)
    return stubbable, other


def stub_source(symbols: list[str]) -> str:
    """A C file that traps on every omitted entrypoint instead of binding to an empty address."""
    lines = ["/* Generated for a research build: the iOS runtime does not implement these natives.",
             "   Reaching one must stop the process with a named message, never continue silently. */",
             "#include <stdio.h>", "#include <stdlib.h>", "",
             "static void fabricaot_unsupported(const char *name) {",
             '    fprintf(stderr, "FabricAOT: unsupported JVM native entrypoint reached: %s\\n", name);',
             "    fflush(stderr);", "    abort();", "}", ""]
    for symbol in sorted(symbols):
        c_name = symbol[1:] if symbol.startswith("_") else symbol
        lines.append(f'void {c_name}(void) {{ fabricaot_unsupported("{c_name}"); }}')
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True,
                        help="Build directory that holds the relocatable client-graph.o")
    parser.add_argument("--runtime", type=Path, default=ROOT / "artifacts/b1/runtime-ios")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk", choices=("iphoneos", "iphonesimulator"), default="iphoneos")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--stub-unsupported-jni", action="store_true",
                        help="After a link that fails only on omitted JVM/JNI natives, add first-party "
                             "stubs that abort with a named message and relink")
    args = parser.parse_args(argv)
    image_dir = args.image.absolute()
    output = args.output.absolute()
    runtime = args.runtime.absolute()

    objects = sorted(p for p in image_dir.rglob("client-graph.o") if p.is_file())
    if len(objects) != 1:
        parser.error(f"Expected exactly one relocatable client object, found {len(objects)}")
    object_sha256 = sha256(objects[0])
    report = json.loads((runtime / "result.json").read_text())
    try:
        target = validate_runtime(report, args.sdk)
    except ValueError as error:
        parser.error(str(error))
    optional=('libextnet.a',)
    archives = [runtime / name for name in (*RUNTIME_ARCHIVES,*(name for name in optional if Path(name).stem in report['archives']))]
    archive_sha256 = {}
    for archive in archives:
        entry = report["archives"].get(archive.stem)
        if entry is None or sha256(archive) != entry["sha256"]:
            parser.error(f"Runtime archive missing or modified: {archive}")
        archive_sha256[archive.stem] = entry["sha256"]

    output.mkdir(parents=True, exist_ok=False)
    binary = output / "client-graph.dylib"
    command = link_command(target, objects, archives, binary, args.sdk,
                           "@rpath/FabricAOTClient.dylib")
    result = capture(command, output / "link", args.timeout)
    log = (output / "link/stdout.log").read_text(errors="replace") + \
          (output / "link/stderr.log").read_text(errors="replace")
    unresolved = undefined_symbols(log)
    stubbed, other = jni_entrypoints(unresolved)
    attempts = [{"step": "link", "exitCode": result["exitCode"], "undefinedSymbols": unresolved}]

    if result["exitCode"] != 0 and args.stub_unsupported_jni and stubbed and not other:
        stubs = output / "unsupported-entrypoints.c"
        stubs.write_text(stub_source(stubbed))
        command = link_command(target, [*objects, stubs], archives, binary, args.sdk,
                               "@rpath/FabricAOTClient.dylib")
        result = capture(command, output / "link-stubbed", args.timeout)
        log = (output / "link-stubbed/stdout.log").read_text(errors="replace") + \
              (output / "link-stubbed/stderr.log").read_text(errors="replace")
        unresolved = undefined_symbols(log)
        attempts.append({"step": "link-with-stubs", "exitCode": result["exitCode"],
                         "undefinedSymbols": unresolved})

    linked = result["exitCode"] == 0 and binary.exists()
    if linked and stubbed:
        status = "LINKED_WITH_UNSUPPORTED_ENTRYPOINTS"
    elif linked:
        status = "LINKED"
    else:
        status = "BLOCKED"
    outcome = {"status": status, "target": target, "sdk": args.sdk,
               "imageObject": {"path": str(objects[0]), "sha256": object_sha256,
                               "bytes": objects[0].stat().st_size},
               "runtime": str(runtime), "runtimeArchivesSHA256": archive_sha256,
               "unsupportedEntrypoints": sorted(stubbed),
               "unresolvedSymbolsAfterLink": unresolved,
               "attempts": attempts,
               "deviceRun": "NOT RUN",
               "gateC0": "BLOCKED",
               "scope": "link only; no game code has run on a device",
               "link": result}
    if binary.exists():
        outcome["binary"] = {"path": str(binary), "sha256": sha256(binary),
                             "bytes": binary.stat().st_size}
    (output / "result.json").write_text(json.dumps(outcome, indent=2) + "\n")
    print(json.dumps({k: v for k, v in outcome.items() if k != "link"}, indent=2))
    return 0 if status.startswith("LINKED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
