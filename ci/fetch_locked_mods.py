#!/usr/bin/env python3
"""Fetch verified public mod inputs; never execute or unpack their contents."""
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ALLOWED={"cdn.modrinth.com", "mediafilez.forgecdn.net"}
MAX_BYTES=96*1024*1024

def check_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!="https" or p.hostname not in ALLOWED or p.username or p.password or p.port not in (None,443):
        raise ValueError("Untrusted mod download URL")
    return url

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req,fp,code,msg,headers,check_url(newurl))

def fetch(lock, output):
    obj=json.loads(Path(lock).read_text(encoding="utf-8"))
    items=obj["files"]
    if obj.get("minecraft")!="26.1.2" or len(items)!=53:
        raise ValueError("Unexpected Recollection3 lock")
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    names=set();opener=urllib.request.build_opener(SafeRedirect())
    for item in items:
        name=item["name"]; size=item["size"]; expected=item["sha512"]
        if not isinstance(name,str) or Path(name).name!=name or not name.endswith(".jar") or name.casefold() in names:
            raise ValueError("Unsafe or duplicate mod filename")
        names.add(name.casefold())
        if not isinstance(size,int) or not 0<size<=MAX_BYTES or len(expected)!=128 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("Invalid size or SHA-512")
        req=urllib.request.Request(check_url(item["url"]),headers={"User-Agent":"FabricAOT-build/1.0"})
        temp=output/(name+".part"); target=output/name; total=0; digest=hashlib.sha512()
        try:
            with opener.open(req,timeout=90) as src,temp.open("xb") as dst:
                while True:
                    chunk=src.read(1024*1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total>size: raise ValueError("Download exceeds locked size")
                    digest.update(chunk);dst.write(chunk)
            if total!=size or digest.hexdigest()!=expected:raise ValueError("Mod size/hash mismatch: "+name)
            os.replace(temp,target)
        finally:
            if temp.exists():temp.unlink()
        print("verified",name,flush=True)
    return len(names)

if __name__=="__main__":print("LOCKED_MOD_INPUTS_PASS count=",fetch(sys.argv[1],sys.argv[2]))
