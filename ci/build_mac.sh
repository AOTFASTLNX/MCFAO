#!/usr/bin/env bash
# One-shot build of the FabricAOT (Minecraft 26.1.2) iOS game IPA on an arm64 Mac.
#
#   SOURCE_REF=integration/aot-and-performance-20261113 bash build_mac.sh
#
# Requirements: Apple silicon macOS with Xcode 16+ and >= 16 GiB RAM.
# Produces: $WORK/FabricAOT-game.ipa (unsigned), $WORK/build.log
set -euo pipefail

WORK="${WORK:-$HOME/mcfao-build}"
CI_REPO="${CI_REPO:-https://github.com/AOTFASTLNX/MCFAO}"
UPSTREAM="${UPSTREAM:-https://github.com/AOTFASTLNX/MCFAO}"
SOURCE_REF="${SOURCE_REF:-integration/aot-and-performance-20261113}"
SOURCE_SHA="${SOURCE_SHA:-}" # CircleCI sets this to the triggering commit
HEAP_GIB="${HEAP_GIB:-8}"
JOBS="${JOBS:-4}"
AOT_PAR="${AOT_PAR:-4}"

log() { printf '\n=== [%s] %s ===\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

[ "$(uname -m)" = "arm64" ] || die "this must run on Apple silicon"
MEM=$(( $(sysctl -n hw.memsize) / 1073741824 ))
[ "$MEM" -ge 15 ] || die "need >=16 GiB RAM, this machine has ${MEM} GiB"
xcodebuild -version >/dev/null || die "Xcode command line tools missing"

mkdir -p "$WORK"
cd "$WORK"
exec > >(tee -a build.log) 2>&1
log "host: $(uname -m) ${MEM} GiB, $(xcodebuild -version | head -1), workdir $WORK"

# ---------------------------------------------------------------- sources
log "fetch sources (public, commit-pinned; no token)"
if [ ! -d repo/.git ]; then
  git clone --depth 1 --branch "$SOURCE_REF" "$CI_REPO" repo
fi
if [ ! -d src/.git ]; then
  git clone --depth 1 --branch "$SOURCE_REF" "$UPSTREAM" src
fi
REPO_HEAD="$(git -C repo rev-parse HEAD)"
SRC_HEAD="$(git -C src rev-parse HEAD)"
if [ -n "$SOURCE_SHA" ] && [ "$SRC_HEAD" != "$SOURCE_SHA" ]; then
  die "source branch moved during CI: actual $SRC_HEAD, requested $SOURCE_SHA"
fi
if [ -n "$SOURCE_SHA" ] && [ "$REPO_HEAD" != "$SOURCE_SHA" ]; then
  die "CI helper sources do not match build source SHA ($REPO_HEAD != $SOURCE_SHA)"
fi
log "pinned source commit: $SRC_HEAD"
python3 "$WORK/repo/ci/patch_src.py" src
# All source changes are CI portability patches, never pushed upstream.
git -C src diff --stat

mkdir -p .ci/bin
printf '#!/bin/sh\necho "{}"\n' > .ci/bin/aar
chmod +x .ci/bin/aar
export PATH="$WORK/.ci/bin:$PATH"

# some tools spawn an absolute /Applications/Xcode.app
XC=$(ls -d /Applications/Xcode*.app 2>/dev/null | sort -V | tail -1 || true)
[ -n "$XC" ] || die "no Xcode found in /Applications"
if [ ! -e /Applications/Xcode.app ]; then
  sudo -n ln -sfn "$XC" /Applications/Xcode.app 2>/dev/null || echo "warn: cannot link /Applications/Xcode.app"
fi
sudo -n xcode-select -s "$XC" 2>/dev/null || true
log "xcode: $XC ($(xcode-select -p))"

# ---------------------------------------------------------------- host tools
log "host tools"
need_brew=()
command -v autoconf >/dev/null || need_brew+=(autoconf)
command -v automake >/dev/null || need_brew+=(automake)
command -v cmake    >/dev/null || need_brew+=(cmake)
command -v make     >/dev/null || need_brew+=(make)
if [ ${#need_brew[@]} -gt 0 ]; then
  command -v brew >/dev/null || die "Homebrew missing and needed for: ${need_brew[*]}"
  brew install -q "${need_brew[@]}"
fi
command -v zip >/dev/null || die "zip missing"
if [ -d /opt/homebrew/opt/make/libexec/gnubin ]; then
  export PATH="/opt/homebrew/opt/make/libexec/gnubin:$PATH"
fi

# ---------------------------------------------------------------- stage 1
log "stage 1: GraalVM + upstream sources"
cd "$WORK/src"
time python3 -B tools/bootstrap_toolchain.py
time python3 -B tools/fetch_upstream.py
GRAAL=$(ls -d "$PWD"/.cache/toolchains/graalvm-25.0.2/*/Contents/Home)
export GRAALVM_HOME="$GRAAL"
"$GRAAL/bin/native-image" --version

# ---------------------------------------------------------------- stage 2
log "stage 2a: OpenJDK configure + java.base-java (slow, 10-25 min)"
JDK=$(python3 -c "import json;print(json.load(open('.cache/upstream/jdk.json'))['path'])")
mkdir -p artifacts/ci
pushd "$JDK" >/dev/null
bash configure --with-conf-name=fabricaot-host --with-boot-jdk="$GRAAL" \
  --with-debug-level=release --with-native-debug-symbols=none --disable-warnings-as-errors \
  --with-num-cores="$JOBS" --with-memory-size=4096 >/dev/null 2>"$WORK/configure.err" \
  || { tail -25 "$WORK/configure.err"; die "configure failed"; }
make CONF=fabricaot-host JOBS="$JOBS" java.base-java >/dev/null 2>"$WORK/make.err" \
  || { tail -25 "$WORK/make.err"; die "java.base-java failed"; }
popd >/dev/null
ls "$JDK/build/fabricaot-host/support/headers/java.base" >/dev/null || die "JNI headers missing"

log "stage 2b: iOS bootstrap runtime"
time python3 -B tools/build_ios_runtime.py --sdk iphoneos --with-extnet \
  --graalvm-home "$GRAALVM_HOME" --output artifacts/b1/runtime-ios

log "stage 2c: Minecraft 26.1.2 inputs (Mojang CDN)"
time python3 -B "$WORK/repo/ci/fetch_minecraft.py" --out artifacts/ci/mc --src-root .
export MCFAO_A0="$PWD/artifacts/ci/mc/a0"

log "stage 2d: B0 prepared reference"
time python3 -B tools/prepare_b0.py --graalvm-home "$GRAALVM_HOME" --output artifacts/b0/prepared-04

log "stage 2e: method splitter + game assets"
python3 -B tools/build_method_splitter.py --output artifacts/compiler/method-splitter-01 --fetch-missing
mkdir -p artifacts/ci/empty-assets
time python3 -B tools/stage_game_assets.py --source artifacts/ci/empty-assets \
  --version-metadata artifacts/ci/mc/26.1.2.json \
  --output artifacts/graphics/game-assets-01 --fetch-missing

# ---------------------------------------------------------------- stage 3
log "stage 3a: GLFW-lite"
time python3 -B tools/build_glfw_lite.py --sdk iphoneos --output artifacts/graphics/glfw-ios-world-01 --test-host
log "stage 3b: STB + ASM"
python3 -B tools/fetch_stb.py
python3 -B tools/build_method_splitter.py --output artifacts/ci/splitter-bootstrap --fetch-missing
log "stage 3c: LWJGL-lite"
time python3 -B tools/build_lwjgl_lite.py --sdk iphoneos \
  --glfw-library artifacts/graphics/glfw-ios-world-01/libglfw.dylib \
  --output artifacts/graphics/lwjgl-ios-world-01
log "stage 3d: shader toolchain + catalog"
time python3 -B tools/prepare_shader_toolchain.py --output artifacts/graphics/shader-toolchain-03
time python3 -B tools/collect_shader_catalog.py --output artifacts/graphics/shader-catalog-03
log "stage 3e: Metal backend + OpenAL Soft"
time python3 -B tools/build_metal_backend.py --sdk iphoneos \
  --graphics-bridge artifacts/graphics/lwjgl-ios-world-01 \
  --glfw-library artifacts/graphics/glfw-ios-world-01/libglfw.dylib \
  --output artifacts/graphics/metal-ios-world-03
time python3 -B tools/build_openal_soft.py --sdk iphoneos --output artifacts/graphics/openal-ios-world-01
log "stage 3f: translate vanilla shaders"
time python3 -B tools/translate_shaders.py --sdk iphoneos \
  --catalog artifacts/graphics/shader-catalog-03 \
  --toolchain artifacts/graphics/shader-toolchain-03 \
  --output artifacts/graphics/shaders-ios-world-01

# ---------------------------------------------------------------- stage 4
log "stage 4a: split methods"
python3 - <<'PY' > /tmp/cp.txt
import json
prepared = json.load(open("artifacts/b0/prepared-04/result.json", encoding="utf-8"))
print(":".join(row["path"] for row in prepared["referenceLibraries"]))
PY
time python3 -B tools/split_methods.py \
  --jar artifacts/ci/mc/meta/versions/26.1.2/26.1.2.jar \
  --output-jar artifacts/ci/client-split.jar \
  --report artifacts/ci/split-report.json \
  --tool artifacts/compiler/method-splitter-01 \
  --min-sites 200 --target-sites 64 --max-parts 64 --trigger-cost 50000 \
  --classpath-file /tmp/cp.txt

DUMP="$WORK/repo/ci/classdump.py"
if [ -f "$DUMP" ]; then
  log "diagnostic: EnvironmentAttributes field flags"
  python3 "$DUMP" artifacts/ci/mc/meta/versions/26.1.2/26.1.2.jar EnvironmentAttributes || true
  python3 "$DUMP" artifacts/ci/client-split.jar EnvironmentAttributes || true
  python3 "$DUMP" artifacts/ci/injected/client-26.1.2-metal.jar EnvironmentAttributes || true
fi
VERIFY="$WORK/repo/ci/VerifyClasses.java"
if [ -f "$VERIFY" ]; then
  log "verify: load every class in the split jar with the real JVM"
  CP=$(cat /tmp/cp.txt)
  if [ ! -f "$WORK/verify-classes" ]; then
    "$GRAALVM_HOME/bin/javac" -d "$WORK/verify" "$VERIFY"
    cp -R "$WORK/verify" "$WORK/verify-classes" 2>/dev/null || true
  fi
  "$GRAALVM_HOME/bin/java" -cp "$WORK/verify" VerifyClasses artifacts/ci/client-split.jar $CP || \
    log "WARNING: class verification reported problems (see above)"
fi
log "stage 4b: inject Metal backend"
time python3 -B tools/inject_metal_backend.py --client artifacts/ci/client-split.jar \
  --output artifacts/ci/injected --graalvm-home "$GRAALVM_HOME" \
  --asm-jars .cache/libs/asm-9.9/asm-9.9.jar .cache/libs/asm-9.9/asm-tree-9.9.jar

log "stage 4c: A1 probe for the CAP cache"
time python3 -B tools/run_a1_probe.py --graalvm-home "$GRAALVM_HOME" \
  --output artifacts/ci/a1 --mode ios-relocatable || true

log "stage 4d: customer client AOT (heap ${HEAP_GIB} GiB) -- the long one"
time python3 -B tools/probe_client_graph.py \
  --prepared artifacts/b0/prepared-04 \
  --runtime artifacts/b1/runtime-ios \
  --caps artifacts/ci/a1/caps \
  --b1-evidence artifacts/evidence/b1-user-device-run-01/result.json \
  --client-jar artifacts/ci/injected/client-26.1.2-metal.jar \
  --graphics-bridge artifacts/graphics/lwjgl-ios-world-01 \
  --metal-bootstrap artifacts/graphics/metal-ios-world-03 \
  --full-build --relocatable --include-game-resources \
  --heap-gib "$HEAP_GIB" --parallelism "$AOT_PAR" \
  --output artifacts/ci/aot
python3 -c "import json;d=json.load(open('artifacts/ci/aot/result.json'));print(d['status'],d.get('imageObject',{}).get('bytes'))"

log "stage 4e: device runtime + link"
OBJ=$(python3 -c "import json;print(json.load(open('artifacts/ci/aot/result.json'))['imageObject']['path'])")
time python3 -B tools/build_ios_runtime.py --sdk iphoneos --with-extnet \
  --graalvm-home "$GRAALVM_HOME" --aot-object "$OBJ" \
  --output artifacts/graphics/runtime-ios-world-02
time python3 -B tools/link_c0_ios.py --sdk iphoneos --image artifacts/ci/aot \
  --runtime artifacts/graphics/runtime-ios-world-02 --stub-unsupported-jni \
  --output artifacts/graphics/main-link-ios-world-01
ls -la artifacts/graphics/main-link-ios-world-01/client-graph.dylib

log "stage 4f: stage WorldDevice inputs"
python3 -B tools/stage_device_xcode.py \
  --client artifacts/graphics/main-link-ios-world-01 \
  --glfw artifacts/graphics/glfw-ios-world-01 \
  --lwjgl artifacts/graphics/lwjgl-ios-world-01 \
  --metal artifacts/graphics/metal-ios-world-03 \
  --openal artifacts/graphics/openal-ios-world-01 \
  --shaders artifacts/graphics/shaders-ios-world-01 \
  --output artifacts/graphics/world-device-input-02

log "stage 4g: xcodebuild + IPA"
G=artifacts/graphics
xcodebuild -project ios/C0Harness/C0Harness.xcodeproj -scheme WorldDevice \
  -configuration "World Device" \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$G/world-device-01/DerivedData" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  FAOT_GRAPHICS_NATIVE_DIR="$PWD/$G/world-device-input-02" \
  FAOT_CLIENT_LIBRARY="$PWD/$G/world-device-input-02/client-graph.dylib" \
  FAOT_GAME_ASSETS_DIR="$PWD/$G/game-assets-01/assets" \
  build | tail -25
APP=$(find "$G/world-device-01/DerivedData/Build/Products" -maxdepth 2 -name '*.app' | head -1)
test -n "$APP" || die "no .app produced"
if [ "${SLIM_ASSETS:-0}" = "1" ] && [ -d "$APP/assets" ]; then
  log "slim: dropping the bundled asset tree (they are pushed into the app container instead)"
  du -sh "$APP/assets" || true
  rm -rf "$APP/assets"
fi
rm -rf dist Payload
mkdir -p dist/Payload
cp -R "$APP" dist/Payload/
# Do not publish a placebo IPA: the complete embedded AOT client, native
# graphics libraries and game resources are required for a standalone build.
PACKAGE_APP="$(find dist/Payload -maxdepth 1 -type d -name '*.app' -print -quit)"
test -n "$PACKAGE_APP" || die "missing packaged .app"
for required in   "$PACKAGE_APP/Frameworks/client-graph.dylib"   "$PACKAGE_APP/Frameworks/libglfw.dylib"   "$PACKAGE_APP/Frameworks/liblwjgl.dylib"   "$PACKAGE_APP/Frameworks/libfaot_metal.dylib"   "$PACKAGE_APP/Frameworks/libopenal.dylib"   "$PACKAGE_APP/assets/indexes/30.json"; do
  test -s "$required" || die "INCOMPLETE IPA: $required"
done
test -d "$PACKAGE_APP/assets/objects" || die "INCOMPLETE IPA: game asset objects missing"
test -n "$(find "$PACKAGE_APP/assets/objects" -type f -print -quit)" || die "INCOMPLETE IPA: game asset objects empty"
test -s "$PACKAGE_APP/Frameworks/fabricaot-shaders/index.json" || die "INCOMPLETE IPA: shader index missing"
(cd dist && /usr/bin/zip -qry "$WORK/FabricAOT-game.ipa" Payload)
unzip -tq "$WORK/FabricAOT-game.ipa" > "$WORK/ipa-zip-test.txt"
shasum -a 256 "$WORK/FabricAOT-game.ipa" | tee "$WORK/ipa-sha256.txt"
printf '%s\n' "$SRC_HEAD" > "$WORK/source-sha.txt"
du -sh dist/Payload || true
log "DONE: $WORK/FabricAOT-game.ipa (unsigned; personal signing required)"
