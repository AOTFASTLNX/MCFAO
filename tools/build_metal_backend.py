#!/usr/bin/env python3
"""Compile the experimental blaze3d Metal backend, draw paths and JNI bridge."""
from __future__ import annotations
import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from bootstrap_toolchain import sha256
from capture import ROOT,capture
from build_c0_harness import validate_dylib
from graphics_common import bridge_overlays,register_tree
from run_b0_reference import sandbox_policy

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--graphics-bridge",type=Path,required=True)
    p.add_argument("--glfw-library",type=Path,required=True)
    p.add_argument("--sdk",choices=("iphoneos","iphonesimulator"),default="iphonesimulator")
    p.add_argument("--test-host",action="store_true",help="Run first-party texture bounds contracts under a default-deny policy")
    args=p.parse_args(argv)
    overlays=bridge_overlays(args.graphics_bridge)
    glfw=args.glfw_library.resolve(strict=True);validate_dylib(glfw,args.sdk=="iphonesimulator")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    home=ROOT/".cache/toolchains/graalvm-25.0.2/graalvm-community-openjdk-25.0.2+10.1/Contents/Home"
    manifest=json.loads((ROOT/"artifacts/b0/prepared-04/result.json").read_text())
    cp=[*overlays]
    for entry in manifest["referenceLibraries"]:
        f=Path(entry["path"])
        if f.name in {p.name.replace("-ios.jar","-3.4.1.jar") for p in overlays}:continue
        if sha256(f)!=entry["sha256"]:p.error("Changed Java reference input: "+str(f))
        cp.append(f)
    classes=out/"classes";classes.mkdir()
    sources=sorted((ROOT/"compiler/metal-backend/src").rglob("*.java"))
    sources.append(ROOT/"interop/graphics/MetalProbe.java")
    sources.append(ROOT/"interop/graphics/MetalResourceProbe.java")
    sources.append(ROOT/"interop/graphics/NativeImageProbe.java")
    sources.append(ROOT/"interop/graphics/MetalDrawProbe.java")
    target="arm64-apple-ios17.0"+("-simulator" if args.sdk=="iphonesimulator" else "")
    result={"status":"BLOCKED","gateC0a":"BLOCKED","target":target,
            "scope":"Metal resources and precompiled vanilla pipelines with draw/bind/scissor paths; full game integration remains experimental",
            "sourcesSHA256":{str(f.relative_to(ROOT)):sha256(f) for f in [*sources,ROOT/"ios/metal-bridge/metal_bridge.m",ROOT/"ios/metal-bridge/metal_resources.h",ROOT/"ios/metal-bridge/metal_resources.m",ROOT/"ios/metal-bridge/present.metal",ROOT/"ios/metal-bridge/texture_transfer.h",ROOT/"interop/graphics/TextureSpecProbe.java",ROOT/"interop/graphics/texture_transfer_test.c"]},
            "classpathSHA256":{str(f):sha256(f) for f in cp},"glfwSHA256":sha256(glfw)}
    compiled=capture([str(home/"bin/javac"),"-proc:none","-cp",os.pathsep.join(map(str,cp)),"-d",str(classes),*map(str,sources)],out/"javac",180)
    result["javac"]=compiled
    if not compiled["exitCode"]:
        jar=out/"metal-backend.jar"
        with zipfile.ZipFile(jar,"w",zipfile.ZIP_DEFLATED) as archive:
            for f in sorted(classes.rglob("*.class")):archive.write(f,f.relative_to(classes).as_posix())
        binary=out/"libfaot_metal.dylib"
        native=capture(["xcrun","--sdk",args.sdk,"clang","-target",target,"-std=c11","-fobjc-arc","-O2","-Wall","-Wextra","-Werror",
            "-I",str(home/"include"),"-I",str(home/"include/darwin"),"-I",str(ROOT/"ios/glfw-lite"),"-dynamiclib",
            str(ROOT/"ios/metal-bridge/metal_bridge.m"),str(ROOT/"ios/metal-bridge/metal_resources.m"),str(glfw),"-framework","Metal","-framework","QuartzCore","-framework","Foundation",
            "-install_name","@rpath/libfaot_metal.dylib","-o",str(binary)],out/"native-compile",180)
        result["native"]=native
        if not native["exitCode"]:
            air=out/"present.air";metallib=out/"fabricaot-present.metallib"
            metal_target="air64-apple-ios17.0"+("-simulator" if args.sdk=="iphonesimulator" else "")
            metal=capture(["xcrun","--sdk",args.sdk,"metal","-c","-std=ios-metal2.4","-target",metal_target,
                           "-fmodules-cache-path="+str(out/"metal-module-cache"),str(ROOT/"ios/metal-bridge/present.metal"),"-o",str(air)],out/"metal-compile",180)
            result["metalCompile"]=metal
            if not metal["exitCode"]:
                linked=capture(["xcrun","--sdk",args.sdk,"metallib",str(air),"-o",str(metallib)],out/"metallib",180)
                result["metallibLink"]=linked
                if not linked["exitCode"]:result["metallibSHA256"]=sha256(metallib)
            validate_dylib(binary,args.sdk=="iphonesimulator")
            if result.get("metallibSHA256"):result.update(status="METAL_BOOTSTRAP_BUILT",jarSHA256=sha256(jar),binarySHA256=sha256(binary))
    if args.test_host and not compiled["exitCode"]:
        tests=out/"test-classes";tests.mkdir()
        compiled_test=capture([str(home/"bin/javac"),"-proc:none","-cp",str(classes)+os.pathsep+os.pathsep.join(map(str,cp)),"-d",str(tests),str(ROOT/"interop/graphics/TextureSpecProbe.java")],out/"contract-compile",120)
        policy=out/"contract.sb";policy.write_text(sandbox_policy(out,home,cp))
        if not compiled_test["exitCode"]:
            tested=capture(["/usr/bin/sandbox-exec","-f",str(policy),str(home/"bin/java"),"-Xmx128m","-cp",str(tests)+os.pathsep+str(classes)+os.pathsep+os.pathsep.join(map(str,cp)),"fabricaot.metal.TextureSpecProbe"],out/"contract-run",30)
            result["hostContracts"]="PASS" if not tested["exitCode"] and "METAL_TEXTURE_CONTRACT_PASS" in (out/"contract-run/stdout.log").read_text() else "FAIL"
        else:result["hostContracts"]="FAIL"
        if result["hostContracts"]!="PASS":result["status"]="BLOCKED"
        executable=out/"pixel-layout-test"
        pixel_compile=capture(["xcrun","clang","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I",str(ROOT/"ios/metal-bridge"),str(ROOT/"interop/graphics/texture_transfer_test.c"),"-o",str(executable)],out/"pixel-layout-compile",60)
        if not pixel_compile["exitCode"]:
            pixel=capture([str(executable)],out/"pixel-layout-run",30)
            result["hostPixelLayout"]="PASS" if not pixel["exitCode"] and "METAL_PIXEL_LAYOUT_PASS" in (out/"pixel-layout-run/stdout.log").read_text() else "FAIL"
        else:result["hostPixelLayout"]="FAIL"
        if result["hostPixelLayout"]!="PASS":result["status"]="BLOCKED"
        lifetime=out/"metal-resource-lifetime-test"
        lifetime_compile=capture(["xcrun","clang","-fobjc-arc","-Wall","-Wextra","-Werror","-I",str(home/"include"),"-I",str(home/"include/darwin"),
            "-I",str(ROOT/"ios/metal-bridge"),str(ROOT/"tests/metal_resource_lifetime_test.m"),str(ROOT/"ios/metal-bridge/metal_resources.m"),
            "-framework","Metal","-framework","Foundation","-framework","QuartzCore","-o",str(lifetime)],out/"resource-lifetime-compile",120)
        if not lifetime_compile["exitCode"]:
            lifetime_run=capture([str(lifetime)],out/"resource-lifetime-run",120)
            result["hostResourceLifetime"]="PASS" if not lifetime_run["exitCode"] and "METAL_RESOURCE_LIFETIME_PASS" in (out/"resource-lifetime-run/stdout.log").read_text() else "FAIL"
        else:result["hostResourceLifetime"]="FAIL"
        if result["hostResourceLifetime"]!="PASS":result["status"]="BLOCKED"
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    try:register_tree(out,[sys.executable,"-B",str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    except (OSError,RuntimeError) as exc:print(str(exc),file=sys.stderr);return 1
    print(json.dumps({k:v for k,v in result.items() if k not in ("javac","native","classpathSHA256","sourcesSHA256","metalCompile","metallibLink")},indent=2))
    return 0 if result["status"]=="METAL_BOOTSTRAP_BUILT" else 2

if __name__=="__main__":raise SystemExit(main())
