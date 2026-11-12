#!/usr/bin/env bash
# Reuse a verified AOT image only when all runtime/compiler inputs are unchanged.
set -euo pipefail
: "${BASE_IPA_URL:?provide a trusted prior build artifact URL}"
: "${BASE_SOURCE_REF:?provide its exact source commit}"
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
git cat-file -e "$BASE_SOURCE_REF^{commit}" 2>/dev/null || git fetch --depth 1 origin "$BASE_SOURCE_REF"
python3 - "$BASE_SOURCE_REF" <<'PY'
import subprocess,sys
paths=subprocess.check_output(['git','diff','--name-only',sys.argv[1],'HEAD'],text=True).splitlines()
allowed=('ios/C0Harness/','ci/','docs/','.github/')
blocked=[p for p in paths if not p.startswith(allowed)]
if blocked: raise SystemExit('Full AOT/runtime rebuild required: '+', '.join(blocked))
PY
WORK="$RUNNER_TEMP/fabricaot-native-refresh"
mkdir -p "$WORK/base"
curl -fsSL --retry 3 --retry-all-errors "$BASE_IPA_URL" -o "$WORK/base.ipa"
unzip -q "$WORK/base.ipa" -d "$WORK/base"
BASE="$WORK/base/Payload/C0Harness.app"
test -f "$BASE/Frameworks/client-graph.dylib"
xcodebuild -project ios/C0Harness/C0Harness.xcodeproj -scheme WorldDevice \
  -configuration 'World Device' -destination 'generic/platform=iOS' \
  -derivedDataPath "$WORK/DerivedData" CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  FAOT_CLIENT_LIBRARY="$BASE/Frameworks/client-graph.dylib" \
  FAOT_GRAPHICS_NATIVE_DIR="$BASE/Frameworks" build > "$WORK/xcodebuild.log" 2>&1 || { tail -80 "$WORK/xcodebuild.log"; exit 1; }
APP="$WORK/DerivedData/Build/Products/World Device-iphoneos/C0Harness.app"
test -f "$APP/C0Harness"
if [ -d "$BASE/assets" ]; then ditto "$BASE/assets" "$APP/assets"; fi
python3 - "$APP/FabricAOT-build.json" "$BASE_SOURCE_REF" "$WORK/base.ipa" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'source':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'aotBaseSource':sys.argv[2],'baseIPASHA256':hashlib.file_digest(open(sys.argv[3],'rb'),'sha256').hexdigest(),'scope':'UIKit launcher refresh; unchanged AOT and native graphics libraries'},indent=2))
PY
mkdir -p "$WORK/package/Payload"
ditto "$APP" "$WORK/package/Payload/C0Harness.app"
(cd "$WORK/package" && zip -qry "$WORK/unsigned.ipa" Payload)
echo "unsigned=$WORK/unsigned.ipa" >> "$GITHUB_OUTPUT"
echo "log=$WORK/xcodebuild.log" >> "$GITHUB_OUTPUT"
