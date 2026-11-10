#!/usr/bin/env python3
"""Run a fresh simulator Metal integration probe and retain its log and actual display image.

Requires a newly created log, RenderSystem initialization, successful Metal presentation and
normal probe completion. The result remains a simulator diagnostic, never a playable-game gate.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from bootstrap_toolchain import sha256
from capture import ROOT,capture
from graphics_common import register_tree

def classify_log(text: str,probe: str="clear")->dict:
    if probe=='audio':return {'audioDeviceInitialized':'OPENAL_DEVICE renderer=' in text,
        'coreAudioPlaybackBackend':'Added "core" for playback' in text,
        'pcmPlaybackVerified':'OPENAL_PCM_PLAYBACK_PASS bytes=4410 muted=true' in text,
        'probeCompleted':'OPENAL_PROBE_PASS' in text,'entryReturnedZero':'[FAOT] run_main returned 0' in text}
    resources=probe in ("resources","images","draw")
    facts={"renderSystemInitialized":"MINECRAFT_RENDER_SYSTEM_INITIALIZED backend=Metal" in text,
            "framePresented":("[Metal] TEXTURE_FRAME_PRESENTED" if resources else "[Metal] DIAGNOSTIC_FRAME_PRESENTED") in text,
            "probeCompleted":("METAL_DRAW_PROBE_PASS" if probe=="draw" else "METAL_RESOURCE_PROBE_PASS" if resources else "METAL_INTEGRATION_PROBE_PASS") in text,
            "entryReturnedZero":"[FAOT] run_main returned 0" in text}
    if resources and probe!="draw":facts["resourceRoundtripVerified"]="METAL_RESOURCE_ROUNDTRIP_PASS" in text
    if probe=="images":facts["nativeImageVerified"]="MINECRAFT_NATIVE_IMAGE_PASS" in text
    if probe=="draw":
        facts['vanillaPipelinesVerified']='VANILLA_METAL_PSO_PASS count=87' in text
        facts['vanillaPixelsVerified']='METAL_VANILLA_DRAW_PASS' in text
    return facts

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--simulator",required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--probe",choices=("clear","resources","images","draw","audio"),default="clear")
    p.add_argument("--check-runtime",action="store_true",help="Enable Apple's Main Thread Checker and Metal API validation for this simulator run")
    args=p.parse_args(argv)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    command=["xcrun","simctl","get_app_container",args.simulator,"org.fabricaot.research.c0.kexin","data"]
    container=subprocess.run(command,capture_output=True,text=True,timeout=15)
    if container.returncode:raise SystemExit(container.stderr)
    log_dir=Path(container.stdout.strip())/"Documents/c0-logs"
    known={f.name for f in log_dir.glob("run-*.log")}
    previous={}
    environment={}
    if args.probe=='audio':environment.update(SIMCTL_CHILD_ALSOFT_DRIVERS='core',SIMCTL_CHILD_ALSOFT_LOGLEVEL='3')
    if args.check_runtime:
        checker=Path("/Applications/Xcode.app/Contents/Developer/usr/lib/libMainThreadChecker.dylib")
        if not checker.is_file():p.error("Apple Main Thread Checker unavailable")
        environment.update(SIMCTL_CHILD_DYLD_INSERT_LIBRARIES=str(checker),SIMCTL_CHILD_MTL_DEBUG_LAYER='1')
    for name,value in environment.items():previous[name]=os.environ.get(name);os.environ[name]=value
    try:launched=capture(["xcrun","simctl","launch","--terminate-running-process",args.simulator,"org.fabricaot.research.c0.kexin"],out/"launch",30)
    finally:
        for name,value in previous.items():
            if value is None:os.environ.pop(name,None)
            else:os.environ[name]=value
    result={"status":"BLOCKED","gateC0":"BLOCKED","gateC0a":"BLOCKED","simulator":args.simulator,
            "scope":("actual Window and RenderSystem + GPU resource roundtrip, optional NativeImage checks and first-party presentation; no game pipelines or device acceptance" if args.probe!="clear" else "actual Window and RenderSystem bootstrap + diagnostic Metal clear; no game pipelines or device acceptance"), "launch":launched}
    result["probe"]=args.probe;result["runtimeCheckersRequested"]=args.check_runtime
    if args.probe=='draw':result['scope']='actual vanilla shaders/PSOs and GPU pixel assertions with first-party geometry; no game Main/menu acceptance'
    if args.probe=='audio':result['scope']='actual OpenAL context, PCM upload and muted playback progression; audible output and game audio not accepted'
    deadline=time.monotonic()+45;current=None;screenshot=False
    if launched["exitCode"]==0:
        while time.monotonic()<deadline:
            fresh=sorted(f for f in log_dir.glob("run-*.log") if f.name not in known)
            if fresh:
                current=fresh[-1];text=current.read_text(errors="replace")
                facts=classify_log(text,args.probe);result.update(facts)
                if facts.get("framePresented") and not screenshot:
                    shot=capture(["xcrun","simctl","io",args.simulator,"screenshot",str(out/"frame.png")],out/"screenshot",15)
                    screenshot=shot["exitCode"]==0 and (out/"frame.png").exists();result["screenshot"]=shot
                if all(facts.values()):
                    warnings=[warning for warning in ("Main Thread Checker: UI API called on a background thread","should not be called after already presenting this drawable") if warning in text]
                    result["runtimeWarnings"]=warnings
                    result["status"]=("RUNTIME_WARNINGS" if warnings else "SIMULATOR_OPENAL_PCM_PASS" if args.probe=='audio' else "SIMULATOR_VANILLA_METAL_DRAW_PASS" if args.probe=="draw" else "SIMULATOR_METAL_IMAGES_PASS" if args.probe=="images" else "SIMULATOR_METAL_RESOURCES_PASS" if args.probe=="resources" else "SIMULATOR_METAL_DIAGNOSTIC_PASS") if screenshot or args.probe=='audio' else "SCREENSHOT_FAILED";break
                if re.search(r'^\[FAOT\] run_main returned -?[1-9][0-9]*$',text,re.M) or '[FAOT] FATAL signal' in text:break
            time.sleep(0.1)
    if current:shutil.copy2(current,out/current.name);result["runLog"]=current.name
    result["filesSHA256"]={f.name:sha256(f) for f in out.iterdir() if f.is_file()}
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    try:register_tree(out,[sys.executable,"-B",str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)],regenerable=False)
    except (OSError,RuntimeError) as exc:print(str(exc),file=sys.stderr);return 1
    print(json.dumps({k:v for k,v in result.items() if k not in ("launch","screenshot")},indent=2))
    return 0 if result["status"] in ("SIMULATOR_METAL_DIAGNOSTIC_PASS","SIMULATOR_METAL_RESOURCES_PASS","SIMULATOR_METAL_IMAGES_PASS","SIMULATOR_VANILLA_METAL_DRAW_PASS","SIMULATOR_OPENAL_PCM_PASS") else 2

if __name__=="__main__":raise SystemExit(main())
