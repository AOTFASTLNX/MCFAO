#!/usr/bin/env python3
"""Translate actual vanilla shader pairs to precompiled Metal, preserving binding evidence."""
from __future__ import annotations
import argparse
import json
import math
import re
import shutil
import sys
from pathlib import Path
from bootstrap_toolchain import sha256
from capture import ROOT,capture
from graphics_common import register_tree

Y_UP_TEXTURE_WRITERS = frozenset((
    'minecraft:core/animate_sprite',
    'minecraft:core/screenquad',
    'minecraft:post/rotscale',
))

def interface_locations(vertex: dict,fragment: dict)->dict[str,int]:
    outputs={r['name']:r for r in vertex['resources'] if r['kind']=='output'}
    inputs={r['name']:r for r in fragment['resources'] if r['kind']=='input'}
    shape=lambda r:tuple(r.get(k) for k in ['baseType','width','components','columns','array'])
    for name,value in inputs.items():
        if name not in outputs or shape(value)!=shape(outputs[name]):raise ValueError('Shader varying mismatch: '+name)
    result={};offset=0
    for name,value in sorted(outputs.items()):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('Unsupported structured varying: '+name)
        count=value.get('columns',1)*math.prod(value.get('array',[]))
        if count<1 or offset+count>31:raise ValueError('Shader varying location limit exceeded')
        result[name]=offset;offset+=count
    return result

def validate_bindings(pipeline: dict,vertex: dict,fragment: dict):
    uniforms={u['name']:u['type'] for u in pipeline['uniforms']};samplers=set(pipeline['samplers']);attributes={a['name'] for a in pipeline['attributes']}
    # GlProgram.setupUniforms also discovers these RenderSystem.bindDefaultUniforms blocks.
    for name in ['Projection','Lighting','Fog','Globals']:uniforms.setdefault(name,'UNIFORM_BUFFER')
    for stage,data in [('vertex',vertex),('fragment',fragment)]:
        for resource in data['resources']:
            name=resource['name'];kind=resource['kind']
            if kind=='input' and stage=='vertex' and name not in attributes:raise ValueError('Undeclared vertex attribute: '+name)
            if kind=='uniform' and uniforms.get(name)!='UNIFORM_BUFFER':raise ValueError('Undeclared or mismatched UBO: '+name)
            if kind=='texture':
                if resource['bufferTexture']:
                    if uniforms.get(name)!='TEXEL_BUFFER':raise ValueError('Undeclared or mismatched texel buffer: '+name)
                elif name not in samplers:raise ValueError('Undeclared sampler: '+name)
            if kind in ['storage','sampler','image']:raise ValueError('Unsupported shader resource: '+kind+' '+name)
            if kind=='uniform' and resource['metalIndex']>=30:raise ValueError('Uniform collides with reserved vertex buffer slot')
            if kind=='texture' and (resource['metalIndex']>=16 or resource['metalSamplerIndex'] not in range(16) and resource['metalSamplerIndex']!=4294967295):raise ValueError('Metal texture/sampler slot budget exceeded')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sdk',choices=['iphonesimulator','iphoneos'],default='iphonesimulator');a=p.parse_args(argv)
    catalog_root=a.catalog.resolve();tool_root=a.toolchain.resolve();report=json.loads((tool_root/'result.json').read_text())
    if report['status']!='SHADER_HOST_TOOLS_BUILT':p.error('Verified host tools required')
    tools={}
    for name,entry in report['binaries'].items():
        path=Path(entry['path'])
        if sha256(path)!=entry['sha256']:p.error('Modified shader tool: '+name)
        tools[name]=path
    metadata=json.loads((catalog_root/'result.json').read_text());catalog_file=catalog_root/'catalog/catalog.json'
    if metadata['status']!='VANILLA_SHADER_CATALOG_COLLECTED' or sha256(catalog_file)!=metadata['catalogSHA256']:p.error('Verified shader catalog required')
    catalog=json.loads(catalog_file.read_text());out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);work=out/'work';work.mkdir();bundle=out/'bundle';bundle.mkdir()
    result={'status':'BLOCKED','scope':'build-time vanilla shader translation only; target draw semantics unverified','sourcesSHA256':{str(f.relative_to(ROOT)):sha256(f) for f in [Path(__file__),ROOT/'compiler/shaders/native/msl_translate.cpp']},'catalogSHA256':sha256(catalog_file),'sdk':a.sdk,'programs':[],'failures':[]}
    def run(command,folder,cwd=work):
        r=capture(list(map(str,command)),folder,90,cwd=cwd)
        if r['exitCode'] or r['timedOut']:raise RuntimeError(str(folder.relative_to(out))+': '+(folder/'stdout.log').read_text()[-1400:]+(folder/'stderr.log').read_text()[-1400:])
    try:
        source=ROOT/'.cache/graphics/shader-toolchain/spirv-cross/SPIRV-Cross-f11ba9f0b21ba8fc15153d50a2a1ae31ab1cf8f7';library=tool_root/'work/build-spirv-cross';adapter=work/'msl-translate'
        run(['xcrun','clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',source,ROOT/'compiler/shaders/native/msl_translate.cpp',library/'libspirv-cross-msl.a',library/'libspirv-cross-glsl.a',library/'libspirv-cross-core.a','-o',adapter],out/'adapter-compile')
        for program in catalog['programs']:
            key=program['key']
            if not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('Invalid shader program key')
            folder=work/key;folder.mkdir();entry={**program,'status':'UNSUPPORTED'}
            try:
                original=catalog_root/'catalog/variants'/key
                for stage,suffix in [('vertex','vert'),('fragment','frag')]:
                    path=original/('shader.'+suffix)
                    if sha256(path)!=program[stage+'SHA256']:raise ValueError('Modified preprocessed shader: '+str(path))
                    shutil.copy2(path,folder/path.name)
                run([tools['glslang'],'-G','--auto-map-bindings','--auto-map-locations','-l','shader.vert','shader.frag'],folder/'glslang',cwd=folder)
                stages={}
                for stage,prefix in [('vertex','vert'),('fragment','frag')]:
                    run([adapter,folder/(prefix+'.spv'),stage,folder/(prefix+'-initial.metal'),folder/(prefix+'-initial.json')],folder/(prefix+'-reflect'))
                    stages[stage]=json.loads((folder/(prefix+'-initial.json')).read_text())
                mapping=interface_locations(stages['vertex'],stages['fragment']);location_file=folder/'interface-locations.txt';location_file.write_text(''.join(f'{name} {location}\n' for name,location in mapping.items()))
                for stage,prefix in [('vertex','vert'),('fragment','frag')]:
                    origin=['--texture-y-down'] if stage=='vertex' and program['vertex'] in Y_UP_TEXTURE_WRITERS else []
                    run([adapter,folder/(prefix+'.spv'),stage,folder/(prefix+'.metal'),folder/(prefix+'-bindings.json'),location_file,*origin],folder/(prefix+'-translate'))
                    stages[stage]=json.loads((folder/(prefix+'-bindings.json')).read_text())
                    target='air64-apple-ios17.0'+('-simulator' if a.sdk=='iphonesimulator' else '')
                    run(['xcrun','--sdk',a.sdk,'metal','-c','-std=ios-metal2.4','-fno-fast-math','-target',target,'-fmodules-cache-path='+str(work/'metal-modules'),folder/(prefix+'.metal'),'-o',folder/(prefix+'.air')],folder/(prefix+'-metal'))
                for pipeline in catalog['pipelines']:
                    if pipeline['program']==key:validate_bindings(pipeline,stages['vertex'],stages['fragment'])
                run(['xcrun','--sdk',a.sdk,'metallib',folder/'vert.air',folder/'frag.air','-o',bundle/(key+'.metallib')],folder/'metallib')
                entry.update(status='TRANSLATED',stages=stages,interfaceLocations=mapping,metallibSHA256=sha256(bundle/(key+'.metallib')))
            except (OSError,ValueError,RuntimeError) as error:entry['error']=str(error);result['failures'].append({'key':key,'error':str(error)})
            result['programs'].append(entry);print(key[:10],entry['status'],flush=True)
        covered={('assets/'+p[stage].split(':')[0]+'/shaders/'+p[stage].split(':')[1]+suffix) for p in catalog['programs'] for stage,suffix in [('vertex','.vsh'),('fragment','.fsh')]}
        missing=[name for name in catalog['rawSources'] if name.endswith(('.vsh','.fsh')) and name not in covered]
        result['uncoveredExecutableSources']=missing
        if not result['failures'] and not missing:
            index={'schema':1,'clientSHA256':metadata['clientSHA256'],'programs':result['programs'],'pipelines':catalog['pipelines'],'postPasses':catalog.get('postPasses',[])}
            (bundle/'index.json').write_text(json.dumps(index,indent=2)+'\n');result.update(status='VANILLA_SHADERS_PRECOMPILED',indexSHA256=sha256(bundle/'index.json'))
    except (OSError,ValueError,RuntimeError) as error:result['failures'].append({'error':str(error)})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');register_tree(out,[sys.executable,'-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    print(json.dumps({'status':result['status'],'programs':len(result['programs']),'failures':result['failures'],'uncovered':result.get('uncoveredExecutableSources')},indent=2));return 0 if result['status']=='VANILLA_SHADERS_PRECOMPILED' else 2

if __name__=='__main__':raise SystemExit(main())
