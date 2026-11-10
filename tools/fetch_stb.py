#!/usr/bin/env python3
"""Fetch checksum-pinned STB headers only; never execute an upstream build script."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from bootstrap_toolchain import sha256
from capture import ROOT
from graphics_common import register_tree

CACHE=ROOT/".cache/graphics/stb-lwjgl-3.4.1"
LOCK=ROOT/"compiler/stb.lock.json"

def verify_sources(directory: Path=CACHE,lock: dict|None=None)->Path:
    lock=json.loads(LOCK.read_text()) if lock is None else lock
    for name,entry in lock["files"].items():
        path=directory/name
        if not path.is_file() or sha256(path)!=entry["sha256"]:
            raise ValueError("Missing or modified pinned STB header: "+str(path)+"; run tools/fetch_stb.py")
    return directory

def main():
    lock=json.loads(LOCK.read_text());CACHE.mkdir(parents=True,exist_ok=True)
    try:
        for name,entry in lock["files"].items():
            path=CACHE/name
            if path.exists():
                if sha256(path)!=entry["sha256"]:raise ValueError("Modified STB header preserved: "+str(path))
                continue
            temporary=CACHE/(name+".download")
            subprocess.run(["/usr/bin/curl","-fsSL","--proto","=https","--max-time","60",entry["url"],"-o",str(temporary)],check=True)
            if sha256(temporary)!=entry["sha256"]:raise ValueError("Downloaded STB checksum mismatch: "+name)
            temporary.rename(path)
        verify_sources()
        register_tree(CACHE,[sys.executable,"-B",str(Path(__file__).resolve())],kind="CACHE")
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        print(str(exc),file=sys.stderr);return 1
    print(json.dumps({"status":"PINNED_STB_HEADERS_VERIFIED","cache":str(CACHE),"files":len(lock["files"])}))
    return 0

if __name__=="__main__":raise SystemExit(main())
