#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="${1:-NCL-demo-20261121}"
OUT="${ROOT}/artifacts/ncl-demo-${LABEL}"
DERIVED="${OUT}/DerivedData"
PAYLOAD="${OUT}/Payload"

rm -rf "$OUT"
mkdir -p "$OUT" "$PAYLOAD"

/usr/bin/xcodebuild \
  -project "$ROOT/ios/NCLDemo/NCLDemo.xcodeproj" \
  -target C0Harness \
  -configuration Release \
  -sdk iphoneos \
  CONFIGURATION_BUILD_DIR="$DERIVED/Build/Products/Release-iphoneos" \
  FAOT_TEST_VERSION="$LABEL" \
  PRODUCT_BUNDLE_IDENTIFIER=org.fabricaot.ncl.demo \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  build

APP="$DERIVED/Build/Products/Release-iphoneos/C0Harness.app"
test -d "$APP"
cp -R "$APP" "$PAYLOAD/NCLDemo.app"

IPA="$OUT/Native-Craft-Launcher-${LABEL}.ipa"
(cd "$OUT" && /usr/bin/zip -qry "$IPA" Payload)

/usr/bin/python3 - "$IPA" "$APP" "$OUT/result.json" <<'PY'
import hashlib, json, plistlib, sys
from pathlib import Path
ipa, app, result = map(Path, sys.argv[1:])
info = plistlib.loads((app / "Info.plist").read_bytes())
payload = {"status": "UNSIGNED_DEMO_IPA", "ipa": str(ipa), "bytes": ipa.stat().st_size,
           "sha256": hashlib.sha256(ipa.read_bytes()).hexdigest(),
           "testVersion": info.get("FAOTTestVersion", ""), "containsGameRuntime": False}
Path(result).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
