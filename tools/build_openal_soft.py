#!/usr/bin/env python3
"""Build pinned OpenAL Soft for iOS under a default-deny policy; require real CoreAudio."""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from bootstrap_toolchain import sha256
from build_c0_harness import validate_dylib
from capture import ROOT
from graphics_common import register_tree
from prepare_shader_toolchain import extract,policy
from run_b0_reference import execute

CACHE=ROOT/'.cache/graphics/openal-soft'
LOCK=ROOT/'compiler/openal.lock.json'

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sdk',choices=('iphoneos','iphonesimulator'),default='iphonesimulator');a=p.parse_args(argv)
    spec=json.loads(LOCK.read_text());archive=CACHE/spec['file'];CACHE.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        partial=archive.with_suffix('.part')
        if partial.exists():raise ValueError('Interrupted download preserved')
        subprocess.run(['/usr/bin/curl','-fsSL','--proto','=https','--max-time','120','--max-filesize',str(spec['size']),spec['url'],'-o',str(partial)],check=True)
        if sha256(partial)!=spec['sha256']:raise ValueError('OpenAL download checksum mismatch')
        partial.rename(archive)
    if archive.stat().st_size!=spec['size'] or sha256(archive)!=spec['sha256']:raise ValueError('OpenAL archive modified')
    extract(archive,CACHE/'source');source=CACHE/'source'/('openal-soft-'+spec['commit'])
    host=ROOT/'artifacts/graphics/shader-toolchain-03';report=json.loads((host/'result.json').read_text())
    cmake=ROOT/'.cache/graphics/shader-toolchain/cmake/cmake-3.31.12-macos-universal/CMake.app/Contents/bin/cmake'
    # This executable's archive is pinned by the existing host-tool lock.
    cmake_lock=json.loads((ROOT/'compiler/graphics-toolchain.lock.json').read_text())['cmake']
    cmake_archive=ROOT/'.cache/graphics/shader-toolchain/archives'/cmake_lock['file']
    if sha256(cmake_archive)!=cmake_lock['sha256'] or report['status']!='SHADER_HOST_TOOLS_BUILT':raise ValueError('Verified CMake toolchain required')
    extract(cmake_archive,ROOT/'.cache/graphics/shader-toolchain/cmake')
    if not cmake.is_file():raise ValueError('Pinned CMake executable unavailable')
    command=[sys.executable,'-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)]
    register_tree(CACHE,command,kind='CACHE')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);work=out/'work';work.mkdir()
    sb=out/'build.sb';sb.write_text(policy(work)+'(allow file-read* (subpath '+json.dumps(str(CACHE))+'))\n')
    sdk=subprocess.check_output(['xcrun','--sdk',a.sdk,'--show-sdk-path'],text=True).strip()
    env={'SDKROOT':sdk,'DEVELOPER_DIR':'/Applications/Xcode.app/Contents/Developer','PYTHONDONTWRITEBYTECODE':'1'}
    result={'status':'BLOCKED','sdk':a.sdk,'target':'arm64-apple-ios17.0'+('-simulator' if a.sdk=='iphonesimulator' else ''),
            'scope':'source-built CoreAudio OpenAL; runtime audio and device acceptance are separate',
            'sourcesSHA256':{str(f.relative_to(ROOT)):sha256(f) for f in [Path(__file__),LOCK]},
            'sourceArchiveSHA256':spec['sha256'],'cmakeSHA256':sha256(cmake),'steps':[]}
    def run(args,name,timeout=300,expected=0):
        r=execute(['/usr/bin/sandbox-exec','-f',str(sb),*map(str,args)],out/name,work,timeout=timeout,cpu_seconds=1800,file_size_bytes=512*1024**2,extra_env=env);result['steps'].append(r)
        if (r['exitCode']==0)!=(expected==0) or r['timedOut']:raise RuntimeError(name+' failed; see retained logs')
    try:
        controls=out/'controls';controls.mkdir();(controls/'input').write_text('denied outside read')
        run(['/bin/cat',controls/'input'],'deny-read',10,1);run(['/usr/bin/touch',controls/'output'],'deny-write',10,1)
        if (controls/'output').exists():raise RuntimeError('Sandbox write control escaped')
        toolchain=Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin')
        build=work/'build'
        compatibility=work/'sdk-compat.cmake'
        compatibility.write_text('cmake_language(DEFER CALL set_property SOURCE '+json.dumps(str(source/'alc/backends/coreaudio.cpp'))+' APPEND PROPERTY COMPILE_OPTIONS "-Wno-error=function-effects")\n')
        options=['-G','Unix Makefiles','-DCMAKE_SYSTEM_NAME=iOS','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_OSX_ARCHITECTURES=arm64',
            '-DCMAKE_OSX_SYSROOT='+sdk,'-DCMAKE_OSX_DEPLOYMENT_TARGET=17.0',
            '-DCMAKE_C_COMPILER='+str(toolchain/'clang'),'-DCMAKE_CXX_COMPILER='+str(toolchain/'clang++'),
            '-DCMAKE_AR='+str(toolchain/'ar'),'-DCMAKE_RANLIB='+str(toolchain/'ranlib'),
            # Append only to CoreAudio after upstream target flags, retaining the diagnostic.
            '-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES='+str(compatibility),
            '-DCMAKE_MAKE_PROGRAM=/Applications/Xcode.app/Contents/Developer/usr/bin/make',
            '-DLIBTYPE=SHARED','-DALSOFT_REQUIRE_COREAUDIO=ON','-DALSOFT_BACKEND_COREAUDIO=ON',
            '-DALSOFT_UTILS=OFF','-DALSOFT_EXAMPLES=OFF','-DALSOFT_TESTS=OFF','-DALSOFT_INSTALL=OFF',
            '-DALSOFT_UPDATE_BUILD_VERSION=OFF','-DALSOFT_ENABLE_MODULES=OFF','-DALSOFT_EMBED_HRTF_DATA=ON']
        options += ['-DALSOFT_BACKEND_'+name+'=OFF' for name in ('PIPEWIRE','PULSEAUDIO','ALSA','OSS','SOLARIS','SNDIO','JACK','OBOE','OPENSL','PORTAUDIO','SDL2','SDL3','WAVE')]
        run([cmake,'-S',source,'-B',build,*options],'configure')
        run([cmake,'--build',build,'--target','OpenAL','--parallel','4'],'build',900)
        candidates=[f for f in build.glob('libopenal*.dylib') if f.is_file() and not f.is_symlink()]
        if len(candidates)!=1:raise ValueError('Expected one actual OpenAL dynamic library')
        binary=out/'libopenal.dylib';shutil.copy2(candidates[0],binary)
        subprocess.run(['xcrun','install_name_tool','-id','@rpath/libopenal.dylib',str(binary)],check=True)
        validate_dylib(binary,a.sdk=='iphonesimulator')
        dependencies=subprocess.check_output(['xcrun','otool','-L',str(binary)],text=True)
        if '/Users/' in '\n'.join(dependencies.splitlines()[1:]):raise ValueError('Host dependency leaked into iOS OpenAL')
        (out/'dependencies.txt').write_text(dependencies)
        notices=out/'licenses';notices.mkdir();shutil.copy2(source/'COPYING',notices/'OpenAL-Soft-COPYING')
        shutil.copy2(source/'fmt-11.2.0/LICENSE',notices/'fmt-LICENSE')
        result.update(status='OPENAL_SOFT_BUILT',binarySHA256=sha256(binary),sandboxReadWriteControls='PASS',networkPolicy='deny default')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:result['error']=str(error)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    linked=any(f.is_symlink() for f in out.rglob('*'));register_tree(out,command,recursive=not linked)
    if linked:
        for item in out.iterdir():
            if item.name!='work':register_tree(item,command)
    print(json.dumps({k:v for k,v in result.items() if k not in ['steps','sourcesSHA256']},indent=2));return 0 if result['status']=='OPENAL_SOFT_BUILT' else 2

if __name__=='__main__':raise SystemExit(main())
