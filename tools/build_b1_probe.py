#!/usr/bin/env python3
"""Build the verified B0 first-party replay as an iOS AOT object in a restricted build workspace."""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import zipfile
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT, capture
from inspect_ios_candidate import inspect
from run_b0_reference import execute, require_run, sandbox_policy


def validate_b0_snapshot(b0: Path) -> dict:
    b0 = b0.resolve(strict=True)
    metadata = b0 / "result.json"
    if metadata.stat().st_size > 2 * 1024**2:
        raise ValueError("B0 report too large")
    reference = json.loads(metadata.read_text())
    if reference.get("gateB0") != "PASS" or reference.get("sandboxProbe") != "PASS":
        raise ValueError("Actual sandboxed B0 behavior PASS required")
    for name, expected in reference["filesSHA256"].items():
        path = b0 / name
        if path.is_symlink() or not path.resolve().is_relative_to(b0) or not path.is_file():
            raise ValueError("B0 snapshot path escaped or missing: " + name)
        if sha256(path) != expected:
            raise ValueError("B0 evidence changed: " + name)
    return reference


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b0", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    b0 = args.b0.resolve(strict=True)
    try:
        reference = validate_b0_snapshot(b0)
    except ValueError as error:
        parser.error(str(error))
    prepared = Path(reference["sourcePreparation"])
    manifest = json.loads((prepared / "result.json").read_text())
    home = Path(manifest["javaHome"])
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    work = output / "work"
    for name in ("classes", "tmp", "home", "caps"):
        (work / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(b0 / "sandbox/export", work / "classes", dirs_exist_ok=True)
    shutil.copytree(ROOT / "interop/b1/metadata", work / "classes", dirs_exist_ok=True)
    engine = [Path(e["path"]) for e in manifest["engineLibraries"]]
    for entry in manifest["engineLibraries"]:
        if sha256(Path(entry["path"])) != entry["sha256"]:
            parser.error("Pinned engine library changed")
    dependencies = [prepared / "fixture.jar", prepared / "nested.jar", *engine]
    for name in ("fixture.jar", "nested.jar", "driver.jar"):
        if sha256(prepared / name) != manifest["binaries"][name]["sha256"]:
            parser.error("Prepared fixture changed")
    classpath = ":".join(map(str, [work / "classes", *dependencies]))
    source_root = ROOT / "interop/b1/src/fabricaot/b1"
    compile_result = capture([str(home / "bin/javac"), "--release", "25", "-proc:none",
        "-cp", classpath, "-d", str(work / "classes"), str(source_root / "B1Probe.java")], output / "compile", 180)
    entry_result = None
    if compile_result["exitCode"] == 0:
        # --release hides vendor SDK modules; compile the C ABI wrapper with the
        # exact pinned Java25 SDK, as in the verified A1 build.
        entry_result = capture([str(home / "bin/javac"), "-proc:none", "--add-modules", "org.graalvm.nativeimage",
            "-cp", classpath, "-d", str(work / "classes"), str(source_root / "B1EntryPoint.java")], output / "compile-entry", 180)
    if compile_result["exitCode"] or entry_result is None or entry_result["exitCode"]:
        (output / "result.json").write_text(json.dumps({"status":"BLOCKED", "gateB1":"BLOCKED",
            "stage":"compile", "deviceRun":"NOT RUN", "b0Evidence":str(b0), "binaries":{}}, indent=2)+"\n")
        return 2
    spec = json.loads((ROOT / "compiler/toolchains.lock.json").read_text())["iosCandidate"]
    candidate = ROOT / ".cache/toolchains" / spec["file"]
    cache_info = inspect(candidate, spec)
    with zipfile.ZipFile(candidate) as archive:
        for name in cache_info["capFiles"]:
            (work / "caps" / Path(name).name).write_bytes(archive.read(name))
    readable = [*dependencies, prepared / "driver.jar"]
    policy = sandbox_policy(work, home, readable)
    native_image = (home / "bin/native-image").resolve(strict=True)
    policy += '(allow process-exec (literal ' + json.dumps(str(native_image)) + '))\n'
    policy_file = output / "policy.sb"
    policy_file.write_text(policy)
    java = [str(home / "bin/java"), "-XX:+DisableAttachMechanism", "-XX:-UsePerfData", "-Xmx128m",
            "-Duser.home=" + str(work / "home"), "-Djava.io.tmpdir=" + str(work / "tmp")]
    base = ["/usr/bin/sandbox-exec", "-f", str(policy_file)]
    control = output / "outside-control.txt"
    control.write_text("B1 first-party control\n")
    outside_write = output / "outside-write.txt"
    result = {"status": "BLOCKED", "gateB1": "BLOCKED", "deviceRun": "NOT RUN", "b0Evidence": str(b0),
              "b0ResultSHA256": sha256(b0 / "result.json"), "builderSHA256": sha256(Path(__file__)),
              "scope": "pre-transformed first-party fixture only; no Minecraft code on AOT classpath"}
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0)); listener.listen(1); listener.settimeout(0.05)
            step = output / "sandbox-probe"
            check = execute([*base, *java, "-cp", str(prepared / "driver.jar"),
                "fabricaot.b0.bootstrap.SandboxProbe", str(control), str(outside_write), str(listener.getsockname()[1])], step, work)
            require_run(check, step, "B0_SANDBOX_PASS")
            if outside_write.exists():
                raise RuntimeError("B1 workspace outside write permitted")
            try:
                connection, _ = listener.accept(); connection.close()
                raise RuntimeError("B1 workspace network permitted")
            except socket.timeout:
                pass
        result["sandboxProbe"] = "PASS"
        command = [*base, str(home / "bin/native-image"), "--no-fallback", "-O1", "--parallelism=4",
            "-J-Xmx3g", "-J-XX:-UsePerfData", "-J-Duser.home=" + str(work / "home"),
            "-J-Djava.io.tmpdir=" + str(work / "tmp"), "-H:+UnlockExperimentalVMOptions", "--shared",
            "-H:PageSize=16384", "-R:MaxHeapSize=96m", "-Dsvm.targetName=iOS", "-Dsvm.targetArch=arm64",
            "-Dsvm.platform=org.graalvm.nativeimage.Platform$IOS_AARCH64", "-H:+ExitAfterRelocatableImageWrite",
            "-H:+UseCAPCache", "-H:CAPCacheDir=" + str(work / "caps"),
            "-H:TempDirectory=" + str(work / "native-tmp"), "--enable-native-access=ALL-UNNAMED",
            "-cp", classpath, "-o", str(work / "a1probe"), "fabricaot.b1.B1Probe"]
        built = execute(command, output / "native-image", work)
        objects = list((work / "native-tmp").rglob("a1probe.o"))
        if built["exitCode"] or built["timedOut"] or len(objects) != 1:
            raise RuntimeError("Native Image object generation failed; inspect native-image logs")
        for header in work.glob("*.h"):
            shutil.copy2(header, output / header.name)
        result["status"] = "COMPILED"
    except Exception as error:
        result["error"] = str(error)
    result["binaries"] = {str(p.relative_to(output)): {"bytes": p.stat().st_size, "sha256": sha256(p)}
                          for p in work.rglob("a1probe.o") if p.is_file()}
    result["inputsSHA256"] = {str(p.relative_to(ROOT)): sha256(p) for p in (ROOT / "interop/b1").rglob("*") if p.is_file()}
    result["sandboxPolicySHA256"] = sha256(policy_file)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
