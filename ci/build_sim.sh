#!/usr/bin/env bash
# Build and run the FabricAOT client in the iOS Simulator on the CI Mac.
# Same pipeline as build_mac.sh up to the AOT image; the image is then linked for
# the simulator, wrapped in the WorldSimulator app and launched with simctl.
set -euo pipefail

WORK="${WORK:-$HOME/mcfao-sim}"
CI_REPO="${CI_REPO:-https://github.com/zhangrongxue/mc-aot-ios}"
UPSTREAM="${UPSTREAM:-https://github.com/AOTFASTLNX/MCFAO}"
SOURCE_REF="${SOURCE_REF:-}"
HEAP_GIB="${HEAP_GIB:-8}"
JOBS="${JOBS:-6}"
AOT_PAR="${AOT_PAR:-4}"

log() { printf '\n=== [%s] %s ===\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

mkdir -p "$WORK"
cd "$WORK"
exec > >(tee -a build.log) 2>&1
log "host: $(uname -m) $(sysctl -n hw.memsize | awk '{printf "%.0f GiB", $1/1073741824}')"

if [ ! -d repo/.git ]; then git clone --depth 1 "$CI_REPO" repo; fi
if [ ! -d src/.git ]; then
  if [ -n "$SOURCE_REF" ]; then
    git clone --depth 1 --branch "$SOURCE_REF" "$UPSTREAM" src
  else
    git clone --depth 1 "https://x-access-token:${MCFAO_TOKEN}@${UPSTREAM#https://}" src
  fi
fi
cd repo && git pull --ff-only -q || true
cd "$WORK"
python3 "$WORK/repo/ci/patch_src.py" src
mkdir -p .ci/bin
printf '#!/bin/sh\necho "{}"\n' > .ci/bin/aar
chmod +x .ci/bin/aar
export PATH="$WORK/.ci/bin:$PATH"

XC=$(ls -d /Applications/Xcode*.app 2>/dev/null | sort -V | tail -1)
[ -n "$XC" ] || die "no Xcode"
if [ ! -e /Applications/Xcode.app ]; then sudo -n ln -sfn "$XC" /Applications/Xcode.app 2>/dev/null || true; fi
sudo -n xcode-select -s "$XC" 2>/dev/null || true
log "xcode: $XC"

need=()
command -v autoconf >/dev/null || need+=(autoconf)
command -v automake >/dev/null || need+=(automake)
command -v cmake >/dev/null || need+=(cmake)
command -v make >/dev/null || need+=(make)
if [ ${#need[@]} -gt 0 ]; then brew install -q "${need[@]}"; fi
if [ -d /opt/homebrew/opt/make/libexec/gnubin ]; then export PATH="/opt/homebrew/opt/make/libexec/gnubin:$PATH"; fi

cd "$WORK/src"
log "toolchain"
python3 -B tools/bootstrap_toolchain.py
python3 -B tools/fetch_upstream.py
GRAAL=$(ls -d "$PWD"/.cache/toolchains/graalvm-25.0.2/*/Contents/Home)
export GRAALVM_HOME="$GRAAL"

log "OpenJDK headers"
JDK=$(python3 -c "import json;print(json.load(open('.cache/upstream/jdk.json'))['path'])")
mkdir -p artifacts/ci
pushd "$JDK" >/dev/null
bash configure --with-conf-name=fabricaot-host --with-boot-jdk="$GRAAL" \
  --with-debug-level=release --with-native-debug-symbols=none --disable-warnings-as-errors \
  --with-num-cores="$JOBS" --with-memory-size=4096 >/dev/null 2>"$WORK/configure.err" \
  || { tail -20 "$WORK/configure.err"; die "configure failed"; }
make CONF=fabricaot-host JOBS="$JOBS" java.base-java >/dev/null 2>"$WORK/make.err" \
  || { tail -20 "$WORK/make.err"; die "java.base-java failed"; }
popd >/dev/null

log "MC inputs / B0 / splitter / assets"
time python3 -B "$WORK/repo/ci/fetch_minecraft.py" --out artifacts/ci/mc --src-root .
export MCFAO_A0="$PWD/artifacts/ci/mc/a0"
time python3 -B tools/prepare_b0.py --graalvm-home "$GRAALVM_HOME" --output artifacts/b0/prepared-04
python3 -B tools/build_method_splitter.py --output artifacts/compiler/method-splitter-01 --fetch-missing
mkdir -p artifacts/ci/empty-assets
time python3 -B tools/stage_game_assets.py --source artifacts/ci/empty-assets \
  --version-metadata artifacts/ci/mc/26.1.2.json --output artifacts/graphics/game-assets-01 --fetch-missing

log "runtime (device variant is fine for the AOT object)"
time python3 -B tools/build_ios_runtime.py --sdk iphoneos --with-extnet \
  --graalvm-home "$GRAALVM_HOME" --output artifacts/b1/runtime-ios

log "graphics for the simulator"
python3 -B tools/fetch_stb.py
time python3 -B tools/build_glfw_lite.py --sdk iphonesimulator --output artifacts/sim/glfw
time python3 -B tools/build_lwjgl_lite.py --sdk iphonesimulator \
  --glfw-library artifacts/sim/glfw/libglfw.dylib --output artifacts/sim/lwjgl
time python3 -B tools/prepare_shader_toolchain.py --output artifacts/graphics/shader-toolchain-03
time python3 -B tools/collect_shader_catalog.py --output artifacts/graphics/shader-catalog-03
time python3 -B tools/build_metal_backend.py --sdk iphonesimulator \
  --graphics-bridge artifacts/sim/lwjgl --glfw-library artifacts/sim/glfw/libglfw.dylib \
  --output artifacts/sim/metal
time python3 -B tools/build_openal_soft.py --sdk iphonesimulator --output artifacts/sim/openal
time python3 -B tools/translate_shaders.py --sdk iphonesimulator \
  --catalog artifacts/graphics/shader-catalog-03 --toolchain artifacts/graphics/shader-toolchain-03 \
  --output artifacts/sim/shaders

log "split + inject + AOT"
python3 - <<'PY' > /tmp/cp.txt
import json
prepared = json.load(open("artifacts/b0/prepared-04/result.json", encoding="utf-8"))
print(":".join(row["path"] for row in prepared["referenceLibraries"]))
PY
time python3 -B tools/split_methods.py --jar artifacts/ci/mc/meta/versions/26.1.2/26.1.2.jar \
  --output-jar artifacts/ci/client-split.jar --report artifacts/ci/split-report.json \
  --tool artifacts/compiler/method-splitter-01 --min-sites 200 --target-sites 64 \
  --max-parts 64 --trigger-cost 50000 --classpath-file /tmp/cp.txt
time python3 -B tools/inject_metal_backend.py --client artifacts/ci/client-split.jar \
  --output artifacts/ci/injected --graalvm-home "$GRAALVM_HOME" \
  --asm-jars .cache/libs/asm-9.9/asm-9.9.jar .cache/libs/asm-9.9/asm-tree-9.9.jar
time python3 -B tools/run_a1_probe.py --graalvm-home "$GRAALVM_HOME" --output artifacts/ci/a1 --mode ios-relocatable || true
time python3 -B tools/probe_client_graph.py \
  --prepared artifacts/b0/prepared-04 --runtime artifacts/b1/runtime-ios --caps artifacts/ci/a1/caps \
  --b1-evidence artifacts/evidence/b1-user-device-run-01/result.json \
  --client-jar artifacts/ci/injected/client-26.1.2-metal.jar \
  --graphics-bridge artifacts/sim/lwjgl --metal-bootstrap artifacts/sim/metal \
  --full-build --relocatable --include-game-resources --heap-gib "$HEAP_GIB" --parallelism "$AOT_PAR" \
  --output artifacts/ci/aot

log "diagnostic: EnvironmentAttributes members in the split jar"
python3 "$WORK/repo/ci/classdump.py" artifacts/ci/client-split.jar EnvironmentAttributes --methods | grep -E 'class |init|part|methods=' | head -25 || true
log "diagnostic: same class in the injected jar"
python3 "$WORK/repo/ci/classdump.py" artifacts/ci/injected/client-26.1.2-metal.jar EnvironmentAttributes --methods | grep -E 'class |init|part|methods=' | head -25 || true
log "link for the simulator"
OBJ=$(python3 -c "import json;print(json.load(open('artifacts/ci/aot/result.json'))['imageObject']['path'])")
time python3 -B tools/build_ios_runtime.py --sdk iphonesimulator --with-extnet \
  --graalvm-home "$GRAALVM_HOME" --aot-object "$OBJ" --output artifacts/sim/runtime
time python3 -B tools/link_c0_ios.py --sdk iphonesimulator --image artifacts/ci/aot \
  --runtime artifacts/sim/runtime --stub-unsupported-jni --output artifacts/sim/link

log "stage + xcodebuild (WorldSimulator)"
STAGED="$WORK/staged"
rm -rf "$STAGED" && mkdir -p "$STAGED"
cp artifacts/sim/link/client-graph.dylib "$STAGED/"
for lib in libglfw liblwjgl libfaot_metal libopenal; do
  f=$(ls artifacts/sim/*/${lib}.dylib 2>/dev/null | head -1)
  [ -n "$f" ] && cp "$f" "$STAGED/"
done
METALLIB=$(find artifacts/sim/metal -name 'fabricaot-present.metallib' | head -1)
[ -n "$METALLIB" ] || die "metallib missing"
cp "$METALLIB" "$STAGED/fabricaot-present.metallib"
SHADER_INDEX=$(find artifacts/sim/shaders -name 'index.json' | head -1)
[ -n "$SHADER_INDEX" ] || die "shader bundle missing"
cp -R "$(dirname "$SHADER_INDEX")" "$STAGED/fabricaot-shaders"
[ -f "$STAGED/fabricaot-shaders/index.json" ] || die "shader bundle layout unexpected"
log "staged: $(ls "$STAGED" | tr '\n' ' ')"
log "shader entries: $(ls "$STAGED/fabricaot-shaders" | wc -l)"

DERIVED="$WORK/DerivedData"
xcodebuild -project ios/C0Harness/C0Harness.xcodeproj -scheme WorldSimulator \
  -configuration "World Simulator" -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$DERIVED" \
  FAOT_GRAPHICS_NATIVE_DIR="$STAGED" FAOT_CLIENT_LIBRARY="$STAGED/client-graph.dylib" \
  build | tail -15
APP=$(find "$DERIVED/Build/Products" -maxdepth 2 -name '*.app' | head -1)
[ -n "$APP" ] || die "no simulator app"
log "app: $APP"

log "simulator run"
UDID=$(python3 - <<'PY'
import json, subprocess, sys

def simctl(*args):
    return subprocess.run(["xcrun", "simctl", *args], capture_output=True, text=True).stdout

runtimes = json.loads(simctl("list", "runtimes", "-j"))["runtimes"]
usable = [r for r in runtimes if r.get("isAvailable") and "iOS" in r.get("identifier", "")]
print("# runtimes:", [r["identifier"] for r in usable], file=sys.stderr)
if not usable:
    sys.exit(0)
devices = json.loads(simctl("list", "devices", "-j"))["devices"]
for candidate_runtime in reversed(usable):
    identifier = candidate_runtime["identifier"]
    for device in devices.get(identifier, []):
        name = device.get("name", "")
        if device.get("isAvailable") and "iPhone" in name and "Duo" not in name:
            print(device["udid"], end="")
            sys.exit(0)
runtime = usable[-1]["identifier"]

import re
supported = [d.get("identifier") for d in (usable[0].get("supportedDeviceTypes") or [])
             if "iPhone" in d.get("name", "") and "Duo" not in d.get("name", "")]
if not supported:
    types = json.loads(simctl("list", "devicetypes", "-j"))["devicetypes"]
    supported = [d["identifier"] for d in types
                 if "iPhone" in d.get("name", "") and "Duo" not in d.get("name", "")]
print("# device types:", supported[:5], file=sys.stderr)
for identifier in supported:
    created = simctl("create", "mcfao-sim", identifier, runtime).strip()
    if re.fullmatch(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", created):
        print(created, end="")
        sys.exit(0)
    print("# create failed for", identifier, "->", created, file=sys.stderr)
PY
)
[ -n "$UDID" ] || die "no usable simulator"
log "simulator $UDID"
xcrun simctl bootstatus "$UDID" -b || log "boot status did not report ready; continuing"
for i in $(seq 1 60); do
  if xcrun simctl list devices | grep "$UDID" | grep -q "Booted"; then
    log "simulator is Booted"
    break
  fi
  sleep 3
done
xcrun simctl list devices | grep "$UDID" || true
log "installing the app"
set +e
INSTALL_OUT=$(xcrun simctl install "$UDID" "$APP" 2>&1)
INSTALL_RC=$?
set -e
log "install rc=$INSTALL_RC: $INSTALL_OUT"
[ "$INSTALL_RC" -eq 0 ] || die "simctl install failed"
BUNDLE=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Info.plist")
log "bundle id: $BUNDLE"
DATA=""
for i in $(seq 1 20); do
  set +e
  DATA=$(xcrun simctl get_app_container "$UDID" "$BUNDLE" data 2>&1)
  RC=$?
  set -e
  if [ "$RC" -eq 0 ] && [ -d "$DATA" ]; then break; fi
  log "get_app_container rc=$RC: $DATA"
  DATA=""
  sleep 2
done
[ -n "$DATA" ] || die "cannot locate the installed app container"
log "data container: $DATA"
log "seeding the app container"
mkdir -p "$DATA/Documents"
if [ ! -d "$DATA/Documents/assets" ]; then
  log "copying assets ($(du -sh artifacts/graphics/game-assets-01/assets | cut -f1))"
  cp -R artifacts/graphics/game-assets-01/assets "$DATA/Documents/assets" || die "asset copy failed"
fi
log "assets in place: $(du -sh "$DATA/Documents/assets" 2>/dev/null | cut -f1)"
mkdir -p "$DATA/Documents/game"
printf 'renderDistance:8\nsimulationDistance:5\nmaxFps:30\n' > "$DATA/Documents/game/options.txt"
log "options written"
mkdir -p "$DATA/Documents/c0-logs"
BEFORE=$(ls "$DATA/Documents/c0-logs" 2>/dev/null | wc -l || true)
xcrun simctl launch "$UDID" "$BUNDLE" || true
for i in $(seq 1 100); do
  sleep 3
  NOW=$(ls "$DATA/Documents/c0-logs" 2>/dev/null | wc -l || true)
  if [ "$NOW" -gt "$BEFORE" ]; then break; fi
done
log "waiting for the client to finish loading"
sleep 45
xcrun simctl io "$UDID" screenshot "$WORK/sim-45s.png" || true
sleep 60
xcrun simctl io "$UDID" screenshot "$WORK/sim-105s.png" || true
sleep 60
xcrun simctl io "$UDID" screenshot "$WORK/sim-165s.png" || true
for shot in "$WORK"/sim*.png; do
  [ -f "$shot" ] && sips -s format jpeg -s formatOptions 65 "$shot" --out "${shot%.png}.jpg" >/dev/null 2>&1 || true
done
log "opening the Simulator UI to click Singleplayer"
open -a Simulator --args -CurrentDeviceUDID "$UDID" || true
sleep 12
osascript <<'APPLESCRIPT' || log "osascript click failed"
tell application "System Events"
  tell process "Simulator"
    set frontmost to true
    set {wx, wy} to position of window 1
    set {ww, wh} to size of window 1
    set clickX to wx + (ww / 2)
    set clickY to wy + 28 + ((wh - 28) * 0.365)
    click at {clickX, clickY}
    return "clicked at " & clickX & "," & clickY & " window " & wx & "," & wy & " size " & ww & "x" & wh
  end tell
end tell
APPLESCRIPT
sleep 10
xcrun simctl io "$UDID" screenshot "$WORK/sim-click1.png" || true
sips -s format jpeg -s formatOptions 65 "$WORK/sim-click1.png" --out "$WORK/sim-click1.jpg" >/dev/null 2>&1 || true
cp "$DATA/Documents/game/logs/latest.log" "$WORK/latest.log" 2>/dev/null || true
ls -la "$WORK"/*.jpg 2>/dev/null || true
NEWEST=$(ls -t "$DATA/Documents/c0-logs"/*.log 2>/dev/null | head -1 || true)
if [ -n "${NEWEST:-}" ]; then
  log "c0 log: $(basename "$NEWEST")"
  tail -120 "$NEWEST"
else
  log "no c0 log appeared"
fi
if [ -f "$DATA/Documents/game/logs/latest.log" ]; then
  log "minecraft latest.log tail"
  tail -80 "$DATA/Documents/game/logs/latest.log"
fi
xcrun simctl io "$UDID" screenshot "$WORK/sim.png" || true
cp -R "$DATA/Documents/c0-logs" "$WORK/c0-logs" 2>/dev/null || true
