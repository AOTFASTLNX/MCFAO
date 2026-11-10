#!/usr/bin/env python3
"""Copy only hash-verified assets from an owned launcher cache into research build inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import sys
import ssl
import urllib.request
from pathlib import Path
from bootstrap_toolchain import sha256
from graphics_common import register_tree

def fetch_verified(url:str,target:Path,size:int,digest:str):
    context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    target.parent.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen(url,context=context,timeout=45) as response:
        if response.url!=url:raise ValueError('Unexpected asset redirect')
        data=response.read(size+1)
    if len(data)!=size or hashlib.sha1(data).hexdigest()!=digest:raise ValueError('Downloaded asset fingerprint mismatch')
    with target.open('xb') as stream:stream.write(data)

def verified_assets(source:Path, metadata:dict,download:Path|None=None):
    if metadata.get('id')!='26.1.2':raise ValueError('Exact 26.1.2 version metadata required')
    spec=metadata['assetIndex'];index_id=spec['id']
    if not re.fullmatch(r'[0-9]+',index_id):raise ValueError('Invalid asset index ID')
    index=source/'indexes'/f'{index_id}.json'
    if index.is_symlink() or not index.is_file() or index.stat().st_size!=spec['size'] or hashlib.sha1(index.read_bytes()).hexdigest()!=spec['sha1']:
        if download is None:raise ValueError('Asset index fingerprint mismatch')
        digest=spec['sha1']
        if not re.fullmatch(r'[0-9a-f]{40}',digest) or not 0<spec['size']<=2*1024**2:raise ValueError('Invalid asset index metadata')
        url=f'https://piston-meta.mojang.com/v1/packages/{digest}/{index_id}.json'
        if spec['url']!=url:raise ValueError('Unexpected official asset index origin')
        index=download/'indexes'/f'{index_id}.json'
        fetch_verified(url,index,spec['size'],digest)
    objects=json.loads(index.read_text())['objects'];files={}
    if len(objects)>20000:raise ValueError('Asset count budget exceeded')
    for info in objects.values():
        digest=info['hash'];size=info['size']
        if not re.fullmatch(r'[0-9a-f]{40}',digest) or not isinstance(size,int) or not 0<=size<=128*1024**2:raise ValueError('Invalid object metadata')
        relative=Path('objects')/digest[:2]/digest;path=source/relative
        valid=False
        if not path.is_symlink() and path.resolve().is_relative_to(source.resolve()) and path.is_file() and path.stat().st_size==size:
            with path.open('rb') as stream:valid=hashlib.file_digest(stream,'sha1').hexdigest()==digest
        if not valid:
            if download is None:raise ValueError('Missing or invalid asset: '+str(relative))
            path=download/relative
            if not path.is_file():fetch_verified(f'https://resources.download.minecraft.net/{digest[:2]}/{digest}',path,size,digest)
            elif path.is_symlink() or path.stat().st_size!=size or hashlib.sha1(path.read_bytes()).hexdigest()!=digest:raise ValueError('Modified downloaded asset')
        files[relative]=path
    if sum(p.stat().st_size for p in files.values())>1024**3:raise ValueError('Asset byte budget exceeded')
    return index_id,index,files

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--version-metadata',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fetch-missing',action='store_true',help='Fetch pinned missing assets from the official Mojang origins into the new output')
    args=p.parse_args(argv)
    metadata=args.version_metadata.resolve(strict=True);source=args.source.resolve(strict=True)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);assets=out/'assets'
    index_id,index,files=verified_assets(source,json.loads(metadata.read_text()),out/'downloaded' if args.fetch_missing else None)
    all_files={Path('indexes')/index.name:index,**files}
    for relative,path in all_files.items():
        target=assets/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    result={'status':'OWNED_ASSETS_VERIFIED_STAGED','assetIndex':index_id,'source':str(source),
            'metadataSHA256':sha256(metadata),'indexSHA256':sha256(index),'objects':len(files),
            'bytes':sum(p.stat().st_size for p in files.values()),'sourcesSHA256':{str(Path(__file__).resolve()):sha256(Path(__file__))},
            'scope':'local owned assets only; no accounts, access tokens, worlds or Mods'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    register_tree(out,[sys.executable,'-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
