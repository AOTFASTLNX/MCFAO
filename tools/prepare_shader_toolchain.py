#!/usr/bin/env python3
"""Build pinned host-only GLSL/SPIRV-Cross tools with no global installation."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from bootstrap_toolchain import sha256
from capture import ROOT
from graphics_common import register_tree
from run_b0_reference import execute

CACHE=ROOT/".cache/graphics/shader-toolchain"
LOCK=ROOT/"compiler/graphics-toolchain.lock.json"

def extract(archive: Path,directory: Path):
    with tarfile.open(archive,"r:gz") as source:
        members=source.getmembers()
        if len(members)>30000 or sum(m.size for m in members)>2*1024**3:
            raise ValueError("Shader tool archive exceeds extraction budget")
        if not directory.exists():
            directory.mkdir(parents=True)
            source.extractall(directory,members=members,filter="data")
        # Verify regular files against the pinned archive even when reusing a cache.
        for member in members:
            path=directory/member.name
            if not path.resolve().is_relative_to(directory.resolve()):raise ValueError("Escaping tool archive path")
            if member.isfile():
                if path.is_symlink() or not path.is_file():raise ValueError("Missing/linked cached tool source: "+str(path))
                digest=hashlib.sha256()
                with source.extractfile(member) as stream:
                    while data:=stream.read(1024*1024):digest.update(data)
                if sha256(path)!=digest.hexdigest():raise ValueError("Modified cached tool source: "+str(path))

def cache_inputs()->dict:
    lock=json.loads(LOCK.read_text());roots={}
    for name,spec in lock.items():
        path=CACHE/"archives"/spec["file"];path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            temporary=path.with_suffix(path.suffix+".part")
            if temporary.exists():raise ValueError("Interrupted archive preserved: "+str(temporary))
            subprocess.run(["/usr/bin/curl","-fsSL","--proto","=https","--max-time","180",spec["url"],"-o",str(temporary)],check=True)
            if sha256(temporary)!=spec["sha256"]:raise ValueError("Shader tool download checksum mismatch")
            temporary.rename(path)
        if path.stat().st_size!=spec["size"] or sha256(path)!=spec["sha256"]:raise ValueError("Changed shader tool archive: "+str(path))
        directory=CACHE/name;extract(path,directory)
        children=list(directory.iterdir())
        if len(children)!=1 or not children[0].is_dir():raise ValueError("Unexpected shader tool root: "+name)
        roots[name]=children[0]
    return roots

def policy(work: Path)->str:
    def sub(path):return '(subpath '+json.dumps(str(path))+')'
    return '\n'.join(['(version 1)','(deny default)','(allow file-read-metadata)',
        '(allow file-read* '+ ' '.join(sub(p) for p in ['/System','/usr','/bin','/Library/Apple/System','/Applications/Xcode.app',CACHE,work])+' (literal "/") (literal "/dev/null") (literal "/dev/urandom") (literal "/Library/Preferences/com.apple.dt.Xcode.plist"))',
        '(allow file-write* '+sub(work)+' (literal "/dev/null"))','(allow process-exec)','(allow process-fork)',
        '(allow sysctl-read)','(allow process-info* (target self))','(allow signal (target self))',
        '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo") (global-name "com.apple.system.notification_center"))'])+'\n'

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--cache-only',action='store_true');a=p.parse_args(argv)
    if not a.cache_only and not a.output:p.error('--output is required for a build')
    roots=cache_inputs()
    # CMake.app contains internal links; register its parent without traversing them.
    aar=str(Path.home() / 'Documents/Codex/monitor/bin/aar');command=[sys.executable,'-B',str(Path(__file__).resolve()),'--cache-only']
    for directory in [CACHE/'archives',*(CACHE/name for name in roots)]:
        args=[aar,'register','--path',str(directory),'--project',str(ROOT),'--type','CACHE','--regenerable','--source','Official checksum-pinned shader host tools; compiler/graphics-toolchain.lock.json','--argv-json',json.dumps(command),'--json']
        if not any(f.is_symlink() for f in directory.rglob('*')):args.append('--include-files')
        done=subprocess.run(args,capture_output=True,text=True,timeout=180)
        if done.returncode:raise RuntimeError('Central AAR registration failed: '+(done.stderr or done.stdout))
    if a.cache_only:print('SHADER_TOOL_SOURCES_VERIFIED');return 0
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);work=out/'work';work.mkdir();(work/'tmp').mkdir()
    sb=out/'build.sb';sb.write_text(policy(work));env={'PYTHONDONTWRITEBYTECODE':'1','DEVELOPER_DIR':'/Applications/Xcode.app/Contents/Developer'}
    sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip();env['SDKROOT']=sdk
    cmake=roots['cmake']/'CMake.app/Contents/bin/cmake';result={'status':'BLOCKED','scope':'host shader tools only; no target shader or game acceptance','sourcesSHA256':{str(f.relative_to(ROOT)):sha256(f) for f in [Path(__file__),LOCK]},'steps':[]}
    def run(args,name,timeout=600,expected=0):
        r=execute(['/usr/bin/sandbox-exec','-f',str(sb),*map(str,args)],out/name,work,timeout=timeout,cpu_seconds=600,file_size_bytes=2*1024**3,extra_env=env);result['steps'].append(r)
        if (r['exitCode']==0)!=(expected==0) or r['timedOut']:raise RuntimeError(name+' failed; see retained logs')
    try:
        controls=out/'controls';controls.mkdir();(controls/'input').write_text('first-party denied-read control')
        run(['/bin/cat',controls/'input'],'deny-read',10,1);run(['/usr/bin/touch',controls/'output'],'deny-write',10,1)
        if (controls/'output').exists():raise RuntimeError('Sandbox write control escaped')
        common=['-DCMAKE_BUILD_TYPE=Release','-DCMAKE_OSX_ARCHITECTURES=arm64','-DCMAKE_OSX_SYSROOT='+sdk,'-DCMAKE_MAKE_PROGRAM=/Applications/Xcode.app/Contents/Developer/usr/bin/make',
            '-DCMAKE_AR=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ar',
            '-DCMAKE_RANLIB=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ranlib',
            '-DCMAKE_C_COMPILER=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang',
            '-DCMAKE_CXX_COMPILER=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++']
        targets=[('glslang',['-DBUILD_EXTERNAL=OFF','-DENABLE_OPT=OFF','-DENABLE_HLSL=OFF','-DGLSLANG_TESTS=OFF','-DENABLE_PCH=OFF','-DGLSLANG_ENABLE_INSTALL=OFF']),
            ('spirv-cross',['-DSPIRV_CROSS_ENABLE_TESTS=OFF','-DSPIRV_CROSS_ENABLE_C_API=OFF','-DSPIRV_CROSS_SKIP_INSTALL=ON'])]
        for name,options in targets:
            build=work/('build-'+name)
            run([cmake,'-S',roots[name],'-B',build,*common,*options],name+'-configure')
            run([cmake,'--build',build,'--parallel','4'],name+'-build')
        binaries={'glslang':work/'build-glslang/StandAlone/glslang','spirv-cross':work/'build-spirv-cross/spirv-cross'}
        if not all(f.is_file() for f in binaries.values()):raise RuntimeError('Expected shader tool executable missing')
        (out/'bin').mkdir()
        for name,path in list(binaries.items()):
            target=out/'bin'/name;shutil.copy2(path,target);binaries[name]=target
        result.update(status='SHADER_HOST_TOOLS_BUILT',binaries={name:{'path':str(f),'sha256':sha256(f)} for name,f in binaries.items()},sandboxReadWriteControls='PASS',networkPolicy='deny default')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:result['error']=str(exc)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    regeneration=[sys.executable,'-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)]
    linked=any(f.is_symlink() for f in out.rglob('*'))
    register_tree(out,regeneration,recursive=not linked)
    if linked:
        for item in out.iterdir():
            if item.name!='work':register_tree(item,regeneration)
    print(json.dumps({k:v for k,v in result.items() if k not in ['steps','sourcesSHA256']},indent=2));return 0 if result['status']=='SHADER_HOST_TOOLS_BUILT' else 2

if __name__=='__main__':raise SystemExit(main())
