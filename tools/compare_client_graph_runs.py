"""Compare two fixed-input analysis runs; never promote client or device Gates."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from bootstrap_toolchain import sha256


def normalized_command(argv: list[str], output: Path, vary="heap") -> list[str]:
    values=[arg.replace(str(output), "<OUTPUT>") for arg in argv]
    if vary=="heap":
        return [re.sub(r"^-J-Xmx\d+g$", "-J-Xmx<HEAP>g", arg) for arg in values]
    return [arg for arg in values if arg not in ("-J-XX:-UseParallelGC","-J-XX:+UseG1GC")]


def compare(left: Path, right: Path, vary="heap") -> dict:
    if vary not in ("heap","builder-gc"):raise ValueError("Unsupported experiment variable")
    left, right = left.resolve(strict=True), right.resolve(strict=True)
    a, b = [json.loads((p/"result.json").read_text()) for p in (left,right)]
    commands = [json.loads((p/"analysis/command.json").read_text())["argv"] for p in (left,right)]
    def observed_gc(directory):
        text="\n".join(p.read_text(errors="replace") for p in (directory/"work").glob("gc.log*"))
        collectors=re.findall(r"\] Using (Parallel|G1)\s*$",text,re.MULTILINE)
        return collectors[-1].lower() if collectors else None
    checks = {
        "commandExceptOutputPathAndVariable":normalized_command(commands[0],left,vary)==normalized_command(commands[1],right,vary),
        "sameClasspathFingerprints":a["classpathSHA256"]==b["classpathSHA256"],
        "sameDiagnosticsHelper":a["diagnosticsHelperSHA256"]==b["diagnosticsHelperSHA256"],
        "sameCAPData":{k:v for k,v in a["filesSHA256"].items() if k.startswith("work/caps/")}
                     =={k:v for k,v in b["filesSHA256"].items() if k.startswith("work/caps/")},
        "sameSandboxPolicy":(left/"policy.sb").read_text().replace(str(left),"<OUTPUT>")
                            ==(right/"policy.sb").read_text().replace(str(right),"<OUTPUT>"),
        "bothSandboxControlsPassed":a["sandboxProbe"]==b["sandboxProbe"]=="PASS",
        "noBuilderJfr":a["builderJfrEnabled"] is b["builderJfrEnabled"] is False,
        "recordedGCMatchesObservedLogs":observed_gc(left)==a.get("builderGC","parallel")
                                      and observed_gc(right)==b.get("builderGC","parallel")}
    source_equal=a["builderSHA256"]==b["builderSHA256"]
    if vary=="heap":
        checks.update(sameBuilder=source_equal,differentHeapBudgets=a["heapGiB"]!=b["heapGiB"])
    else:
        # The recorded command proves the added GC-option branch changes only
        # build-JVM GC flags, while the earlier builder source remains frozen.
        checks.update(sameHeapBudget=a["heapGiB"]==b["heapGiB"],
            differentBuilderGC=a.get("builderGC","parallel")!=b.get("builderGC","parallel"))
    if not all(checks.values()):
        raise ValueError("Not a controlled comparison: " + ", ".join(k for k,v in checks.items() if not v))
    rows=[]
    for directory, record in [(left,a),(right,b)]:
        rows.append({"directory":str(directory),"resultSHA256":sha256(directory/"result.json"),
            **{k:record.get(k) for k in ["heapGiB","analysisExitCode","wallSeconds","childCPUSeconds",
                "maximumResidentSetBytes","analysisCompleted","analysisStatistics","gcSummary","timedOut"]}})
    return {"status":"COMPARED","gateC0":"BLOCKED","gateC1":"NOT RUN","gateC2":"NOT RUN",
            "scope":"untransformed core-client analysis comparison; target generation/execution and full Fabric transformation not tested",
            "variable":vary,"checks":checks,"recordedBuilderSourcesIdentical":source_equal,"runs":rows,
            "resourceCaveat":"host load and memory pressure are observed, not controlled; RSS from Darwin time; GC values from rounded HotSpot logs"}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left",type=Path,required=True)
    parser.add_argument("--right",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--vary",choices=("heap","builder-gc"),default="heap")
    args=parser.parse_args(argv)
    report=compare(args.left,args.right,args.vary)
    with args.output.open("x") as file:json.dump(report,file,indent=2);file.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k!="runs"},indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
