#!/usr/bin/env python3
"""Fail closed if a Fabric export omitted mods or does not match the input files."""
import hashlib
import json
import sys
from pathlib import Path


def check(report, directory):
    data=json.loads(Path(report).read_text(encoding="utf-8"))
    if data.get("status")!="FABRIC_AOT_INPUT_PREPARED":
        raise ValueError("Fabric transformation did not produce an AOT input")
    if data.get("excludedMods") or data.get("retiredJars"):
        raise ValueError("Fabric export excluded mods: " + json.dumps({
            "excludedMods": data.get("excludedMods", {}),
            "retiredJars": data.get("retiredJars", []),
        }, ensure_ascii=True, sort_keys=True))
    mods=sorted(Path(directory).glob("*.jar"))
    if not mods: raise ValueError("Fabric input contains no root mod JARs")
    expected=data.get("modSHA256",{})
    actual={}
    for p in mods:
        if p.is_symlink() or not p.is_file(): raise ValueError("Unsafe mod input: "+str(p))
        with p.open("rb") as f: actual[str(p.resolve())]=hashlib.file_digest(f,"sha256").hexdigest()
    if actual!=expected: raise ValueError("Fabric mod inputs differ from transformation report")
    jar=Path(report).parent/"client.jar"
    if not jar.is_file(): raise ValueError("Fabric transformed client missing")
    with jar.open("rb") as f: digest=hashlib.file_digest(f,"sha256").hexdigest()
    if digest!=data.get("outputJarSHA256"): raise ValueError("Fabric transformed client hash mismatch")
    return len(actual)

if __name__=="__main__":
    print("FABRIC_INPUT_VERIFIED root_mods="+str(check(sys.argv[1],sys.argv[2])))
