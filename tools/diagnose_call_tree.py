#!/usr/bin/env python3
"""Re-run a recorded AOT analysis with -H:+PrintAnalysisCallTree.

The saved product (work/client-graph.o and friends) is left untouched: every output path in the
recorded argv is redirected into <product>/work/diag/, because the sandbox profile recorded for
that analysis only grants read/write under <product>/work.

Usage:
    python3 -B tools/diagnose_call_tree.py artifacts/mcfao/fabric-pack-N/aot/<hash>/product

Results land in <product>/work/diag/reports/diagnostics_<timestamp>/:
    call_tree_methods_*.csv   method id, declaring class, name, descriptor, reachability
    call_tree_invokes_*.csv   caller id -> callee id
    used_methods_*.txt        methods that survived analysis
    class_initialization_*.csv build-time / run-time / simulation init policy

A call whose target resolves to ImplicitExceptions.throwNoSuchMethodError means the declaring
class could not be linked (usually a missing type or a VerifyError), so every call into it was
silently stubbed. That is the single most common failure mode in this project.
"""
import json
import subprocess
import sys
from pathlib import Path

PRODUCT = Path(sys.argv[1]).resolve()
WORK = PRODUCT / "work"
DIAG = WORK / "diag"
for sub in ("", "native-tmp", "tmp"):
    (DIAG / sub).mkdir(parents=True, exist_ok=True)

argv = json.loads((PRODUCT / "analysis" / "command.json").read_text())["argv"]
redirect = {
    str(WORK / "client-graph"): str(DIAG / "client-graph"),
    str(WORK / "native-tmp"): str(DIAG / "native-tmp"),
    str(WORK / "build-output.json"): str(DIAG / "build-output.json"),
    str(WORK / "gc.log"): str(DIAG / "gc.log"),
    str(WORK / "tmp"): str(DIAG / "tmp"),
}
out = []
for arg in argv:
    for src, dst in redirect.items():
        if arg == src or arg.startswith(src + ":"):
            arg = dst + arg[len(src):]
            break
    out.append(arg)
if str(DIAG / "client-graph") not in out:
    raise SystemExit("Recorded argv has no client-graph output path; refusing to guess")
out += ["-H:+PrintAnalysisCallTree", "-H:PrintAnalysisCallTreeType=CSV"]

print("call tree build ->", DIAG, flush=True)
with open(DIAG / "build.log", "wb") as log:
    code = subprocess.run(
        out, cwd=WORK,
        env={"PATH": "/usr/bin:/bin", "TMPDIR": str(DIAG / "tmp"), "LANG": "en_US.UTF-8"},
        stdout=log, stderr=subprocess.STDOUT,
    ).returncode
print("exit", code, flush=True)
sys.exit(code)
