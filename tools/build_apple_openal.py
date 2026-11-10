#!/usr/bin/env python3
"""Build a signed-bundle library handle for the public iOS OpenAL framework."""
import argparse
import json
import sys
from pathlib import Path
from bootstrap_toolchain import sha256
from capture import ROOT,capture
from graphics_common import register_tree
from build_c0_harness import validate_dylib

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sdk',choices=('iphoneos','iphonesimulator'),default='iphonesimulator');a=p.parse_args(argv)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);source=ROOT/'ios/audio/openal_anchor.c'
    target='arm64-apple-ios17.0'+('-simulator' if a.sdk=='iphonesimulator' else '');binary=out/'libopenal.dylib'
    run=capture(['xcrun','--sdk',a.sdk,'clang','-target',target,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations','-dynamiclib',str(source),'-framework','OpenAL','-install_name','@rpath/libopenal.dylib','-o',str(binary)],out/'compile',120)
    result={'status':'BLOCKED','target':target,'scope':'public Apple OpenAL implementation; optional extensions depend on actual device capabilities',
            'sourcesSHA256':{str(f.relative_to(ROOT)):sha256(f) for f in [source,Path(__file__)]}}
    if not run['exitCode']:
        validate_dylib(binary,a.sdk=='iphonesimulator');result.update(status='APPLE_OPENAL_BUILT',binarySHA256=sha256(binary))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    register_tree(out,[sys.executable,'-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    print(json.dumps(result,indent=2));return 0 if result['status']=='APPLE_OPENAL_BUILT' else 2

if __name__=='__main__':raise SystemExit(main())
