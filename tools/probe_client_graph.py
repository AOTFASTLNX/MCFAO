#!/usr/bin/env python3
"""Analyze the real locally owned client entry graph; this is not a game runtime or C0 acceptance."""
from __future__ import annotations
import os

import argparse
import json
import shutil
import socket
import subprocess
import zipfile
from pathlib import Path

from bootstrap_toolchain import sha256
from capture import ROOT, capture
from run_b0_reference import execute, require_run, sandbox_policy
from client_graph_diagnostics import audit_metadata, parse_time_rss, read_analysis_statistics, summarize_gc_logs
from graphics_common import bridge_overlays
from lwjgl_codegen import CALLBACKS
from config_reflection import reflection_from_jar

def verify_split_runtime_input(candidate: Path)->dict|None:
    manifest=candidate.parent/'result.json'
    if not manifest.is_file():return None
    record=json.loads(manifest.read_text())
    if record.get('status')=='BACKEND_INJECTED':
        if sha256(candidate)!=record.get('outputJarSHA256'):raise ValueError('Injected client fingerprint changed')
        original=Path(record['client']);verified=verify_split_runtime_input(original)
        if not verified or verified!=record.get('splitRuntimeValidation') or sha256(original)!=record.get('clientSHA256'):
            raise ValueError('Injected client split provenance changed')
        return {'injectionManifestSHA256':sha256(manifest),'split':verified}
    if record.get('status')!='SPLIT':return None
    if sha256(candidate)!=record.get('outputJarSHA256'):raise ValueError('Split client fingerprint changed')
    changed=[row for row in record.get('classes',[]) if row.get('methodsSplit',0)]
    if not changed or any('finalFieldsUnfinalised' not in row for row in changed):
        raise ValueError('Old split client lacks final-field relocation validation; use the corrected split output')
    return {'manifestSHA256':sha256(manifest),'finalFieldsUnfinalised':sum(row['finalFieldsUnfinalised'] for row in changed)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, default=ROOT / "artifacts/b0/prepared-04")
    parser.add_argument("--runtime", type=Path, default=ROOT / "artifacts/b1/runtime-ios")
    parser.add_argument("--caps", type=Path, default=ROOT / "artifacts/b1/ios-probe-03/work/caps")
    parser.add_argument("--b1-evidence", type=Path, default=ROOT / "artifacts/evidence/b1-user-device-run-01/result.json")
    parser.add_argument("--heap-gib", type=int, choices=(6, 7, 8, 9), default=6)
    parser.add_argument("--builder-gc", choices=("parallel", "g1"), default="parallel")
    parser.add_argument("--oom-stack", action="store_true", help="Let the build JVM report the first OOM instead of immediately exiting")
    parser.add_argument("--census-agent",type=Path,help="Sandbox-verified first-party Mac JVMTI agent directory")
    parser.add_argument("--census-at",default=None,
                        help="Comma separated second offsets for scheduled shallow snapshots; needs --census-agent")
    parser.add_argument("--analysis-mode",choices=("default","conservative"),default="default",
                        help="Conservative points-to mode disables primitive tracking and predicates")
    parser.add_argument("--analysis-inline-depth",type=int,default=20,
                        help="InlineBeforeAnalysisAllowedDepth; 0 is known-broken (MetadataTracer)")
    parser.add_argument("--analysis-inline-inlinings",type=int,default=10000,
                        help="InlineBeforeAnalysisAllowedInlinings applied to nested scopes only")
    parser.add_argument("--constructor-inline-nodes",type=int,choices=(0,200),default=200)
    parser.add_argument("--methodhandle-inline-nodes",type=int,default=10000,
                        help="InlineBeforeAnalysisMethodHandleAllowedNodes (default 10000)")
    parser.add_argument("--methodhandle-inline-depth",type=int,default=1000,
                        help="InlineBeforeAnalysisMethodHandleAllowedDepth (default 1000)")
    parser.add_argument("--methodhandle-inline-inlines",type=int,default=10000,
                        help="InlineBeforeAnalysisMethodHandleAllowedInlinings (default 10000)")
    parser.add_argument("--parallelism",type=int,default=4,help="Native Image build parallelism, not a hard thread cap")
    parser.add_argument("--full-build",action="store_true",
                        help="Do not stop after analysis: continue through code generation and linking")
    parser.add_argument("--relocatable",action="store_true",
                        help="With --full-build: stop after writing the relocatable image object instead of "
                             "letting Native Image invoke the host linker (it would link macOS libraries)")
    parser.add_argument("--simulator-thread-dumps",action="store_true",
                        help="Include SIGQUIT Java thread dumps and native frame pointers in a simulator research image")
    parser.add_argument("--client-jar",type=Path,
                        help="Use this client jar instead of the verified launcher copy (e.g. a split build)")
    parser.add_argument("--client-jar-note",default="",
                        help="Free-form provenance note recorded next to the client jar override")
    parser.add_argument("--include-game-resources",action="store_true",help="Embed owned vanilla assets/data and pack/version metadata for the actual Main entry")
    parser.add_argument("--initialize-at-build-time",default="",
                        help="Comma separated classes initialized on the build host instead of at run time")
    parser.add_argument("--graphics-bridge",type=Path,help="Verified build_lwjgl_lite output; replace core/GLFW jars with explicit iOS JNI overlays")
    parser.add_argument("--window-probe",action="store_true",help="Build only the first-party entry that invokes the real 26.1.2 Window; requires --graphics-bridge")
    parser.add_argument('--openal-probe',action='store_true',help='Real OpenAL device/context/PCM playback probe; requires graphics bridge')
    parser.add_argument("--metal-bootstrap",type=Path,help="Verified build_metal_backend output")
    parser.add_argument("--metal-probe",action="store_true",help="Real Window/RenderSystem plus diagnostic clear; requires --graphics-bridge and --metal-bootstrap")
    parser.add_argument("--metal-resource-probe",action="store_true",help="Actual blaze3d resource transfers, GPU readback and precompiled presentation; requires graphics and Metal inputs")
    parser.add_argument("--metal-draw-probe",action="store_true",help="Actual vanilla shaders, PSO creation and GPU pixel assertions; requires graphics and Metal inputs")
    args = parser.parse_args(argv)
    if args.window_probe and not args.graphics_bridge:parser.error("--window-probe requires --graphics-bridge")
    if args.openal_probe and not args.graphics_bridge:parser.error('--openal-probe requires --graphics-bridge')
    if args.metal_probe and (not args.graphics_bridge or not args.metal_bootstrap):parser.error("--metal-probe requires graphics bridge and Metal bootstrap")
    if args.metal_resource_probe and (not args.graphics_bridge or not args.metal_bootstrap):parser.error("--metal-resource-probe requires graphics bridge and Metal bootstrap")
    if args.metal_draw_probe and (not args.graphics_bridge or not args.metal_bootstrap):parser.error("--metal-draw-probe requires graphics bridge and Metal bootstrap")
    if sum((args.window_probe,args.openal_probe,args.metal_probe,args.metal_resource_probe,args.metal_draw_probe))>1:parser.error("Choose one graphics integration probe")
    if args.relocatable and not args.full_build:
        parser.error("--relocatable only applies to --full-build runs")
    if args.simulator_thread_dumps and not args.relocatable:
        parser.error("--simulator-thread-dumps requires --full-build --relocatable")
    if not 0 <= args.analysis_inline_depth <= 20:
        parser.error("--analysis-inline-depth must be within 0..20")
    if not 1 <= args.analysis_inline_inlinings <= 10000:
        parser.error("--analysis-inline-inlinings must be within 1..10000")
    if not 0 <= args.methodhandle_inline_nodes <= 10000:
        parser.error("--methodhandle-inline-nodes must be within 0..10000")
    if not 0 <= args.methodhandle_inline_depth <= 1000:
        parser.error("--methodhandle-inline-depth must be within 0..1000")
    if not 0 <= args.methodhandle_inline_inlines <= 10000:
        parser.error("--methodhandle-inline-inlines must be within 0..10000")
    if not 1 <= args.parallelism <= 4:
        parser.error("--parallelism must be within 1..4")
    if args.census_at:
        if not args.census_agent:
            parser.error("--census-at requires --census-agent")
        import re as _re
        if not _re.fullmatch(r"[0-9]{1,4}(,[0-9]{1,4})*", args.census_at):
            parser.error("--census-at must be comma separated whole seconds")
    if json.loads(args.b1_evidence.read_text())["gateB1"] != "PASS":
        parser.error("Confirmed B1 device behavior required")
    prepared = args.prepared.resolve(strict=True)
    manifest = json.loads((prepared / "result.json").read_text())
    home = Path(manifest["javaHome"])
    if sha256(home / "bin/java") != manifest["javaSHA256"]:
        parser.error("Java changed")
    libraries = []
    for entry in manifest["referenceLibraries"]:
        path = Path(entry["path"])
        # This isolates the core client graph from Loader/bootstrap/Mod transformation.
        if any(piece in path.name for piece in ["fabric-loader-", "sponge-mixin-", "intermediary-"]):
            continue
        if sha256(path) != entry["sha256"]:
            parser.error("Reference library changed: " + str(path))
        libraries.append(path)
    client_jar_override = None
    if args.graphics_bridge:
        try: overlays=bridge_overlays(args.graphics_bridge)
        except (OSError,ValueError,KeyError) as error:parser.error(str(error))
        replaced={p.name.replace("-ios.jar","-3.4.1.jar") for p in overlays}
        libraries=[*overlays,*(p for p in libraries if p.name not in replaced)]
    if args.metal_bootstrap:
        metal=args.metal_bootstrap.resolve(strict=True)
        report=json.loads((metal/"result.json").read_text())
        if report.get("status")!="METAL_BOOTSTRAP_BUILT" or sha256(metal/"metal-backend.jar")!=report.get("jarSHA256"):
            parser.error("Metal bootstrap missing or modified")
        libraries.insert(0,metal/"metal-backend.jar")
    if args.client_jar:
        candidate = args.client_jar.resolve(strict=True)
        try:split_input=verify_split_runtime_input(candidate)
        except ValueError as error:parser.error(str(error))
        replaced = 0
        for index, path in enumerate(libraries):
            # The client jar is the only library that lives in versions/<version>/.
            if path.name.startswith("26.1.2") and path.suffix == ".jar" and path.parent.name == "26.1.2":
                libraries[index] = candidate
                replaced += 1
        if replaced != 1:
            parser.error("--client-jar replaced %d libraries, expected exactly 1" % replaced)
        # The merged client jar carries Mixin-transformed copies of library classes (a Mixin may
        # target a library class, and Fabric API's dimension module does exactly that). Native
        # Image resolves a duplicated class from the first classpath entry, so the client jar has
        # to precede the libraries it shadows. No library shares a class file with it otherwise,
        # which is what makes the position free to choose.
        libraries.remove(candidate)
        libraries.insert(0, candidate)
        client_jar_override = {"path": str(candidate), "sha256": sha256(candidate),
                               "original": str(args.client_jar.parent),
                               "note": args.client_jar_note or None}
        if split_input:client_jar_override['splitRuntimeValidation']=split_input
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    # The output may live under an artifacts symlink in a worktree. Sandbox rules and child cwd
    # must use the same physical path; otherwise macOS denies getcwd() despite the lexical work
    # path being allowed, and HotSpot fails during VM property initialization.
    output = output.resolve(strict=True)
    sources=output/"source"
    for name in ["probe_client_graph.py","client_graph_diagnostics.py","run_b0_reference.py",
                 "config_reflection.py"]:
        sources.mkdir(exist_ok=True)
        shutil.copy2(ROOT/"tools"/name,sources/name)
    work = output / "work"
    for name in ["tmp", "home", "caps"]:
        (work / name).mkdir(parents=True, exist_ok=True)
    entry_class="net.minecraft.client.main.Main"
    if args.window_probe or args.openal_probe:
        probe_name='OpenALProbe' if args.openal_probe else 'WindowProbe'
        classes=work/"classes";classes.mkdir()
        compiled=capture([str(home/"bin/javac"),"-proc:none","-cp",":".join(map(str,libraries)),"-d",str(classes),
                          str(ROOT/('interop/graphics/'+probe_name+'.java'))],output/"window-probe-compile",180)
        if compiled["exitCode"]:parser.error("Window probe compilation failed; see window-probe-compile/stderr.log")
        jar=work/"window-probe.jar"
        with zipfile.ZipFile(jar,"w",compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(classes.rglob("*.class")):archive.write(path,path.relative_to(classes).as_posix())
        libraries.insert(0,jar)
        entry_class='fabricaot.graphics.'+probe_name
    if args.metal_probe:entry_class="fabricaot.graphics.MetalProbe"
    if args.metal_resource_probe:entry_class="fabricaot.graphics.MetalResourceProbe"
    if args.metal_draw_probe:entry_class="fabricaot.graphics.MetalDrawProbe"
    agent_library=None
    if args.census_agent:
        agent=args.census_agent.resolve(strict=True)
        verified=json.loads((agent/'result.json').read_text())
        if verified.get('status')!='VERIFIED' or verified.get('fixtureTest')!='PASS' or verified['javaSHA256']!=manifest['javaSHA256']:
            parser.error('Verified diagnostic agent for this Java required')
        if sha256(agent/'liboomcensus.dylib')!=verified['librarySHA256']:parser.error('Agent changed')
        agent_library=work/'liboomcensus.dylib';shutil.copy2(agent/'liboomcensus.dylib',agent_library)
    shutil.copytree(args.caps, work / "caps", dirs_exist_ok=True)
    driver = prepared / "driver.jar"
    if sha256(driver) != manifest["binaries"]["driver.jar"]["sha256"]:
        parser.error("Control driver changed")
    runtime_dir = args.runtime.resolve(strict=True)
    runtime = json.loads((runtime_dir / "result.json").read_text())
    if runtime.get("target") != "arm64-apple-ios17.0" or runtime.get("status") != "COMPILED":
        parser.error("Actual iPhoneOS static runtime required")
    runtime_files = []
    for entry in runtime["archives"].values():
        path = Path(entry["path"])
        if sha256(path) != entry["sha256"]: parser.error("Static runtime changed")
        runtime_files.append(path)
    policy = sandbox_policy(work, home, [*libraries, driver, *runtime_files])
    # -H:CLibraryPath is handed to NativeLibraries as a directory, which lists it before analysis
    # ends; allowing only the archive files left that listing denied (Operation not permitted).
    policy += '(allow file-read* (subpath ' + json.dumps(str(runtime_dir)) + '))\n'

    executable = (home / "bin/native-image").resolve(strict=True)
    policy += '(allow process-exec (literal ' + json.dumps(str(executable)) + '))\n'
    compiler = Path(subprocess.check_output(["/usr/bin/xcrun", "--find", "clang"], text=True).strip()).resolve(strict=True)
    policy += '(allow file-read* (literal ' + json.dumps(str(compiler)) + '))\n'
    policy += '(allow process-exec (literal ' + json.dumps(str(compiler)) + '))\n'
    # The builder JVM launches every child through lib/jspawnhelper (POSIX_SPAWN is the macOS default).
    # Without an exec allowance for it, any ProcessBuilder call dies as "posix_spawn failed, error: 0"
    # even when the child itself is allowed. Proven by artifacts/c0/spawn-probe: the same policy plus
    # this one literal spawns clang, and -Djdk.lang.Process.launchMechanism=FORK is the alternative.
    spawn_helper = home / "lib/jspawnhelper"
    if spawn_helper.exists():
        policy += '(allow process-exec (literal ' + json.dumps(str(spawn_helper)) + '))\n'
    if args.full_build:
        # Linking runs clang, which spawns ld/cc1 from the same toolchain directory. Allowing only the
        # single clang literal made posix_spawn fail ("error: 0"), so the toolchain's own bin and lib
        # subtrees are opened for read+exec. Nothing outside Apple's toolchain is widened.
        toolchain = compiler.parent.parent
        for subtree in ("bin", "lib", "include"):
            target = toolchain / subtree
            if target.exists():
                policy += '(allow file-read* (subpath ' + json.dumps(str(target)) + '))\n'
                policy += '(allow process-exec (subpath ' + json.dumps(str(target)) + '))\n'
        # Apple's clang driver only derives -isysroot from SDKROOT (the /usr/bin/clang shim would have
        # called xcrun first). Without it the link drops every system library: "ld: library 'dl' not
        # found". Round 33 adds the SDK read plus SDKROOT; artifacts/c0/spawn-probe/sdk-result.json
        # holds the before/after pair.
        sdk_root = Path(subprocess.check_output(["/usr/bin/xcrun", "--show-sdk-path"], text=True).strip()).resolve(strict=True)
        policy += '(allow file-read* (subpath ' + json.dumps(str(sdk_root)) + '))\n'
    policy_file = output / "policy.sb"
    policy_file.write_text(policy)
    base = ["/usr/bin/sandbox-exec", "-f", str(policy_file)]
    control = output / "outside-control.txt"
    control.write_text("first-party-client-analysis-control\n")
    outside_write = output / "outside-write.txt"
    result = {"status":"BLOCKED", "gateC0":"BLOCKED", "mode":"client-graph-diagnostic",
              "scope":"real net.minecraft.client.main.Main reachability only; no game execution, auth arguments or rendering",
              "classpathSHA256":{str(p):sha256(p) for p in libraries if p.is_file()},
              "gateC1":"NOT RUN", "gateC2":"NOT RUN", "heapGiB":args.heap_gib,
              "targetCodeGeneration":"NOT RUN", "targetExecution":"NOT RUN",
              "fullClientFabricTransformation":"NOT RUN",
              "analysisCompleted":False, "builderJfrEnabled":False,
              "fullBuildRequested":args.full_build, "imageArtifacts":None,
              "builderGC":args.builder_gc,
              "oomStackRequested":args.oom_stack,
              "diagnosticAgent":str(args.census_agent) if args.census_agent else None,
              "scheduledSnapshots":args.census_at,
              "analysisMode":args.analysis_mode,
              "analysisInlineDepth":args.analysis_inline_depth,
              "analysisInlineInlinings":args.analysis_inline_inlinings,
              "constructorInlineNodes":args.constructor_inline_nodes,
              "methodHandleInlineNodes":args.methodhandle_inline_nodes,
              "methodHandleInlineDepth":args.methodhandle_inline_depth,
              "methodHandleInlineInlinings":args.methodhandle_inline_inlines,
              "buildParallelism":args.parallelism,
              "initializeAtBuildTime":args.initialize_at_build_time or None,
              "builderSHA256":sha256(Path(__file__)),
              "diagnosticsHelperSHA256":sha256(ROOT/"tools/client_graph_diagnostics.py"),
              "clientJarOverride":client_jar_override}
    if args.graphics_bridge:
        result["graphicsBridge"]=str(args.graphics_bridge.resolve())
        result["entryClass"]=entry_class
        if args.window_probe:result["scope"]="real 26.1.2 Window constructor only; no Minecraft main, renderer or gameplay"
        if args.openal_probe:result['scope']='real audio context/PCM playback progression, muted fixture; no audible or game audio acceptance'
        if args.metal_probe:result["scope"]="real Window/RenderSystem plus diagnostic Metal clear; game pipelines unavailable"
        if args.metal_resource_probe:result["scope"]="real Window/RenderSystem plus GPU resource roundtrip and first-party presentation; game draw pipelines unavailable"
        if args.metal_draw_probe:result["scope"]="real vanilla shaders/PSOs with first-party geometry and pixel assertions; not game Main/menu acceptance"
    try:
        host = subprocess.run(["/usr/bin/memory_pressure", "-Q"], capture_output=True, text=True, timeout=10)
        (output/"host-memory-before.log").write_text(host.stdout+host.stderr)
        import re
        physical = re.search(r"system has (\d+)", host.stdout)
        free = re.search(r"memory free percentage:\s*(\d+)%", host.stdout)
        if host.returncode or not physical or not free:
            raise RuntimeError("Cannot establish host memory budget")
        result["hostMemory"]={"physicalBytes":int(physical.group(1)), "availablePercent":int(free.group(1)),
                              "heapLimitGiB":args.heap_gib, "check":"preflight only; not an RSS limit"}
        # The analysis peaked at 5.9 GiB of a 6 GiB heap (pack-43); packs 61-68 held ~4.96 GB
        # live under 8 GiB. pack-69 (first pack without Iris) reached 7087M live against a 7337M
        # old-gen capacity, so 9 GiB is now the working setting. Half of physical memory is the
        # hard ceiling and 9 GiB is exactly that on an 18 GiB machine; anything larger has to
        # come with a bigger host, not a bigger flag.
        if args.heap_gib*1024**3 > int(physical.group(1))*0.50 or int(free.group(1)) < (45 if args.heap_gib==8 else 35):
            raise RuntimeError("Host memory headroom below bounded experiment threshold")
        if shutil.disk_usage(output).free < 8*1024**3:
            raise RuntimeError("Less than 8 GiB free disk headroom")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1",0));listener.listen(1);listener.settimeout(0.05)
            step=output/"sandbox-probe"
            check=execute([*base,str(home/"bin/java"),"-XX:+DisableAttachMechanism","-XX:-UsePerfData","-Xmx128m",
                "-Duser.home="+str(work/"home"),"-Djava.io.tmpdir="+str(work/"tmp"),"-cp",str(driver),
                "fabricaot.b0.bootstrap.SandboxProbe",str(control),str(outside_write),str(listener.getsockname()[1])],step,work)
            require_run(check,step,"B0_SANDBOX_PASS")
            if outside_write.exists():raise RuntimeError("Outside write allowed")
            try:
                connection,_=listener.accept();connection.close();raise RuntimeError("Network allowed")
            except socket.timeout:pass
        result["sandboxProbe"]="PASS"
        # The sandbox only opens the work directory for reads, so the reflection config is copied in
        # rather than referenced from compiler/ where it is maintained.
        reflection_config = work / "reflection-config.json"
        reflection_entries = json.loads((ROOT / "compiler/reflection-config.json").read_text())
        inferred = reflection_from_jar(args.client_jar) if args.client_jar else []
        by_name = {entry["name"]: entry for entry in reflection_entries}
        for entry in inferred:
            by_name.setdefault(entry["name"], {}).update(entry)
        reflection_config.write_text(json.dumps(list(by_name.values()), indent=2) + "\n")
        result["configurationReflection"] = [entry["name"] for entry in inferred]
        # Name-based lookups Mods perform at run time. A closed world answers getDeclaredMethod
        # from metadata only, so these are the members whose absence would look like a missing
        # method rather than a missing registration.
        result["reflectiveMembers"] = {
            entry["name"]: sorted([item["name"] for item in entry.get("methods", ())] +
                                  [item["name"] for item in entry.get("fields", ())])
            for entry in inferred if entry.get("methods") or entry.get("fields")}
        cmd=[*base,str(executable),"--no-fallback","-H:+SharedArenaSupport",os.environ.get("MCFAO_OPT_LEVEL","-O1"),f"--parallelism={args.parallelism}",f"-J-Xmx{args.heap_gib}g","-J-XX:-UsePerfData",
             "-J-Duser.home="+str(work/"home"),"-J-Djava.io.tmpdir="+str(work/"tmp"),"-H:+UnlockExperimentalVMOptions",
             "--shared","--verbose","--diagnostics-mode","-H:+PrintAnalysisStatistics",
             "-H:BuildOutputJSONFile="+str(work/"build-output.json"),
             "-J-Xlog:gc*,safepoint:file="+str(work/"gc.log")+":time,uptime,level,tags:filecount=2,filesize=8M",
             "-H:-CheckToolchain","-H:CCompilerPath="+str(compiler),"-H:CLibraryPath="+str(runtime_dir),"-H:PageSize=16384","-Dsvm.targetName=iOS","-Dsvm.targetArch=arm64",
             "-Dsvm.platform=org.graalvm.nativeimage.Platform$IOS_AARCH64","-H:+ExitAfterAnalysis","-H:+UseCAPCache",
             "-H:CAPCacheDir="+str(work/"caps"),"-H:TempDirectory="+str(work/"native-tmp"),
             # joptsimple is here for a specific reason: its Reflection class keeps a
             # HashMap<Class<?>, ValueConverter<?>> that Main.main queries via ofType(File.class).
             # Initialised at build time, that table is serialised into the image heap and the
             # Class-keyed lookups miss at run time, so the client died with
             # "class java.io.File is not a value type" before it ever looked at an asset.
             "--initialize-at-run-time=net.minecraft,com.mojang,org.lwjgl,com.microsoft,io.netty,joptsimple,fabricaot",
             # Real cause of that message: joptsimple's constructorConverter calls
             # type.getConstructor(String.class) and swallows NoSuchMethodException. Native Image
             # ships no constructor metadata unless asked, so File had none. The config registers it.
             "-H:ReflectionConfigurationFiles="+str(reflection_config),
             "--enable-native-access=ALL-UNNAMED","-cp",":".join(map(str,libraries)),"-o",str(work/"client-graph"),
             entry_class]
        if entry_class=='net.minecraft.client.main.Main':
            # Authlib constructs HTTPS URLs during normal initialization, before network access.
            cmd.insert(cmd.index('-cp'),'--enable-url-protocols=http,https')
        if args.graphics_bridge:
            # Native callbacks call the known interfaces, never reflect on lambda implementation classes.
            config=[{"name":name,"methods":[{"name":"<init>","parameterTypes":["java.lang.String"]}]}
                    for name in ("java.lang.IllegalStateException","java.lang.IllegalArgumentException","java.lang.UnsatisfiedLinkError")]
            types={"I":"int","J":"long","Z":"boolean","D":"double"}
            for name,signature in CALLBACKS:
                config.append({"name":"org.lwjgl.stb.STBIWriteCallbackI" if name=="STBIWrite" else "org.lwjgl.glfw.GLFW"+name+"CallbackI",
                               "methods":[{"name":"invoke","parameterTypes":[types[t] for t in signature]}]})
            jni_config=work/"graphics-jni.json";jni_config.write_text(json.dumps(config,indent=2)+"\n")
            cmd.insert(cmd.index("-cp"),"-H:JNIConfigurationFiles="+str(jni_config))
        if args.include_game_resources:
            resource_config=work/'game-resources.json'
            # A root-level `*.toml` is a Mod's bundled default config: ForgeConfigAPIPort reads its
            # own one through `Class.getResourceAsStream` and copies it into the game directory on
            # first run, and `requireNonNull` makes a missing entry fatal. The OOM bisection
            # cleared this pattern of suspicion: it died with and without it. What actually
            # fixed the heap was narrowing the JAR resource merge (see AotExport), not this
            # list - one root toml is kilobytes.
            resource_config.write_text(json.dumps({'resources':{'includes':[{'pattern':p} for p in
                (r'assets/.*',r'data/.*',r'pack\.mcmeta',r'version\.json',r'com/ibm/icu/impl/data/.*',
                 r'[^/]+\.toml')]}} ,indent=2)+'\n')
            cmd.insert(cmd.index('-cp'),'-H:ResourceConfigurationFiles='+str(resource_config))
            result['gameResourceConfigurationSHA256']=sha256(resource_config)
        if args.builder_gc=="g1":
            # These flags affect the Mac build JVM, not the target iOS collector.
            cmd[cmd.index("-J-XX:-UsePerfData"):cmd.index("-J-XX:-UsePerfData")]=[
                "-J-XX:-UseParallelGC","-J-XX:+UseG1GC"]
        if args.full_build:
            # SDKROOT reached the builder's environment but never its linker child, so clang emitted no
            # -isysroot and every system library vanished ("ld: library 'dl' not found"). The sysroot is
            # therefore stated on the link line itself, where it is also visible in the recorded command.
            at = cmd.index("-H:-CheckToolchain")
            cmd[at:at] = ["-H:NativeLinkerOption=-isysroot", "-H:NativeLinkerOption=" + str(sdk_root)]
        if args.oom_stack:
            cmd.insert(cmd.index("-J-XX:-UsePerfData"),"-J-XX:-ExitOnOutOfMemoryError")
        if agent_library:
            cmd.insert(cmd.index("-J-XX:-UsePerfData"),"-J-agentpath:"+str(agent_library)+'='+str(work/'census.tsv'))
        if args.census_at:
            # Recorded through the command line, consumed by the agent's VMInit hook.
            cmd.insert(cmd.index("-J-XX:-UsePerfData"),"-J-Dfabricaot.census.at="+args.census_at)
        if args.initialize_at_build_time:
            cmd.insert(cmd.index("-cp"),"--initialize-at-build-time="+args.initialize_at_build_time)
        if args.analysis_mode=="conservative":
            cmd.insert(cmd.index("-H:+ExitAfterAnalysis"),"-H:-TrackPrimitiveValues")
            cmd.insert(cmd.index("-H:+ExitAfterAnalysis"),"-H:-UsePredicates")
        if args.analysis_inline_depth!=20:
            cmd.insert(cmd.index("-H:+ExitAfterAnalysis"),"-H:InlineBeforeAnalysisAllowedDepth="+str(args.analysis_inline_depth))
        if args.analysis_inline_inlinings!=10000:
            cmd.insert(cmd.index("-H:+ExitAfterAnalysis"),"-H:InlineBeforeAnalysisAllowedInlinings="+str(args.analysis_inline_inlinings))
        if args.methodhandle_inline_nodes!=10000:
            cmd.insert(cmd.index("-H:+ExitAfterAnalysis"),"-H:InlineBeforeAnalysisMethodHandleAllowedNodes="+str(args.methodhandle_inline_nodes))
        if args.methodhandle_inline_depth!=1000:
            cmd.insert(cmd.index("-H:+ExitAfterAnalysis"),"-H:InlineBeforeAnalysisMethodHandleAllowedDepth="+str(args.methodhandle_inline_depth))
        if args.methodhandle_inline_inlines!=10000:
            cmd.insert(cmd.index("-H:+ExitAfterAnalysis"),"-H:InlineBeforeAnalysisMethodHandleAllowedInlinings="+str(args.methodhandle_inline_inlines))
        if args.constructor_inline_nodes!=200:
            cmd.insert(cmd.index("-H:+ExitAfterAnalysis"),"-H:InlineBeforeAnalysisConstructorAllowedNodes="+str(args.constructor_inline_nodes))
        if args.full_build:
            cmd.remove("-H:+ExitAfterAnalysis")
        if args.relocatable:
            # Mirrors the B1 recipe: Native Image writes the image object and stops, so the link can be
            # performed for arm64-apple-ios with the iPhoneOS SDK and the iOS static runtime instead of
            # the host linker pulling in the macOS libdarwin.a and macOS system stubs.
            cmd.insert(cmd.index("-H:+UseCAPCache"),"-H:+ExitAfterRelocatableImageWrite")
        if args.simulator_thread_dumps:
            cmd[cmd.index("-cp"):cmd.index("-cp")]=[
                "-H:+DumpThreadStacksOnSignal","-H:+PreserveFramePointer","-R:+EnableSignalHandling"]
            result["simulatorThreadDumps"]=True
        audit=audit_metadata(libraries,cmd)
        (output/"metadata-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
        if audit["preserveAllOccurrences"]:raise RuntimeError("Broad preservation requires review before analysis")
        budget = (3600, 10_800) if args.full_build else (600, 1800)
        # Analysis runs keep the 64 MiB write cap; a full build has to emit a large object file.
        file_cap = 8 * 1024**3 if args.full_build else 64 * 1024**2
        result["fileSizeLimitBytes"]=file_cap
        if args.full_build:
            result["sdkRoot"]=str(sdk_root)
        built=execute(["/usr/bin/time","-l",*cmd],output/"analysis",work,timeout=budget[0],
                      cpu_seconds=budget[1],file_size_bytes=file_cap,
                      extra_env={"SDKROOT":str(sdk_root)} if args.full_build else None)
        result["analysisExitCode"]=built["exitCode"]
        result["timedOut"]=built["timedOut"]
        result["childCPUSeconds"]=built["childCPUSeconds"]
        result["outputLimitExceeded"]=built["outputLimitExceeded"]
        result["wallSeconds"]=built["finishedUnix"]-built["startedUnix"]
        result["maximumResidentSetBytes"]=parse_time_rss((output/"analysis/stderr.log").read_text())
        result["analysisStatistics"]=read_analysis_statistics(work)
        result["buildOutputJSONPresent"]=(work/"build-output.json").exists()
        logs=sorted(work.glob("gc.log*"),key=lambda p:p.stat().st_mtime_ns)
        result["gcSummary"]=summarize_gc_logs("\n".join(p.read_text(errors="replace") for p in logs))
        result["analysisCompleted"]=bool(built["exitCode"]==0 and not built["timedOut"]
            and result["analysisStatistics"] and not built["outputLimitExceeded"])
        if args.full_build:
            # A full build may legitimately fail after analysis; record whatever it emitted.
            produced=[p for p in work.glob("client-graph*") if p.is_file()]
            if args.relocatable:
                produced += [p for p in (work/"native-tmp").rglob("client-graph.o") if p.is_file()]
            result["imageArtifacts"]=[{"path":str(p),"bytes":p.stat().st_size,"sha256":sha256(p)}
                                      for p in produced] or None
            if args.relocatable:
                objects=[p for p in (work/"native-tmp").rglob("client-graph.o") if p.is_file()]
                if objects:
                    obj=objects[0]
                    if built['exitCode']==0:result['targetCodeGeneration']='RELOCATABLE_OBJECT'
                    load=subprocess.run(["/usr/bin/otool","-l",str(obj)],capture_output=True,text=True).stdout
                    platform=[line.strip() for line in load.splitlines() if "platform" in line.lower()][:4]
                    result["imageObject"]={"path":str(obj),"bytes":obj.stat().st_size,"sha256":sha256(obj),
                                           "platformLoadCommand":platform or ["none"],
                                           "note":"linked separately for arm64-apple-ios; see tools/link_c0_ios.py"}
        result["status"]="ANALYZED" if result["analysisCompleted"] else "BLOCKED"
    except Exception as error:result["error"]=str(error)
    result["filesSHA256"]={str(p.relative_to(output)):sha256(p) for p in output.rglob("*") if p.is_file() and not p.is_symlink() and p.name!="result.json"}
    (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ['filesSHA256','classpathSHA256']},indent=2))
    return 0 if result["status"]=="ANALYZED" else 2


if __name__=="__main__":raise SystemExit(main())
