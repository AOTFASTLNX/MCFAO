#!/usr/bin/env python3
"""Build pinned OpenAL Soft for iOS under a default-deny policy; require real CoreAudio."""
from __future__ import annotations
from storage_config import cache_path
import argparse
import json
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
from bootstrap_toolchain import sha256
from build_c0_harness import validate_dylib
from capture import ROOT
from graphics_common import register_tree
from host_tools import developer_dir, xcode_tool
from prepare_shader_toolchain import extract,policy
from run_b0_reference import execute

CACHE=cache_path('graphics/openal-soft')
LOCK=ROOT/'compiler/openal.lock.json'

def stage_inputs(scratch, archive, cmake_archive, spec, cmake_lock):
    source_root = scratch / 'source'
    extract(archive, source_root)
    source = source_root / ('openal-soft-' + spec['commit'])
    cmake_root = scratch / 'cmake'
    extract(cmake_archive, cmake_root)
    bundle = 'cmake-' + cmake_lock['version'] + '-macos-universal/CMake.app'
    cmake = cmake_root / bundle / 'Contents/bin/cmake'
    if not cmake.is_file():
        raise ValueError('Pinned CMake executable unavailable')
    return source, cmake


def build(source, cmake, work, out, sdk_name, result):
    work.mkdir()
    sb = out / 'build.sb'
    sb.write_text(policy(work, inputs=(source, cmake.parents[2])))
    sdk = subprocess.check_output(['xcrun', '--sdk', sdk_name, '--show-sdk-path'], text=True).strip()
    env = {'SDKROOT': sdk, 'DEVELOPER_DIR': str(developer_dir()), 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(work)}
    result['cmakeSHA256'] = sha256(cmake)
    def run(args,name,timeout=300,expected=0):
        r=execute(['/usr/bin/sandbox-exec','-f',str(sb),*map(str,args)],out/name,work,timeout=timeout,cpu_seconds=1800,file_size_bytes=512*1024**2,extra_env=env);result['steps'].append(r)
        if (r['exitCode']==0)!=(expected==0) or r['timedOut']:raise RuntimeError(name+' failed; see retained logs')
    controls=out/'controls';controls.mkdir();(controls/'input').write_text('denied outside read')
    run(['/bin/cat',controls/'input'],'deny-read',10,1);run(['/usr/bin/touch',controls/'output'],'deny-write',10,1)
    if (controls/'output').exists():raise RuntimeError('Sandbox write control escaped')
    build=work/'build'
    compatibility=work/'sdk-compat.cmake'
    compatibility.write_text('cmake_language(DEFER CALL set_property SOURCE '+json.dumps(str(source/'alc/backends/coreaudio.cpp'))+' APPEND PROPERTY COMPILE_OPTIONS "-Wno-error=function-effects")\n')
    options=['-G','Unix Makefiles','-DCMAKE_SYSTEM_NAME=iOS','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_OSX_ARCHITECTURES=arm64',
        '-DCMAKE_OSX_SYSROOT='+sdk,'-DCMAKE_OSX_DEPLOYMENT_TARGET=17.0',
        '-DCMAKE_C_COMPILER='+xcode_tool('clang',sdk_name),'-DCMAKE_CXX_COMPILER='+xcode_tool('clang++',sdk_name),
        '-DCMAKE_AR='+xcode_tool('ar',sdk_name),'-DCMAKE_RANLIB='+xcode_tool('ranlib',sdk_name),
        # Append only to CoreAudio after upstream target flags, retaining the diagnostic.
        '-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES='+str(compatibility),
        '-DCMAKE_MAKE_PROGRAM='+xcode_tool('make'),
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
    validate_dylib(binary,sdk_name=='iphonesimulator')
    dependencies=subprocess.check_output(['xcrun','otool','-L',str(binary)],text=True)
    if '/Users/' in '\n'.join(dependencies.splitlines()[1:]):raise ValueError('Host dependency leaked into iOS OpenAL')
    (out/'dependencies.txt').write_text(dependencies)
    notices=out/'licenses';notices.mkdir();shutil.copy2(source/'COPYING',notices/'OpenAL-Soft-COPYING')
    shutil.copy2(source/'fmt-11.2.0/LICENSE',notices/'fmt-LICENSE')
    result.update(status='OPENAL_SOFT_BUILT',binarySHA256=sha256(binary),sandboxReadWriteControls='PASS',networkPolicy='deny default')


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
    cmake_lock = json.loads((ROOT / 'compiler/graphics-toolchain.lock.json').read_text())['cmake']
    cmake_archive = cache_path('graphics/shader-toolchain/archives') / cmake_lock['file']
    if not cmake_archive.is_file() or sha256(cmake_archive) != cmake_lock['sha256']:
        raise ValueError('Pinned CMake archive missing or modified: ' + str(cmake_archive))
    command = [sys.executable, '-B', str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)]
    register_tree(CACHE, command, kind='CACHE')
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {
        'status': 'BLOCKED',
        'sdk': a.sdk,
        'target': 'arm64-apple-ios17.0' + ('-simulator' if a.sdk == 'iphonesimulator' else ''),
        'scope': 'source-built CoreAudio OpenAL; runtime audio and device acceptance are separate',
        'sourcesSHA256': {str(f.relative_to(ROOT)): sha256(f) for f in [Path(__file__), LOCK]},
        'sourceArchiveSHA256': spec['sha256'],
        'steps': [],
    }
    try:
        # TMPDIR can point at an external job volume. CMake recursively loads
        # its own compiler modules, so stage the verified archives on the Mac
        # system volume where the build won't pick up AppleDouble sidecars.
        with TemporaryDirectory(prefix='ncl-openal-', dir='/private/tmp') as temporary:
            scratch = Path(temporary)
            source, cmake = stage_inputs(scratch, archive, cmake_archive, spec, cmake_lock)
            build(source, cmake, scratch / 'work', out, a.sdk, result)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result['error'] = str(error)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    linked=any(f.is_symlink() for f in out.rglob('*'));register_tree(out,command,recursive=not linked)
    if linked:
        for item in out.iterdir():
            if item.name!='work':register_tree(item,command)
    print(json.dumps({k:v for k,v in result.items() if k not in ['steps','sourcesSHA256']},indent=2));return 0 if result['status']=='OPENAL_SOFT_BUILT' else 2

if __name__=='__main__':raise SystemExit(main())
