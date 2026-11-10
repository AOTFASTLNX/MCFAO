#!/usr/bin/env python3
"""Build explicit iOS LWJGL overlays and a JNI library with precompiled callback functions."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from bootstrap_toolchain import sha256
from build_method_splitter import gradle_asm
from capture import ROOT,capture
from graphics_common import register_tree
from lwjgl_codegen import generate_callbacks,generate_jni,parse_natives,CALLBACKS
from run_b0_reference import sandbox_policy
from fetch_stb import verify_sources

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--sdk",choices=("iphoneos","iphonesimulator"),default="iphonesimulator")
    p.add_argument("--test-host",action="store_true")
    p.add_argument("--glfw-library",type=Path,default=ROOT/"artifacts/graphics/glfw-sim-01/libglfw.dylib")
    args=p.parse_args(argv)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    home=ROOT/".cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home"
    manifest=json.loads((ROOT/"artifacts/b0/prepared-04/result.json").read_text())
    libraries={}
    for entry in manifest["referenceLibraries"]:
        path=Path(entry["path"])
        if path.name in ("lwjgl-3.4.1.jar","lwjgl-glfw-3.4.1.jar","lwjgl-stb-3.4.1.jar","lwjgl-openal-3.4.1.jar"):
            if sha256(path)!=entry["sha256"]:p.error("Reference LWJGL input changed: "+str(path))
            libraries[path.stem.split('-3.4')[0]]=path
    if set(libraries)!={"lwjgl","lwjgl-glfw","lwjgl-stb","lwjgl-openal"}:p.error("Hash-verified LWJGL 3.4.1 core/GLFW/STB/OpenAL inputs required")
    sources=sorted((ROOT/"compiler/lwjgl-lite/src").rglob("*.java"))
    steps=[]
    def step(command,name,cwd=ROOT):
        r=capture(list(map(str,command)),out/name,180,cwd=cwd);steps.append(r)
        if r["exitCode"]:raise RuntimeError(name+" failed: "+(out/name/"stderr.log").read_text()[-2500:])
        return r
    result={"status":"BLOCKED","gateC0":"BLOCKED","inputsSHA256":{str(v):sha256(v) for v in libraries.values()},
            "sourcesSHA256":{str(v.relative_to(ROOT)):sha256(v) for v in [*sources,ROOT/"compiler/lwjgl-lite/Overlay.java",ROOT/"ios/lwjgl-lite/core.c",ROOT/"ios/lwjgl-lite/stb_images.c",ROOT/"compiler/stb.lock.json",ROOT/'interop/graphics/LwjglProbe.java',Path(__file__),ROOT/"tools/lwjgl_codegen.py"]},
            "callbackABIs":[name for name,_ in CALLBACKS],"slotsPerABI":32,
            "scope":"JNI/GLFW and bounded memory image STB bridge; no game renderer, Minecraft boot or device acceptance"}
    try:
        stb=verify_sources();result["stbSourcesSHA256"]={f.name:sha256(f) for f in sorted(stb.glob('*.h'))}
        classes=out/"overlay-classes";classes.mkdir()
        cp=os.pathsep.join(map(str,libraries.values()))
        step([home/"bin/javac","--release","17","-proc:none","-cp",cp,"-d",classes,*sources],"javac")
        asm=gradle_asm().get("asm-9.9.jar")
        if not asm:raise RuntimeError("Pinned ASM 9.9 jar missing")
        transformer=out/"transformer";transformer.mkdir()
        step([home/"bin/javac","-proc:none","-cp",asm,"-d",transformer,ROOT/"compiler/lwjgl-lite/Overlay.java"],"transformer-compile")
        overlay_libraries=[]
        exports=subprocess.check_output(["xcrun","nm","-gUj",str(args.glfw_library.resolve(strict=True))],text=True)
        symbol_file=out/"glfw-symbols.txt"
        symbol_file.write_text('\n'.join(sorted(x.strip().removeprefix('_') for x in exports.splitlines()))+'\n')
        result["glfwLibrarySHA256"]=sha256(args.glfw_library)
        result["asmSHA256"]=sha256(asm)
        empty=out/"empty";empty.mkdir()
        for module,library in libraries.items():
            jar=out/(module+"-ios.jar")
            # Only the core overlay carries replacement classes. It appears first on the classpath,
            # including our safe glfw.Callbacks helper; the original module contains no duplicate patch.
            step([home/"bin/java","-cp",os.pathsep.join(map(str,[transformer,asm])),"fabricaot.graphics.Overlay",library,jar,classes if module=="lwjgl" else empty,symbol_file],module+"-overlay")
            overlay_libraries.append(jar)
        overlay_libraries.sort(key=lambda path: path.name!="lwjgl-ios.jar")
        native_text=subprocess.check_output([str(home/"bin/javap"),"-p","-s","-cp",str(libraries["lwjgl"]),"org.lwjgl.system.JNI"],text=True)
        methods=parse_natives(native_text)
        (out/"jni.c").write_text(generate_jni(methods));(out/"callbacks.c").write_text(generate_callbacks())
        result["generatedJNIAdapters"]=len(methods)
        jni_include=["-I",str(home/"include"),"-I",str(home/"include/darwin"),"-I",str(stb)]
        native=[ROOT/"ios/lwjgl-lite/core.c",ROOT/"ios/lwjgl-lite/stb_images.c",out/"jni.c",out/"callbacks.c"]
        target="arm64-apple-ios17.0"+("-simulator" if args.sdk=="iphonesimulator" else "")
        result["target"]=target
        binary=out/"liblwjgl.dylib"
        step(["xcrun","--sdk",args.sdk,"clang","-target",target,"-std=c11","-O2","-Wall","-Wextra","-Werror",*jni_include,"-dynamiclib",*native,"-install_name","@rpath/liblwjgl.dylib","-o",binary],"native-compile")
        result["binarySHA256"]=sha256(binary)
        result["overlaysSHA256"]={str(v):sha256(v) for v in overlay_libraries}
        result["status"]="STATIC_JNI_BRIDGE_BUILT"
        if args.test_host:
            host=out/"host";host.mkdir()
            step(["xcrun","clang","-std=c11","-O1","-g","-Wall","-Wextra","-Werror",*jni_include,"-dynamiclib",*native,"-o",host/"liblwjgl.dylib"],"host-native-compile")
            step(["xcrun","clang","-std=c11","-dynamiclib","-I",ROOT/"ios/glfw-lite",ROOT/"ios/glfw-lite/glfw_lite.c",ROOT/"interop/graphics/glfw_state_test.c","-o",host/"libglfw.dylib"],"host-window-compile")
            test_classes=out/"test-classes";test_classes.mkdir()
            cp=os.pathsep.join(map(str,overlay_libraries))
            step([home/"bin/javac","-proc:none","-cp",cp,"-d",test_classes,ROOT/"interop/graphics/LwjglProbe.java"],"host-probe-compile")
            # Only audited LWJGL core + first-party probe. No Minecraft or Mod initialization here.
            step([home/"bin/java","--enable-native-access=ALL-UNNAMED","-Xmx256m","-Dorg.lwjgl.system.allocator=system",
                  "-Dorg.lwjgl.librarypath="+str(host),"-cp",str(test_classes)+os.pathsep+cp,"fabricaot.graphics.LwjglProbe"],"host-probe")
            if "LWJGL_STATIC_BRIDGE_PASS" not in (out/"host-probe/stdout.log").read_text():raise RuntimeError("missing host probe success marker")
            result["hostBridgeFixture"]="PASS"
            references=[]
            for entry in manifest["referenceLibraries"]:
                path=Path(entry["path"])
                if path in libraries.values() or any(s in path.name for s in ("fabric-loader-","sponge-mixin-","intermediary-")):continue
                if sha256(path)!=entry["sha256"]:raise RuntimeError("Window reference dependency changed: "+str(path))
                references.append(path)
            cp=os.pathsep.join(map(str,[test_classes,*overlay_libraries,*references]))
            step([home/"bin/javac","-proc:none","-cp",cp,"-d",test_classes,ROOT/"interop/graphics/WindowProbe.java"],"window-probe-compile")
            policy=out/"window-probe.sb"
            policy.write_text(sandbox_policy(out,home,references))
            step(["/usr/bin/sandbox-exec","-f",policy,home/"bin/java","--enable-native-access=ALL-UNNAMED","-Xmx512m",
                  "-Duser.home="+str(out),"-Dorg.lwjgl.system.allocator=system","-Dorg.lwjgl.librarypath="+str(host),
                  "-cp",cp,"fabricaot.graphics.WindowProbe"],"window-probe",cwd=out)
            if "MINECRAFT_WINDOW_PROBE_PASS" not in (out/"window-probe/stdout.log").read_text():raise RuntimeError("Window probe marker missing")
            result["hostMinecraftWindowFixture"]="PASS"
            step([home/"bin/javac","-proc:none","-cp",cp,"-d",test_classes,ROOT/"interop/graphics/NativeImageProbe.java"],"image-probe-compile")
            # The real client NativeImage path runs under the same default-deny policy.
            step(["/usr/bin/sandbox-exec","-f",policy,home/"bin/java","--enable-native-access=ALL-UNNAMED","-Xmx512m",
                  "-Duser.dir="+str(out),"-Duser.home="+str(out),"-Dorg.lwjgl.system.allocator=system","-Dorg.lwjgl.librarypath="+str(host),
                  "-cp",cp,"fabricaot.graphics.NativeImageProbe"],"image-probe",cwd=out)
            if "MINECRAFT_NATIVE_IMAGE_PASS" not in (out/"image-probe/stdout.log").read_text():raise RuntimeError("NativeImage probe marker missing")
            result["hostMinecraftImageFixture"]="PASS"
    except (OSError,RuntimeError,ValueError,subprocess.SubprocessError) as exc:
        result["status"]="BLOCKED";result["error"]=str(exc)
    result["steps"]=steps
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    command=[sys.executable,"-B",str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)]
    try:register_tree(out,command)
    except (OSError,RuntimeError) as exc:print(str(exc),file=sys.stderr);return 1
    print(json.dumps({k:v for k,v in result.items() if k not in ("steps","sourcesSHA256")},indent=2))
    return 0 if result["status"]=="STATIC_JNI_BRIDGE_BUILT" else 2

if __name__=="__main__":raise SystemExit(main())
