#!/usr/bin/env python3
"""B0 fixture experiment: prove sandbox denials before initializing Fabric, then replay exported classes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import selectors
import shutil
import signal
import socket
import subprocess
import time
import zipfile
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT


def sandbox_policy(work: Path, java_home: Path, readable_files: list[Path]) -> str:
    def literal(path):
        return "(literal " + json.dumps(str(path), ensure_ascii=False) + ")"
    def subpath(path):
        return "(subpath " + json.dumps(str(path), ensure_ascii=False) + ")"
    reads = [subpath(p) for p in ("/System", "/usr/lib", "/Library/Apple/System", java_home, work)]
    reads += [literal(p) for p in readable_files]
    # dyld's cache finder opens the root directory on this macOS version.
    # This permits that directory only, not its descendants.
    reads += [literal(p) for p in ("/", "/dev/null", "/dev/random", "/dev/urandom")]
    return "\n".join([
        "(version 1)", "(deny default)", "(allow file-read-metadata)",
        "(allow file-read* " + " ".join(reads) + ")",
        "(allow file-write* " + subpath(work) + " " + literal("/dev/null") + ")",
        "(allow process-exec " + literal(java_home / "bin/java") + ")",
        "(allow process-fork)", "(allow process-info* (target self))",
        "(allow signal (target self))", "(allow sysctl-read)",
        # HotSpot's native system-property initialization needs local UID lookup.
        "(allow mach-lookup (global-name \"com.apple.system.opendirectoryd.libinfo\") "
        "(global-name \"com.apple.system.notification_center\"))",
    ]) + "\n"


def limits(cpu_seconds=90):
    for kind, requested in [(resource.RLIMIT_CPU, cpu_seconds), (resource.RLIMIT_FSIZE, 64 * 1024**2),
                            (resource.RLIMIT_NOFILE, 512)]:
        _, hard = resource.getrlimit(kind)
        cap = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
        resource.setrlimit(kind, (cap, cap))


def execute(argv: list[str], folder: Path, cwd: Path, *, timeout=120, cpu_seconds=90) -> dict:
    if timeout < 1 or cpu_seconds < 1:
        raise ValueError("Positive wall/CPU budgets required")
    folder.mkdir(exist_ok=False)
    env = {"PATH": "/usr/bin:/bin", "TMPDIR": str(cwd / "tmp"), "LANG": "en_US.UTF-8"}
    started = time.time()
    timed_out = False
    output_limit = False
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    with (folder / "stdout.log").open("wb") as out, (folder / "stderr.log").open("wb") as err:
        # The parent owns the log files. Sandboxed code receives only pipes, so it
        # neither needs write access to evidence nor can overwrite an earlier log.
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, preexec_fn=lambda: limits(cpu_seconds))
        deadline = time.monotonic() + timeout
        remaining = 16 * 1024**2
        killed = False
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, out)
            selector.register(process.stderr, selectors.EVENT_READ, err)
            # A child can close both output streams and continue running. Keep
            # enforcing the deadline until the process itself has exited.
            while selector.get_map() or process.poll() is None:
                if not killed and (time.monotonic() >= deadline or output_limit):
                    timed_out = not output_limit
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    killed = True
                for key, _ in selector.select(0.2):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    key.data.write(data[:remaining])
                    remaining = max(0, remaining - len(data))
                    if remaining == 0:
                        output_limit = True
        code = process.wait()
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    record = {"argv": argv, "cwd": str(cwd), "environmentKeys": sorted(env),
              "startedUnix": started, "finishedUnix": time.time(), "processID": process.pid,
              "exitCode": code, "timedOut": timed_out, "outputLimitExceeded": output_limit,
              "wallBudgetSeconds": timeout, "cpuBudgetSeconds": cpu_seconds,
              "childCPUSeconds": (usage_after.ru_utime + usage_after.ru_stime) - (usage_before.ru_utime + usage_before.ru_stime),
              "logs": {n: {"bytes": (folder / n).stat().st_size,
              "sha256": sha256(folder / n)} for n in ("stdout.log", "stderr.log")}}
    (folder / "command.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def require_run(record, folder, marker):
    if record["exitCode"] != 0 or record["timedOut"] or marker not in (folder / "stdout.log").read_text().splitlines():
        raise RuntimeError("Stage failed: " + str(folder) + "; read stdout.log/stderr.log")


def negative_control_ok(record: dict, stdout: str, stderr: str) -> bool:
    return (record["exitCode"] != 0 and not record["timedOut"]
            and "B0_REPLAY_PASS" not in stdout.splitlines()
            and "AssertionError: real Mixin did not change result to 42" in stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    prepared = args.prepared.resolve(strict=True)
    manifest = json.loads((prepared / "result.json").read_text())
    if manifest.get("status") != "PREPARED" or not Path("/usr/bin/sandbox-exec").is_file():
        parser.error("Prepared fixture and macOS sandbox-exec required")
    for path, expected in manifest["inputsSHA256"].items():
        if sha256(ROOT / path) != expected:
            parser.error("Source changed; prepare again: " + path)
    if json.loads((ROOT / "artifacts/evidence/a0-desktop-reference/result.json").read_text())["gateA0"] != "PASS":
        parser.error("A0 required")
    if json.loads((ROOT / "artifacts/evidence/a1-user-device-run-03/result.json").read_text())["iosGateA1"] != "PASS":
        parser.error("A1 required")
    home = Path(manifest["javaHome"])
    if sha256(home / "bin/java") != manifest["javaSHA256"]:
        parser.error("Java executable changed")
    for name, expected in manifest["binaries"].items():
        if sha256(prepared / name) != expected["sha256"]:
            parser.error("Fixture changed: " + name)
    for entry in manifest["referenceLibraries"] + manifest["engineLibraries"]:
        if sha256(Path(entry["path"])) != entry["sha256"]:
            parser.error("Library changed: " + entry["path"])
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    work = output / "sandbox"
    for name in ("tmp", "home", "game/mods", "export"):
        (work / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(prepared / "fixture.jar", work / "game/mods/fabricaot-b0.jar")
    readable = [prepared / n for n in ("driver.jar", "fixture.jar", "nested.jar")]
    readable += [Path(e["path"]) for e in manifest["referenceLibraries"] + manifest["engineLibraries"]]
    policy = sandbox_policy(work, home, readable)
    policy_file = output / "policy.sb"
    policy_file.write_text(policy)
    java = [str(home / "bin/java"), "-XX:+DisableAttachMechanism", "-XX:-UsePerfData", "-Xms16m", "-Xmx256m",
            "-XX:MaxMetaspaceSize=256m", "-XX:ReservedCodeCacheSize=64m", "-Djava.awt.headless=true",
            "-Duser.home=" + str(work / "home"), "-Djava.io.tmpdir=" + str(work / "tmp")]
    base = ["/usr/bin/sandbox-exec", "-f", str(policy_file), *java]
    result = {"status": "BLOCKED", "gateB0": "BLOCKED", "gateB1": "BLOCKED",
              "scope": "audited first-party fixture only; no game main or user modpack execution",
              "sandboxPolicySHA256": sha256(policy_file), "sourcePreparation": str(prepared),
              "securityScope": "file content read/write, loopback connect, CPU/time/file-size/fd limits; not full D0 certification"}
    try:
        # These are our own harmless controls, outside the only writable/readable work directory.
        forbidden = output / "outside-control.txt"
        forbidden.write_text("first-party-sandbox-control\n")
        forbidden_write = output / "outside-write.txt"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(0.05)
            port = listener.getsockname()[1]
            step = output / "sandbox-probe"
            record = execute([*base, "-cp", str(prepared / "driver.jar"),
                "fabricaot.b0.bootstrap.SandboxProbe", str(forbidden), str(forbidden_write), str(port)], step, work)
            require_run(record, step, "B0_SANDBOX_PASS")
            if forbidden_write.exists():
                raise RuntimeError("Sandbox permitted outside write")
            try:
                connection, _ = listener.accept()
                connection.close()
                raise RuntimeError("Sandbox permitted loopback connection")
            except socket.timeout:
                pass
        result["sandboxProbe"] = "PASS"
        reference_cp = [str(prepared / "driver.jar"), *[e["path"] for e in manifest["referenceLibraries"]]]
        reference = [*base, "--enable-native-access=ALL-UNNAMED", "-javaagent:" + str(prepared / "driver.jar"),
            "-Db0.export=" + str(work / "export"), "-Dfabric.noGui=true", "-Dfabric.gameMappingNamespace=official",
            "-Dfabric.modsFolder=" + str(work / "game/mods"), "-cp", os.pathsep.join(reference_cp),
            "fabricaot.b0.bootstrap.CaptureMain", "--version", "26.1.2", "--gameDir", str(work / "game")]
        step = output / "reference"
        require_run(execute(reference, step, work), step, "B0_REFERENCE_PASS")
        target_name = "net/minecraft/fabricaot_fixture/Target.class"
        transformed = work / "export" / target_name
        with zipfile.ZipFile(prepared / "fixture.jar") as archive:
            original = archive.read(target_name)
        if not transformed.is_file() or hashlib.sha256(original).hexdigest() == sha256(transformed):
            raise RuntimeError("Target final class bytes not captured/changed")
        engine = [e["path"] for e in manifest["engineLibraries"]]
        replay_cp = [str(work / "export"), str(prepared / "fixture.jar"), str(prepared / "nested.jar"), *engine]
        step = output / "replay"
        replay = [*base, "-cp", os.pathsep.join(replay_cp), "fabricaot.b0.ReplayMain"]
        require_run(execute(replay, step, work), step, "B0_REPLAY_PASS")
        behavior = "B0_BEHAVIOR mixed=42 widened=7 parent=1 nested=1"
        if any(behavior not in (output / phase / "stdout.log").read_text().splitlines()
               for phase in ("reference", "replay")):
            raise RuntimeError("Reference/replay behavior mismatch")
        step = output / "untransformed-negative"
        record = execute([*base, "-cp", os.pathsep.join(replay_cp[1:]), "fabricaot.b0.ReplayMain"], step, work)
        if not negative_control_ok(record, (step / "stdout.log").read_text(), (step / "stderr.log").read_text()):
            raise RuntimeError("Untransformed negative control did not fail as expected")
        result.update(status="PASS", gateB0="PASS", transformedTargetSHA256=sha256(transformed),
                      originalTargetSHA256=hashlib.sha256(original).hexdigest(), negativeControl="PASS")
    except Exception as error:
        result["error"] = str(error)
    result["filesSHA256"] = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob("*"))
                             if p.is_file() and not p.is_symlink() and p.name != "result.json"}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "filesSHA256"}, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
