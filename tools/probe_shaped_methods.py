#!/usr/bin/env python3
"""Measure how Native Image type-flow construction scales with a method's bytecode shape.

The points-to analysis builds one type-flow graph per reachable method and, while iterating that
graph, keeps a **full copy** of the node->flow map for every control split and every invoke that
carries exception edges (`PostOrderNodeIterator.nodeStates`). Retained build-host memory for one
method therefore scales with

    snapshots x entries-per-snapshot

which is quadratic in the method's size. `net.minecraft.world.level.block.Blocks.<clinit>` is the
real-world case (40199 bytes, 7331 invokes, 12966 instructions). This tool reproduces the same
shape with a **first-party generated fixture**, so the scaling law and a candidate mitigation can
be measured without touching Minecraft, GraalVM sources or the client jar.

Two shapes are generated:
  --parts 1   one giant <clinit> (the shape Minecraft's registry initialisers have)
  --parts K   the same work split into K smaller methods chained from <clinit>

If memory is quadratic in per-method size, the split shape must complete with a heap where the
single shape fails.

The output is an experiment record for the Mac build JVM only. It is not Gate evidence, it does
not measure iOS, and it does not prove that splitting is sufficient for the real client.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from capture import ROOT, capture
from bootstrap_toolchain import sha256
from run_b0_reference import execute, sandbox_policy

HEADER = """public final class Shaped {
    static final Object[] SINK = new Object[64];
    /** Counts calls, so a transformation that executes the body twice cannot hide behind idempotence. */
    static int RUNS;
    static Object make(int index) { return new Object[]{Integer.valueOf(index), "s" + index}; }
    static void keep(int index, Object value) { RUNS++; SINK[index & 63] = value; }
"""


def generate_source(invokes: int, parts: int) -> str:
    """Generate a class whose static initialiser performs `invokes` calls, in 1 or `parts` methods."""
    if invokes < 1:
        raise ValueError("invokes must be positive")
    if parts < 1:
        raise ValueError("parts must be positive")
    body = HEADER
    per_part = [invokes // parts + (1 if index < invokes % parts else 0) for index in range(parts)]
    start = 0
    for index, count in enumerate(per_part):
        if parts == 1:
            name = "<clinit>"
        else:
            name = "part" + str(index)
        body += "    static void %s() {\n" % name if parts > 1 else "    static {\n"
        for offset in range(count):
            body += "        keep(%d, make(%d));\n" % (start + offset, start + offset)
        body += "    }\n"
        start += count
    if parts > 1:
        body += "    static {\n"
        for index in range(parts):
            body += "        part%d();\n" % index
        body += "    }\n"
    body += "    public static void main(String[] args) { System.out.println(\"SHAPED_OK \" + SINK.length); }\n}\n"
    return body


def gc_summary(path: Path) -> dict:
    """Summarise a unified GC log: pause count, pause time and the maximum live set after a pause."""
    if not path.exists():
        return {"present": False}
    pauses = 0
    pause_seconds = 0.0
    peak_live = 0
    for line in path.read_text(errors="replace").splitlines():
        if "Pause Full" in line or "Pause Young" in line:
            pauses += 1
            tail = line.rsplit(") ", 1)[-1].split()
            for token in tail:
                if token.endswith("ms"):
                    try:
                        pause_seconds += float(token[:-2]) / 1000.0
                    except ValueError:
                        pass
                elif "->" in token and token.endswith(")"):
                    try:
                        live = int(token.split("->")[1].split("M")[0])
                        peak_live = max(peak_live, live)
                    except ValueError:
                        pass
    return {"present": True, "pauseEvents": pauses, "pauseSeconds": round(pause_seconds, 3),
            "peakLiveMebibytes": peak_live}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True, help="fresh directory for this run")
    parser.add_argument("--invokes", type=int, default=4000, help="number of calls in the initialiser")
    parser.add_argument("--parts", type=int, default=1, help="1 keeps one giant method, K splits it")
    parser.add_argument("--heap-mib", type=int, default=512, help="build-JVM heap for the analysis")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--keep-classes", action="store_true", help="keep the compiled fixture classes")
    parser.add_argument("--sandbox", action="store_true",
                        help="wrap the builder in sandbox-exec; off by default because the Native Image "
                             "toolchain check needs to execute cc, which the B0 policy denies")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("--output must not exist")
    if not 256 <= args.heap_mib <= 8192:
        parser.error("--heap-mib must be within 256..8192")
    out = args.output.absolute()
    out.mkdir(parents=True)
    manifest = json.loads((ROOT / "artifacts/b0/prepared-04/result.json").read_text())
    home = Path(manifest["javaHome"])
    driver = ROOT / "artifacts/b0/prepared-04/driver.jar"
    if sha256(home / "bin/java") != manifest["javaSHA256"]:
        parser.error("Pinned control Java changed")
    source = out / "Shaped.java"
    source.write_text(generate_source(args.invokes, args.parts))
    work = out / "work"
    (work / "tmp").mkdir(parents=True)
    (work / "native-tmp").mkdir()
    classes = work / "classes"
    classes.mkdir()
    record = {"status": "BLOCKED", "invokes": args.invokes, "parts": args.parts,
              "heapMebibytes": args.heap_mib, "source": str(source),
              "sandbox": "sandbox-exec" if args.sandbox else "none (first-party fixture)",
              "sourceSHA256": sha256(source),
              "scope": "first-party generated fixture on the Mac build JVM; analysis-phase memory only; "
                       "not Gate evidence, no iOS measurement, no Minecraft content"}
    compile_run = capture([str(home / "bin/javac"), "--release", "25", "-proc:none",
                           "-d", str(classes), str(source)], out / "compile", 120)
    if compile_run["exitCode"]:
        record["error"] = "javac failed"
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
        return 1
    policy = out / "policy.sb"
    native_image = (home / "bin/native-image").resolve(strict=True)
    text = sandbox_policy(work, home, [driver])
    # native-image is a launcher script, so the policy has to allow running it and /bin/sh.
    text += "(allow process-exec (literal " + json.dumps(str(native_image)) + "))\n"
    text += "(allow process-exec (literal \"/bin/sh\"))\n"
    policy.write_text(text)
    gc_log = work / "gc.log"
    prefix = ["/usr/bin/sandbox-exec", "-f", str(policy)] if args.sandbox else []
    command = [*prefix, str(native_image),
               "-cp", str(classes), "--no-fallback", "-O1", "--parallelism=4",
               "-H:+UnlockExperimentalVMOptions", "-H:-CheckToolchain", "-H:+ExitAfterAnalysis",
               "-J-Xmx" + str(args.heap_mib) + "m", "-J-XX:-UsePerfData",
               "-J-Djava.io.tmpdir=" + str(work / "tmp"),
               "-H:TempDirectory=" + str(work / "native-tmp"),
               "-J-Xlog:gc*:file=" + str(gc_log) + ":uptime,level,tags",
               "Shaped"]
    started = time.time()
    run = execute(command, out / "analysis", work, timeout=args.timeout, cpu_seconds=args.timeout)
    record.update({"exitCode": run["exitCode"], "timedOut": run["timedOut"],
                   "wallSeconds": round(time.time() - started, 3),
                   "childCPUSeconds": run.get("childCPUSeconds"),
                   "command": command, "gc": gc_summary(gc_log)})
    stdout = (out / "analysis" / "stdout.log").read_text(errors="replace")
    stderr = (out / "analysis" / "stderr.log").read_text(errors="replace")
    out_of_memory = "OutOfMemoryError" in stdout + stderr
    completed = run["exitCode"] == 0 and not run["timedOut"] and not out_of_memory
    record["outOfMemory"] = out_of_memory
    failure = [line for line in (stdout + stderr).splitlines()
               if "Fatal error" in line or "OutOfMemoryError" in line]
    record["failureHeadline"] = failure[0][:400] if failure else None
    record["status"] = "ANALYSIS_COMPLETED" if completed else "ANALYSIS_FAILED"
    (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    if not args.keep_classes:
        shutil.rmtree(classes, ignore_errors=True)
    print(json.dumps({key: record[key] for key in
                      ("status", "invokes", "parts", "heapMebibytes", "exitCode", "wallSeconds",
                       "outOfMemory", "gc")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
