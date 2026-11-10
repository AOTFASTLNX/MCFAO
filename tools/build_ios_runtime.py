#!/usr/bin/env python3
"""Compile pinned, licensed upstream Java25/SVM C sources for iOS.

No candidate binaries or third-party project scripts are used. This assembles
an experimental runtime for the A1 fixture, not a full Java compatibility claim.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
from pathlib import Path

from bootstrap_toolchain import ROOT, sha256
from capture import capture


def jdk_sources(jdk: Path, library: str, module: str = 'java.base') -> list[Path]:
    # OpenJDK's platform directory overrides a shared implementation with the
    # same relative name. Windows/Linux/AIX sources are not part of this target.
    selected = {}
    for platform in ("share", "unix", "macosx"):
        base = jdk / 'src' / module / platform / "native" / library
        if base.is_dir():
            for path in sorted(base.rglob("*.c")):
                if "zlib" in path.relative_to(base).parts:
                    continue  # Use the public iOS SDK's libz and matching headers.
                selected[str(path.relative_to(base))] = path
    return [selected[key] for key in sorted(selected)]


def ios_source(text: str, name: str) -> str:
    """Narrow first-party platform edits, retaining all upstream notices."""
    if name == "java_props_macosx.c":
        text = text.replace("#include <objc/objc-runtime.h>",
                            "#include <TargetConditionals.h>\n#if !TARGET_OS_IPHONE\n#include <objc/objc-runtime.h>\n#endif")
        text = text.replace('sprops->os_name = strdup("Mac OS X");',
                            '#if TARGET_OS_IPHONE\n    sprops->os_name = strdup("iOS");\n#else\n    sprops->os_name = strdup("Mac OS X");\n#endif')
        start = text.index("void setProxyProperties(")
        body = text.index("{", start) + 1
        end = text.rfind("}")
        text = text[:body] + "\n#if !TARGET_OS_IPHONE\n" + text[body:end] + "\n#endif\n" + text[end:]
    if name == "DefaultProxySelector.c":
        text = text.replace("#include <CoreServices/CoreServices.h>", "#include <CFNetwork/CFNetwork.h>")
    if name == "NetworkInterface.c":
        text = text.replace("#include <net/if_arp.h>",
                            "#include <TargetConditionals.h>\n#if !TARGET_OS_IPHONE\n#include <net/if_arp.h>\n#endif")
    if name == "locale.c":
        text = text.replace('#include "svm_locale.h"', '#include "svm_locale.h"\n#include "java_props_macosx.h"')
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aot-object", type=Path)
    parser.add_argument("--sdk", choices=("iphoneos", "iphonesimulator"), default="iphoneos")
    parser.add_argument('--with-extnet',action='store_true',help='Compile the pinned Darwin extended socket option JNI library')
    args = parser.parse_args(argv)
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    jdk = Path(json.loads((ROOT / ".cache/upstream/jdk.json").read_text())["path"])
    graal = Path(json.loads((ROOT / ".cache/upstream/graal.json").read_text())["path"])
    svm = graal / "substratevm"
    headers = jdk / "build/fabricaot-host/support/headers/java.base"
    if not (headers / "java_lang_System.h").is_file():
        parser.error("Build the official OpenJDK java.base-java target to generate JNI headers first")
    sdk = subprocess.check_output(["xcrun", "--sdk", args.sdk, "--show-sdk-path"], text=True).strip()
    target = "arm64-apple-ios17.0" + ("-simulator" if args.sdk == "iphonesimulator" else "")
    include_paths = {p.parent for platform in ("share", "unix", "macosx")
                     for p in (jdk / "src/java.base" / platform / "native").rglob("*.h")
                     if "zlib" not in p.parts}
    include_paths |= {headers, jdk / "build/fabricaot-host/jdk/include",
                      jdk / "src/hotspot/share/include", jdk / "src/hotspot/os/posix/include",
                      svm / "src/com.oracle.svm.native.libchelper/include"}
    home = ROOT / ".cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home"
    include_paths |= {home / "include", home / "include/darwin"}
    base_args = ["xcrun", "--sdk", args.sdk, "clang", "-target", target, "-isysroot", sdk,
                 "-O2", "-fPIC", "-fno-common", "-fvisibility=hidden", "-ffunction-sections", "-fdata-sections",
                 "-DSTATIC_BUILD=1", "-DMACOSX", "-D_ALLBSD_SOURCE", "-D_LITTLE_ENDIAN", "-D_REENTRANT",
                 '-DARCHPROPNAME="aarch64"', '-DVERSION_STRING="25.0.2+10-jvmci-b01"',
                 "-Wno-deprecated-declarations", "-Wno-incompatible-pointer-types"]
    for path in sorted(include_paths):
        base_args += ["-I", str(path)]
    sources = {}
    for library in ("libjava", "libnet", "libnio", "libzip"):
        sources[library] = jdk_sources(jdk, library)
    if args.with_extnet:sources['libextnet']=jdk_sources(jdk,'libextnet','jdk.net')
    graal_paths = ["com.oracle.svm.native.jvm.posix/src/JvmFuncs.c", "com.oracle.svm.native.darwin/src/foundation.c"]
    graal_paths += ["com.oracle.svm.native.libchelper/src/" + n for n in
                    ("cpuid.c", "locale.c", "timeZone.c", "getEnviron.c", "cSunMiscSignal.c",
                     "codeSynchronization.c", "macrosAsFunctions.c", "varargs_helper.c")]
    sources["libsvm"] = [svm / "src" / p for p in graal_paths]
    patched = output / "patched"
    patched.mkdir()
    jobs = []
    inputs = {}
    for library, files in sources.items():
        (output / "objects" / library).mkdir(parents=True)
        for index, source in enumerate(files):
            original = source.read_text()
            modified = ios_source(original, source.name)
            effective = source
            if modified != original:
                effective = patched / (library + "-" + source.name)
                effective.write_text(modified)
            relative = str(source.relative_to(jdk if source.is_relative_to(jdk) else graal))
            inputs[library + "/" + relative] = sha256(source)
            obj = output / "objects" / library / (f"{index:03d}-" + source.name + ".o")
            command = base_args + ["-DLIBRARY_NAME=" + library[3:]]
            command += (["-x", "objective-c"] if source.name in ("java_props_md.c", "java_props_macosx.c", "foundation.c") else [])
            command += ["-c", str(effective), "-o", str(obj)]
            jobs.append((library, source.name, obj, command))
    print(f"Compiling {len(jobs)} upstream translation units for {target}", flush=True)

    def compile_one(job):
        library, name, obj, command = job
        result = capture(command, output / "commands" / (library + "-" + obj.stem), 90)
        return {"library": library, "source": name, "object": str(obj), **result}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(compile_one, jobs))
    failures = [r for r in results if r["exitCode"] != 0 or r["timedOut"]]
    archives = {}
    if not failures:
        for library in sources:
            archive = output / (library + ".a")
            objects = [r["object"] for r in results if r["library"] == library]
            command = ["xcrun", "libtool", "-static", "-o", str(archive), *objects]
            result = capture(command, output / "commands" / (library + "-archive"), 90)
            if result["exitCode"]:
                failures.append({"source": library + " archive", **result})
            else:
                archives[library] = {"path": str(archive), "sha256": sha256(archive)}
    fallback_names = []
    if not failures and args.aot_object:
        paths = [Path(a["path"]) for a in archives.values()]

        def symbols(path, undefined):
            flags = ["-u", "-j"] if undefined else ["-g", "-U", "-j"]
            result = subprocess.run(["xcrun", "nm", *flags, str(path)], capture_output=True, text=True, check=True)
            return {line.strip() for line in result.stdout.splitlines() if re.fullmatch(r"_JVM_[A-Za-z0-9_]+", line.strip())}

        defined = set().union(*(symbols(p, False) for p in [*paths, args.aot_object]))
        required = set().union(*(symbols(p, True) for p in paths))
        fallback_names = sorted(required - defined)
        fallback = output / "unsupported_jvm_calls.c"
        code = ['/* Generated fail-closed JVM entrypoints. No implementation is silently emulated. */',
                '#include <stdio.h>', '#include <stdlib.h>']
        for name in fallback_names:
            symbol = name[1:]
            code += [f'__attribute__((noreturn,visibility("default"))) void {symbol}(void) {{',
                     f'  fputs("FabricAOT unsupported native entry: {symbol}\\n", stderr); abort();', '}']
        fallback.write_text("\n".join(code) + "\n")
        obj = output / "unsupported_jvm_calls.o"
        result = capture(base_args + ["-c", str(fallback), "-o", str(obj)], output / "commands/fallback-compile")
        if result["exitCode"]:
            failures.append({"source": "fallback compile", **result})
        else:
            archive = output / "libfallback.a"
            result = capture(["xcrun", "libtool", "-static", "-o", str(archive), str(obj)], output / "commands/fallback-archive")
            if result["exitCode"]:
                failures.append({"source": "fallback archive", **result})
            else:
                archives["libfallback"] = {"path": str(archive), "sha256": sha256(archive)}
    report = {"status": "BLOCKED" if failures else "COMPILED", "target": target,
              "inputsSHA256": inputs, "translationUnits": len(results), "failed": [r["source"] for r in failures],
              "archives": archives, "commands": results, "deviceRun": "NOT RUN"}
    report["unsupportedJVMEntrypoints"] = fallback_names
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("commands", "inputsSHA256")}, indent=2))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
