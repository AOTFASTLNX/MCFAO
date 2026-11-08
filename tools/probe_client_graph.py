#!/usr/bin/env python3
"""Analyze the real locally owned client entry graph; this is not a game runtime or C0 acceptance."""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT
from run_b0_reference import execute, require_run, sandbox_policy
from client_graph_diagnostics import audit_metadata, parse_time_rss, read_analysis_statistics, summarize_gc_logs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--heap-gib", type=int, choices=(6, 8), default=6)
    parser.add_argument("--builder-gc", choices=("parallel", "g1"), default="parallel")
    args = parser.parse_args(argv)
    if json.loads((ROOT / "artifacts/evidence/b1-user-device-run-01/result.json").read_text())["gateB1"] != "PASS":
        parser.error("Confirmed B1 device behavior required")
    prepared = ROOT / "artifacts/b0/prepared-04"
    manifest = json.loads((prepared / "result.json").read_text())
    home = Path(manifest["javaHome"])
    if sha256(home / "bin/java") != manifest["javaSHA256"]:
        parser.error("Java changed")
    libraries = []
    for entry in manifest["referenceLibraries"]:
        path = Path(entry["path"])
        # This isolates the core client graph from Loader/bootstrap/Mod transformation.
        if any(piece in path.name for piece in ["fabric-loader-", "sponge-mixin-", "intermediary-"]):
            continue
        if sha256(path) != entry["sha256"]:
            parser.error("Reference library changed: " + str(path))
        libraries.append(path)
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    sources=output/"source"
    for name in ["probe_client_graph.py","client_graph_diagnostics.py","run_b0_reference.py"]:
        sources.mkdir(exist_ok=True)
        shutil.copy2(ROOT/"tools"/name,sources/name)
    work = output / "work"
    for name in ["tmp", "home", "caps"]:
        (work / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "artifacts/b1/ios-probe-03/work/caps", work / "caps", dirs_exist_ok=True)
    driver = prepared / "driver.jar"
    if sha256(driver) != manifest["binaries"]["driver.jar"]["sha256"]:
        parser.error("Control driver changed")
    runtime_dir = ROOT / "artifacts/b1/runtime-ios"
    runtime = json.loads((runtime_dir / "result.json").read_text())
    if runtime.get("target") != "arm64-apple-ios17.0" or runtime.get("status") != "COMPILED":
        parser.error("Actual iPhoneOS static runtime required")
    runtime_files = []
    for entry in runtime["archives"].values():
        path = Path(entry["path"])
        if sha256(path) != entry["sha256"]: parser.error("Static runtime changed")
        runtime_files.append(path)
    policy = sandbox_policy(work, home, [*libraries, driver, *runtime_files])
    executable = (home / "bin/native-image").resolve(strict=True)
    policy += '(allow process-exec (literal ' + json.dumps(str(executable)) + '))\n'
    compiler = Path(subprocess.check_output(["/usr/bin/xcrun", "--find", "clang"], text=True).strip()).resolve(strict=True)
    policy += '(allow file-read* (literal ' + json.dumps(str(compiler)) + '))\n'
    policy += '(allow process-exec (literal ' + json.dumps(str(compiler)) + '))\n'
    policy_file = output / "policy.sb"
    policy_file.write_text(policy)
    base = ["/usr/bin/sandbox-exec", "-f", str(policy_file)]
    control = output / "outside-control.txt"
    control.write_text("first-party-client-analysis-control\n")
    outside_write = output / "outside-write.txt"
    result = {"status":"BLOCKED", "gateC0":"BLOCKED", "mode":"client-graph-diagnostic",
              "scope":"real net.minecraft.client.main.Main reachability only; no game execution, auth arguments or rendering",
              "classpathSHA256":{str(p):sha256(p) for p in libraries},
              "gateC1":"NOT RUN", "gateC2":"NOT RUN", "heapGiB":args.heap_gib,
              "targetCodeGeneration":"NOT RUN", "targetExecution":"NOT RUN",
              "fullClientFabricTransformation":"NOT RUN",
              "analysisCompleted":False, "builderJfrEnabled":False,
              "builderGC":args.builder_gc,
              "builderSHA256":sha256(Path(__file__)),
              "diagnosticsHelperSHA256":sha256(ROOT/"tools/client_graph_diagnostics.py")}
    try:
        host = subprocess.run(["/usr/bin/memory_pressure", "-Q"], capture_output=True, text=True, timeout=10)
        (output/"host-memory-before.log").write_text(host.stdout+host.stderr)
        import re
        physical = re.search(r"system has (\d+)", host.stdout)
        free = re.search(r"memory free percentage:\s*(\d+)%", host.stdout)
        if host.returncode or not physical or not free:
            raise RuntimeError("Cannot establish host memory budget")
        result["hostMemory"]={"physicalBytes":int(physical.group(1)), "availablePercent":int(free.group(1)),
                              "heapLimitGiB":args.heap_gib, "check":"preflight only; not an RSS limit"}
        if args.heap_gib*1024**3 > int(physical.group(1))*0.45 or int(free.group(1)) < (45 if args.heap_gib==8 else 35):
            raise RuntimeError("Host memory headroom below bounded experiment threshold")
        if shutil.disk_usage(output).free < 8*1024**3:
            raise RuntimeError("Less than 8 GiB free disk headroom")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1",0));listener.listen(1);listener.settimeout(0.05)
            step=output/"sandbox-probe"
            check=execute([*base,str(home/"bin/java"),"-XX:+DisableAttachMechanism","-XX:-UsePerfData","-Xmx128m",
                "-Duser.home="+str(work/"home"),"-Djava.io.tmpdir="+str(work/"tmp"),"-cp",str(driver),
                "fabricaot.b0.bootstrap.SandboxProbe",str(control),str(outside_write),str(listener.getsockname()[1])],step,work)
            require_run(check,step,"B0_SANDBOX_PASS")
            if outside_write.exists():raise RuntimeError("Outside write allowed")
            try:
                connection,_=listener.accept();connection.close();raise RuntimeError("Network allowed")
            except socket.timeout:pass
        result["sandboxProbe"]="PASS"
        cmd=[*base,str(executable),"--no-fallback","-O1","--parallelism=4",f"-J-Xmx{args.heap_gib}g","-J-XX:-UsePerfData",
             "-J-Duser.home="+str(work/"home"),"-J-Djava.io.tmpdir="+str(work/"tmp"),"-H:+UnlockExperimentalVMOptions",
             "--shared","--verbose","--diagnostics-mode","-H:+PrintAnalysisStatistics",
             "-H:BuildOutputJSONFile="+str(work/"build-output.json"),
             "-J-Xlog:gc*,safepoint:file="+str(work/"gc.log")+":time,uptime,level,tags:filecount=2,filesize=8M",
             "-H:-CheckToolchain","-H:CCompilerPath="+str(compiler),"-H:CLibraryPath="+str(runtime_dir),"-H:PageSize=16384","-Dsvm.targetName=iOS","-Dsvm.targetArch=arm64",
             "-Dsvm.platform=org.graalvm.nativeimage.Platform$IOS_AARCH64","-H:+ExitAfterAnalysis","-H:+UseCAPCache",
             "-H:CAPCacheDir="+str(work/"caps"),"-H:TempDirectory="+str(work/"native-tmp"),
             "--initialize-at-run-time=net.minecraft,com.mojang,org.lwjgl,com.microsoft,io.netty",
             "--enable-native-access=ALL-UNNAMED","-cp",":".join(map(str,libraries)),"-o",str(work/"client-graph"),
             "net.minecraft.client.main.Main"]
        if args.builder_gc=="g1":
            # These flags affect the Mac build JVM, not the target iOS collector.
            cmd[cmd.index("-J-XX:-UsePerfData"):cmd.index("-J-XX:-UsePerfData")]=[
                "-J-XX:-UseParallelGC","-J-XX:+UseG1GC"]
        audit=audit_metadata(libraries,cmd)
        (output/"metadata-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
        if audit["preserveAllOccurrences"]:raise RuntimeError("Broad preservation requires review before analysis")
        built=execute(["/usr/bin/time","-l",*cmd],output/"analysis",work,timeout=600,cpu_seconds=1800)
        result["analysisExitCode"]=built["exitCode"]
        result["timedOut"]=built["timedOut"]
        result["childCPUSeconds"]=built["childCPUSeconds"]
        result["outputLimitExceeded"]=built["outputLimitExceeded"]
        result["wallSeconds"]=built["finishedUnix"]-built["startedUnix"]
        result["maximumResidentSetBytes"]=parse_time_rss((output/"analysis/stderr.log").read_text())
        result["analysisStatistics"]=read_analysis_statistics(work)
        result["buildOutputJSONPresent"]=(work/"build-output.json").exists()
        logs=sorted(work.glob("gc.log*"),key=lambda p:p.stat().st_mtime_ns)
        result["gcSummary"]=summarize_gc_logs("\n".join(p.read_text(errors="replace") for p in logs))
        result["analysisCompleted"]=bool(built["exitCode"]==0 and not built["timedOut"]
            and result["analysisStatistics"] and not built["outputLimitExceeded"])
        result["status"]="ANALYZED" if result["analysisCompleted"] else "BLOCKED"
    except Exception as error:result["error"]=str(error)
    result["filesSHA256"]={str(p.relative_to(output)):sha256(p) for p in output.rglob("*") if p.is_file() and not p.is_symlink() and p.name!="result.json"}
    (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ['filesSHA256','classpathSHA256']},indent=2))
    return 0 if result["status"]=="ANALYZED" else 2


if __name__=="__main__":raise SystemExit(main())
