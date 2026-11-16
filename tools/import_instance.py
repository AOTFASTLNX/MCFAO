"""Import only declared client files from a preflighted Fabric instance; never execute code."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import unicodedata
import urllib.parse
import urllib.request
from urllib.parse import urljoin, urlsplit
from zipfile import ZipFile
from preflight import scan_pack, scan_mod_bytes, read_json_limited, validate_zip_members, safe_archive_path, tls_context
from mod_file_policy import is_metadata, content_paths, clean_staged_metadata

MAX_FILE = 96 * 1024**2
MAX_TOTAL = 2 * 1024**3
HOSTS = {"cdn.modrinth.com"}
def allowed_file(name):
    return not is_metadata(name) and safe_archive_path(name) and (name == "options.txt" or name.split("/",1)[0] in ("mods","config","resourcepacks"))

def public_endpoint(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password
            or parsed.port not in (None,443) or parsed.fragment or any(ord(c)<33 for c in url)):
        raise ValueError("Only HTTPS Modrinth CDN downloads are supported; import other licensed files locally")
    if urllib.parse.quote(parsed.path, safe="/%:@!$&'()*+,;=-._~") != parsed.path:
        raise ValueError("Download path contains unsupported characters")
    return parsed

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, public_endpoint(urljoin(req.full_url, newurl)).geturl())

def download(url, limit=MAX_FILE):
    # urllib uses the macOS system proxy and the standard *_proxy environment variables, so a
    # local proxy's fake-IP or loopback DNS answer is not rejected. The host allowlist and TLS
    # certificate/hostname verification still apply, including after redirects.
    request = urllib.request.Request(public_endpoint(url).geturl(), headers={"User-Agent": "NCL-local-import/1"})
    with urllib.request.build_opener(SafeRedirect(), urllib.request.HTTPSHandler(context=tls_context())).open(request, timeout=30) as response:
        if response.status != 200: raise ValueError(f"Download HTTP {response.status}")
        data = response.read(limit + 1)
    if len(data) > limit: raise ValueError("Download exceeds file/total budget")
    return data

def import_instance(source: Path, output: Path, fetch=download):
    if source.is_symlink(): raise ValueError("Instance source cannot be a symlink")
    report=scan_pack(source)
    if report["fatal"]: raise ValueError("Static preflight blocked import: "+json.dumps(report["findings"],ensure_ascii=False))
    output.mkdir(parents=True,exist_ok=False)
    records={};skipped=[];total=0;seen=set(); imported_mods=[]; mod_findings=[]
    def save(name,data,expected=None,size=None):
        nonlocal total
        if is_metadata(name): return
        if not allowed_file(name):
            raise ValueError("Only mods/config/resourcepacks/options.txt can be imported: "+name)
        key=unicodedata.normalize("NFC",name).casefold()
        if key in seen: raise ValueError("Imported path collision: "+name)
        seen.add(key)
        if len(data)>MAX_FILE or total+len(data)>MAX_TOTAL: raise ValueError("Import size budget exceeded")
        if size is not None and len(data)!=size: raise ValueError("Declared file size mismatch: "+name)
        if expected and any(hashlib.new(algorithm,data).hexdigest()!=digest.lower() for algorithm,digest in expected.items() if algorithm in ("sha1","sha512")):
            raise ValueError("Declared file hash mismatch: "+name)
        if name.startswith("mods/") and name.lower().endswith(".jar"):
            scan_mod_bytes(data,name,mod_findings,imported_mods)
            if any(row["severity"] == "error" for row in mod_findings):
                raise ValueError("Downloaded/imported Mod metadata failed preflight: " + name)
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        total+=len(data);records[name]={"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}
    try:
        if source.is_file():
            with ZipFile(source) as archive:
                findings=[]
                if not validate_zip_members(archive,findings,str(source)): raise ValueError("Unsafe archive")
                manifest=read_json_limited(archive,"modrinth.index.json",2*1024**2)
                for row in manifest["files"]:
                    name=row["path"]
                    if is_metadata(name): continue
                    if row.get("env",{}).get("client")=="unsupported":
                        skipped.append({"path":name,"reason":"server-only as declared by manifest"});continue
                    if not allowed_file(name):
                        raise ValueError("Unsupported declared client file; no silent omission: "+name)
                    data=fetch(row["downloads"][0],min(MAX_FILE,MAX_TOTAL-total))
                    save(name,data,row["hashes"],row.get("fileSize"))
                for info in archive.infolist():
                    if info.is_dir() or is_metadata(info.filename):continue
                    for prefix in ("overrides/","client-overrides/"):
                        if info.filename.startswith(prefix):
                            name=info.filename[len(prefix):]
                            if info.file_size>MAX_FILE:raise ValueError("Override exceeds budget")
                            save(name,archive.read(info));break
        else:
            base=next((p for p in (source/".minecraft",source/"minecraft",source) if (p/"mods").is_dir()),source)
            for directory in ("mods","config","resourcepacks"):
                root=base/directory
                if root.is_symlink():raise ValueError("Symlink instance directory")
                for path in sorted(content_paths(root)) if root.is_dir() else []:
                    if path.is_symlink():raise ValueError("Symlink instance file")
                    if path.is_file():
                        if path.stat().st_size>MAX_FILE:raise ValueError("Instance file exceeds budget")
                        save(str(path.relative_to(base)),path.read_bytes())
            options = base / "options.txt"
            if options.is_symlink(): raise ValueError("Symlink instance options")
            if options.is_file():
                if options.stat().st_size > MAX_FILE: raise ValueError("Instance options exceed budget")
                save("options.txt", options.read_bytes())
        (output/"mods").mkdir(exist_ok=True)
        clean_staged_metadata(output)
        result={"status":"INSTANCE_FILES_IMPORTED","root":str(output.resolve()),"mods":str((output/"mods").resolve()),"files":records,"skipped":skipped,
                "preflight":report,"importedMods":imported_mods,"modFindings":mod_findings,
                "validation":"STATIC_ONLY; dependency resolution / MDAF / AOT / runtime not yet executed"}
        (output/"import.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
        return result
    except Exception as error:
        (output/"import-failure.json").write_text(json.dumps({"status":"BLOCKED","reason":str(error),"importedFiles":records},indent=2))
        raise

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--source",required=True,type=Path);parser.add_argument("--output",required=True,type=Path);args=parser.parse_args()
    print(json.dumps(import_instance(args.source,args.output),ensure_ascii=False))
