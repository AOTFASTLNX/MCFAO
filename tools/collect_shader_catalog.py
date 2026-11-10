#!/usr/bin/env python3
"""Inventory vanilla shader variants through the real Java pipeline declarations, under isolation."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from bootstrap_toolchain import sha256
from capture import ROOT,capture
from graphics_common import register_tree
from run_b0_reference import sandbox_policy

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/'artifacts/b0/prepared-04/result.json').read_text());references=[];client=None
    for entry in manifest['referenceLibraries']:
        path=Path(entry['path'])
        if any(name in path.name for name in ('fabric-loader-','sponge-mixin-','intermediary-')):continue
        if sha256(path)!=entry['sha256']:raise ValueError('Changed reference dependency: '+str(path))
        references.append(path)
        if path.name=='26.1.2.jar':client=path
    if client is None:raise ValueError('Pinned client missing')
    home=ROOT/'.cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home';classes=out/'classes';classes.mkdir()
    source=ROOT/'compiler/shaders/src/fabricaot/shaders/ShaderCatalog.java';classpath=os.pathsep.join(map(str,references));data=out/'catalog'
    result={'status':'BLOCKED','scope':'static vanilla shader inventory only; no shader compilation or target rendering','sourcesSHA256':{str(f.relative_to(ROOT)):sha256(f) for f in [source,Path(__file__)]},'clientSHA256':sha256(client)}
    compile=capture([str(home/'bin/javac'),'-proc:none','-cp',classpath,'-d',str(classes),str(source)],out/'javac',120);result['javac']=compile
    if not compile['exitCode']:
        policy=out/'catalog.sb';policy.write_text(sandbox_policy(out,home,references))
        run=capture(['/usr/bin/sandbox-exec','-f',str(policy),str(home/'bin/java'),'-Xmx512m','-Duser.home='+str(out),'-Duser.dir='+str(out),'-cp',str(classes)+os.pathsep+classpath,'fabricaot.shaders.ShaderCatalog',str(client),str(data)],out/'run',90,cwd=out);result['run']=run
        if not run['exitCode'] and (data/'catalog.json').is_file():
            catalog=json.loads((data/'catalog.json').read_text());result.update(status='VANILLA_SHADER_CATALOG_COLLECTED',sources=len(catalog['rawSources']),pipelines=len(catalog['pipelines']),programs=len(catalog['programs']),catalogSHA256=sha256(data/'catalog.json'))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');register_tree(out,[sys.executable,'-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    print(json.dumps({k:v for k,v in result.items() if k not in ['javac','run','sourcesSHA256']},indent=2));return 0 if result['status']=='VANILLA_SHADER_CATALOG_COLLECTED' else 2

if __name__=='__main__':raise SystemExit(main())
