#!/usr/bin/env python3
"""Register graphics experiment evidence in the single central AAR, without cleaning.

Native builders register their own reproducible outputs. This records the remaining historical
experiments and Xcode products; symlinked build trees are recorded without recursive traversal.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from capture import ROOT

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--paths",type=Path,nargs='+',help="Register only these explicitly selected new experiment paths")
    args=p.parse_args(argv)
    if os.environ.get("AAR_HOME"):p.error("AAR_HOME must be unset")
    root=ROOT/"artifacts/graphics"
    aar=shutil.which("aar") or "/Users/kexin/Documents/Codex/monitor/bin/aar"
    specs=[]
    selected=[path.resolve(strict=True) for path in args.paths] if args.paths else sorted(root.iterdir())
    if any(not path.is_relative_to(root) for path in selected):p.error('Selected evidence must be under artifacts/graphics')
    for path in selected:
        report=path/"result.json" if path.is_dir() else None
        if report and report.is_file():
            data=json.loads(report.read_text())
            if not args.paths and ("sourcesSHA256" in data or data.get("status")=="SIMULATOR_METAL_DIAGNOSTIC_PASS"):continue
        recursive=path.is_dir() and not any(f.is_symlink() for f in path.rglob("*"))
        specs.append((path,"BUILD",recursive))
        if path.is_dir():
            for sub in (path/"export",path/"C0Harness.xcarchive"):
                if sub.is_dir():specs.append((sub,"DISTRIBUTION" if sub.name=="export" else "BUILD",not any(f.is_symlink() for f in sub.rglob("*"))))
            # Actual app products are separately registered when the surrounding Xcode tree has links.
            if not recursive:
                for app in path.rglob('*.app'):
                    if not app.is_symlink():specs.append((app,"BUILD",True))
    result={"centralDatabase":"/Users/kexin/Documents/Codex/monitor/registry.sqlite","registrations":[],"failures":[]}
    for path,kind,recursive in specs:
        command=[aar,"register","--path",str(path),"--project",str(ROOT),"--type",kind,
                 "--source","FabricAOT graphics evidence; per-step commands in command.json; docs/GRAPHICS_BOOTSTRAP.md","--json"]
        if recursive:command.append("--include-files")
        done=subprocess.run(command,capture_output=True,text=True,timeout=180)
        if done.returncode:result["failures"].append({"path":str(path),"error":done.stderr or done.stdout})
        else:result["registrations"].append({"path":str(path),"recursive":recursive,"receipt":json.loads(done.stdout)})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    command=[aar,"register","--path",str(args.output.resolve()),"--project",str(ROOT),"--type","GENERATED",
             "--source","Central AAR registration receipt for graphics experiments","--json"]
    receipt=subprocess.run(command,capture_output=True,text=True,timeout=30)
    if receipt.returncode:result["failures"].append({"path":str(args.output),"error":receipt.stderr or receipt.stdout})
    print(json.dumps({"registrations":len(result["registrations"]),"failures":result["failures"],"receipt":str(args.output)},indent=2))
    return 1 if result["failures"] else 0

if __name__=="__main__":raise SystemExit(main())
