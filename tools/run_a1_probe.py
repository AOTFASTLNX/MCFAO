#!/usr/bin/env python3
"""Build/run only the audited A1 fixture; desktop success never passes iOS Gate A1."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT, capture
from inspect_ios_candidate import inspect


def run(home: Path, output: Path, mode: str) -> dict:
    home = home.resolve()
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    fixture = ROOT / "interop/a1"
    classes = output / "classes"
    classes.mkdir()
    steps = []

    def step(name, argv, timeout=180):
        print(name, flush=True)
        result = capture([str(a) for a in argv], output / name, timeout)
        steps.append({"name": name, **result})
        return result["exitCode"] == 0 and not result["timedOut"]

    def semantic_result(name, argv):
        ok = step(name, argv)
        log = output / name / "stdout.log"
        return ok and "A1_SEMANTICS_PASS" in log.read_text().splitlines()

    status = "BLOCKED"
    stage = "java-version"
    if step(stage, [home / "bin/java", "-version"]):
        stage = "compile-java25"
        if step(stage, [home / "bin/javac", "--release", "25", "-d", classes,
                        fixture / "src/fabricaot/probe/A1Probe.java"]):
            shutil.copytree(fixture / "resources", classes, dirs_exist_ok=True)
            shutil.copytree(fixture / "metadata", classes, dirs_exist_ok=True)
            library = output / "liba1probe.dylib"
            ios = mode.startswith("ios-")
            sdk = "iphoneos" if ios else "macosx"
            native_args = ["xcrun", "--sdk", sdk, "clang", "-dynamiclib", "-O2",
                           "-Wall", "-Wextra", "-Werror", "-I", home / "include",
                           "-I", home / "include/darwin", fixture / "native/probe.c",
                           "-o", library]
            if ios:
                native_args += ["-target", "arm64-apple-ios17.0", "-install_name", "@rpath/liba1probe.dylib"]
            stage = "compile-jni"
            if step(stage, native_args):
                if mode == "jvm":
                    stage = "run-jvm"
                    ok = semantic_result(stage, [home / "bin/java", "--enable-native-access=ALL-UNNAMED",
                                      "-Xmx96m", "-cp", classes, "fabricaot.probe.A1Probe",
                                      library, output / "scratch"])
                    status = "PASS" if ok else "BLOCKED"
                else:
                    if ios:
                        stage = "compile-c-entry"
                        if not step(stage, [home / "bin/javac", "--add-modules", "org.graalvm.nativeimage",
                                            "-cp", classes, "-d", classes,
                                            fixture / "src-native/fabricaot/probe/A1EntryPoint.java"]):
                            return finish(output, mode, "BLOCKED", stage, steps)
                    stage = "native-image"
                    temporary = output / "tmp"
                    temporary.mkdir()
                    argv = [home / "bin/native-image", "--no-fallback", "-O1", "--parallelism=4",
                            "-J-Xmx3g", "-J-Djava.io.tmpdir=" + str(temporary),
                            "-H:+UnlockExperimentalVMOptions", "-cp", classes,
                            "--enable-native-access=ALL-UNNAMED",
                            "-o", output / "a1probe"]
                    if ios:
                        # An intentionally minimal attempt using the target-platform
                        # hook present in GraalVM 25. No macOS libraries are relabelled
                        # as iOS, and the unaudited candidate ZIP is never executed.
                        argv += ["--shared",
                                 "-H:PageSize=16384", "-Dsvm.targetName=iOS",
                                 "-Dsvm.targetArch=arm64",
                                 "-Dsvm.platform=org.graalvm.nativeimage.Platform$IOS_AARCH64"]
                    if mode == "ios-relocatable":
                        # Only numeric ABI cache data is consumed, not the candidate's
                        # native libraries, Gradle scripts, plugins or initializers.
                        spec = json.loads((ROOT / "compiler/toolchains.lock.json").read_text())["iosCandidate"]
                        candidate = ROOT / ".cache/toolchains" / spec["file"]
                        integrity = inspect(candidate, spec)
                        cap_cache = output / "caps"
                        cap_cache.mkdir()
                        with zipfile.ZipFile(candidate) as archive:
                            for name in integrity["capFiles"]:
                                (cap_cache / Path(name).name).write_bytes(archive.read(name))
                        argv += ["-H:+ExitAfterRelocatableImageWrite", "-H:+UseCAPCache",
                                 "-H:CAPCacheDir=" + str(cap_cache),
                                 "-H:TempDirectory=" + str(output / "native-tmp")]
                    argv += ["fabricaot.probe.A1Probe"]
                    if step(stage, argv, 300):
                        if mode == "desktop-aot":
                            stage = "run-desktop-aot"
                            ok = semantic_result(stage, [output / "a1probe", library, output / "scratch"])
                            status = "PASS" if ok else "BLOCKED"
                        else:
                            stage = "ios-link-sign-install-and-standalone-test"
                            # Compilation alone cannot pass this mode's Gate.
                            status = "BLOCKED"
    return finish(output, mode, status, stage, steps)


def finish(output, mode, status, stage, steps):
    binaries = {}
    paths = [output / name for name in ("a1probe", "a1probe.dylib", "a1probe.o", "liba1probe.dylib")]
    paths += list((output / "native-tmp").rglob("*.o"))
    for path in paths:
        if path.is_file():
            binaries[str(path.relative_to(output))] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    inputs = {str(path.relative_to(ROOT)): sha256(path) for path in (ROOT / "interop/a1").rglob("*") if path.is_file()}
    for relative in ("tools/run_a1_probe.py", "tools/capture.py", "tools/inspect_ios_candidate.py", "compiler/toolchains.lock.json"):
        inputs[relative] = sha256(ROOT / relative)
    result = {"mode": mode, "status": status, "lastStage": stage,
              "iosGateA1": "BLOCKED", "deviceRun": "NOT RUN",
              "binaries": binaries, "steps": steps,
              "inputsSHA256": inputs,
              "scope": "first-party fixture only; not Minecraft/Fabric compatibility"}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graalvm-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("jvm", "desktop-aot", "ios-compile", "ios-relocatable"), required=True)
    args = parser.parse_args(argv)
    result = run(args.graalvm_home, args.output, args.mode)
    print(json.dumps({k: v for k, v in result.items() if k != "steps"}, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
