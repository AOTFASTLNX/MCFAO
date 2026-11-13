#!/usr/bin/env python3
"""Prepare the owned client for Metal and offline world startup without executing its code."""
from __future__ import annotations
import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from bootstrap_toolchain import sha256
from build_method_splitter import gradle_asm, java_home
from capture import ROOT, capture
from graphics_common import register_tree
from probe_client_graph import verify_split_runtime_input
from run_b0_reference import sandbox_policy

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--graalvm-home', type=Path)
    parser.add_argument('--asm-jars', type=Path, nargs=2, metavar=('ASM_CORE', 'ASM_TREE'))
    args=parser.parse_args(argv);client=args.client.resolve(strict=True);split=verify_split_runtime_input(client)
    if split is None:parser.error('A verified corrected split client is required')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java'
    diagnostics=ROOT/'compiler/metal-backend/tools/fabricaot/diag/PlayDiagnostics.java'
    home=args.graalvm_home.resolve(strict=True) if args.graalvm_home else java_home()
    libraries=[path.resolve(strict=True) for path in (args.asm_jars or gradle_asm().values())]
    if {path.name for path in libraries}!={'asm-9.9.jar','asm-tree-9.9.jar'}:
        raise ValueError('Exactly ASM core and tree 9.9 are required')
    classes=out/'classes';classes.mkdir();classpath=os.pathsep.join(map(str,libraries))
    result={'status':'BLOCKED','scope':'build-time Metal injection and equivalent short circuits for unsigned chat; no client execution',
            'client':str(client),'clientSHA256':sha256(client),'splitRuntimeValidation':split,
            'sourcesSHA256':{str(p.relative_to(ROOT)):sha256(p) for p in [source,diagnostics,Path(__file__)]},
            'asmJars':{str(p):sha256(p) for p in libraries}}
    compiled=capture([str(home/'bin/javac'),'--release','25','-proc:none','-Xlint:all','-cp',classpath,'-d',str(classes),str(source),str(diagnostics)],out/'compile',120)
    if compiled['exitCode']:raise RuntimeError('Injector compilation failed')
    policy=out/'transform.sb';policy.write_text(sandbox_policy(out,home,[client,*libraries]))
    command=['/usr/bin/sandbox-exec','-f',str(policy),str(home/'bin/java'),'-Xmx256m','-cp',str(classes)+os.pathsep+classpath,'fabricaot.metal.InjectBackend']
    tested=capture([*command,'--self-test'],out/'self-test',60,cwd=out)
    if tested['exitCode'] or 'BACKEND_INJECTION_SELF_TEST_PASS' not in (out/'self-test/stdout.log').read_text():raise RuntimeError('Injector self-test failed')
    jar=out/'client-26.1.2-metal.jar';run=capture([*command,str(client),str(jar),str(classes)],out/'transform',120,cwd=out)
    if run['exitCode']:raise RuntimeError('Backend injection failed')
    targets={'net/minecraft/client/Minecraft.class','net/minecraft/client/multiplayer/ClientPacketListener.class',
             'net/minecraft/client/gui/render/GuiItemAtlas.class',
             'net/minecraft/client/multiplayer/LevelLoadTracker.class',
             'net/minecraft/client/multiplayer/LevelLoadTracker$WaitingForPlayerChunk.class',
             'net/minecraft/client/renderer/LevelRenderer.class',
             'net/minecraft/client/multiplayer/ClientChunkCache.class',
             'net/minecraft/client/player/LocalPlayer.class',
             'net/minecraft/network/Connection.class',
              'net/minecraft/client/gui/screens/FaviconTexture.class',
              'net/minecraft/client/gui/render/pip/PictureInPictureRenderer.class'}
    with zipfile.ZipFile(client) as before,zipfile.ZipFile(jar) as after:
        remaining=set(after.namelist())
        changed=[name for name in before.namelist() if name in remaining and before.read(name)!=after.read(name)]
        added=sorted(set(remaining)-set(before.namelist()))
        if not targets.issubset(changed) or set(changed)-targets-{'META-INF/MANIFEST.MF'}:
            raise ValueError('Unexpected changed entries: '+repr(changed))
        if added!=['fabricaot/diag/PlayDiagnostics.class']:
            raise ValueError('Unexpected added entries: '+repr(added))
    result.update(status='BACKEND_INJECTED',outputJar=str(jar),outputJarSHA256=sha256(jar),changedEntries=changed,
                  addedEntries=added,
                  playDiagnostics='optional -Dmcfao.diag.play=true/false; level states, chunks, movement, connection failures, heartbeat and stall thread dump',
                  chatKeyWait='false secure-chat flag and null chat session short circuit; non-null session validation preserved',
                  guiItemAtlasOrigin='sample rendered item atlas in Metal texture row order',
                  guiPreviewOrigin='flip world favicon rows and undo the GL PIP blit flip only for Metal',
                  fallbackLoop='preserved',manifest='main attributes retained; stale per-entry signing sections removed',backendOrder=['fabricaot.metal.MetalBackend','com.mojang.blaze3d.opengl.GlBackend'],selfTest='PASS')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    register_tree(out,[sys.executable,'-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
