#!/usr/bin/env python3
"""Build the UIKit/CAMetalLayer GLFW subset for iOS; optionally run the C state fixture."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
from bootstrap_toolchain import sha256
from capture import ROOT, capture
from graphics_common import register_tree
from glfw_runtime_contract import validate_glfw_renderer
from inventory_client_native_calls import glfw_symbols

# Mod polling is absent from the vanilla client call inventory. These functions
# are required by malilib's per-tick key recheck as well as direct game input.
INPUT_POLL_EXPORTS = frozenset({
    "glfwGetMouseButton", "glfwGetKey", "glfwGetCursorPos",
})

# Generated evidence is not part of a packaged source tree, so the caller
# (workbench or CLI) supplies either the client JAR or an inventory that was
# produced from it.
DEFAULT_INVENTORY = ROOT / "artifacts/evidence/client-native-call-inventory.json"


def load_inventory(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            "client native call inventory missing: " + str(path) +
            "; pass --client-inventory with the inventory generated for this client")
    return json.loads(path.read_text())

def validate_input_exports(symbols: set[str]) -> None:
    missing = INPUT_POLL_EXPORTS - symbols
    if missing:
        raise ValueError("GLFW input polling exports missing; rebuild GLFW: " + ", ".join(sorted(missing)))

def exported_symbols(text: str) -> set[str]:
    return {line.split()[-1].removeprefix("_") for line in text.splitlines() if line.split()}

def required_symbols(inventory: dict) -> set[str]:
    # Java structure accessors and Callback.free are NOT C exports. Their ABI is in lwjgl core.
    return set(INPUT_POLL_EXPORTS) | {m["name"] for m in inventory["methods"] if m["owner"] in
            ("org/lwjgl/glfw/GLFW","org/lwjgl/glfw/GLFWNativeCocoa") and m["name"].startswith("glfw")}


def required_symbols_for_client(client: Path) -> set[str]:
    client = Path(client)
    if not client.is_file():
        raise FileNotFoundError("client JAR missing: " + str(client))
    return set(INPUT_POLL_EXPORTS) | glfw_symbols(client)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--sdk",choices=("iphoneos","iphonesimulator"),default="iphonesimulator")
    parser.add_argument("--client",type=Path,help="client JAR the GLFW subset must satisfy")
    parser.add_argument("--client-inventory",type=Path,
                        help="client-native-call-inventory.json generated from the client being built")
    parser.add_argument("--test-host",action="store_true")
    args=parser.parse_args(argv)
    if args.client:
        client=Path(args.client).resolve()
        required=required_symbols_for_client(client)
        inputs={"client":str(client),"clientSHA256":sha256(client)}
    else:
        inventory_path=Path(args.client_inventory or DEFAULT_INVENTORY).resolve()
        required=required_symbols(load_inventory(inventory_path))
        inputs={"clientInventory":str(inventory_path),"clientInventorySHA256":sha256(inventory_path)}
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    source=ROOT/"ios/glfw-lite"
    target="arm64-apple-ios17.0"+("-simulator" if args.sdk=="iphonesimulator" else "")
    binary=output/"libglfw.dylib"
    cmd=["xcrun","--sdk",args.sdk,"clang","-target",target,"-std=c11","-fobjc-arc","-O2",
         "-Wall","-Wextra","-Werror","-Wno-deprecated-declarations","-dynamiclib",
         str(source/"glfw_lite.c"),str(source/"uikit_surface.m"),str(source/"osmesa_gl.c"),"-framework","UIKit","-framework","Foundation",
         "-framework","QuartzCore","-framework","CoreGraphics","-framework","Metal","-framework","GameController","-install_name","@rpath/libglfw.dylib","-o",str(binary)]
    result={"status":"BLOCKED","gateC0":"BLOCKED","target":target,
            "scope":"GLFW native subset only; no Java bridge or Minecraft renderer acceptance",
            **inputs,
            "sourcesSHA256":{str(p.relative_to(ROOT)):sha256(p) for p in source.iterdir() if p.is_file()}}
    build=capture(cmd,output/"compile",180);result["compile"]=build
    if build["exitCode"]==0:
        symbols=subprocess.check_output(["xcrun","nm","-gUj",str(binary)],text=True)
        (output/"exports.txt").write_text(symbols)
        result["requiredCExports"]=sorted(required)
        result["missingCExports"]=sorted(required-exported_symbols(symbols))
        platform=subprocess.check_output(["xcrun","vtool","-show-build",str(binary)],text=True)
        (output/"platform.txt").write_text(platform)
        expected="IOSSIMULATOR" if args.sdk=="iphonesimulator" else "IOS"
        if f"platform {expected}\n" in platform and not result["missingCExports"]:
            result['rendererABI'] = validate_glfw_renderer(binary, 'gl41')
            result['supportedClientAPIs'] = ['NO_API', 'OPENGL_OSMESA']
            result["status"]="NATIVE_SUBSET_BUILT"
        result["binarySHA256"]=sha256(binary)
    if args.test_host:
        fixture=output/"glfw-state-test"
        host=capture(["xcrun","clang","-std=c11","-Wall","-Wextra","-Werror","-g","-fsanitize=address,undefined",
                      "-I",str(source),str(source/"glfw_lite.c"),str(source/"osmesa_gl.c"),
                      str(source/"osmesa_present_host_stub.c"),str(ROOT/"interop/graphics/glfw_state_test.c"),
                      "-o",str(fixture)],output/"fixture-compile",120)
        result["fixtureCompile"]=host
        if host["exitCode"]==0:
            tested=capture([str(fixture)],output/"fixture-run",30);result["fixtureRun"]=tested
            result["hostStateFixture"]="PASS" if tested["exitCode"]==0 and "GLFW_STATE_PASS" in (output/"fixture-run/stdout.log").read_text() else "FAIL"
        else: result["hostStateFixture"]="FAIL"
    (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    command=[sys.executable,"-B",str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)]
    try: register_tree(output,command)
    except (OSError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr);return 1
    print(json.dumps({k:v for k,v in result.items() if k not in ("compile","fixtureCompile","fixtureRun")},indent=2))
    return 0 if result["status"]=="NATIVE_SUBSET_BUILT" and result.get("hostStateFixture")!="FAIL" else 2

if __name__=="__main__":raise SystemExit(main())
