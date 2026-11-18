set -eu
# Copy the icon that tools/app_icon.py already compiled with actool. The build
# passes FAOT_APP_ICON_DIR; a stock build leaves it empty and keeps no icon.
if [ -z "${FAOT_APP_ICON_DIR:-}" ]; then
  exit 0
fi
if [ -z "${FAOT_APP_ICON_NAME:-}" ]; then
  echo "error: custom app icon is missing its asset name" >&2
  exit 1
fi
if [ ! -f "$FAOT_APP_ICON_DIR/Assets.car" ]; then
  echo "error: compiled icon catalog is missing: $FAOT_APP_ICON_DIR" >&2
  exit 1
fi
resources="$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH"
mkdir -p "$resources"
if [ ! -f "$TARGET_BUILD_DIR/$INFOPLIST_PATH" ]; then
  echo "error: packaged Info.plist is missing: $TARGET_BUILD_DIR/$INFOPLIST_PATH" >&2
  exit 1
fi
for name in Assets.car "${FAOT_APP_ICON_NAME}60x60@2x.png" "${FAOT_APP_ICON_NAME}76x76@2x~ipad.png"; do
  if [ ! -f "$FAOT_APP_ICON_DIR/$name" ]; then
    echo "error: compiled icon is missing $name" >&2
    exit 1
  fi
  /usr/bin/ditto "$FAOT_APP_ICON_DIR/$name" "$resources/$name"
done
if [ ! -f "$FAOT_APP_ICON_DIR/partial.plist" ]; then
  echo "error: compiled icon Info.plist fragment is missing" >&2
  exit 1
fi
# Merging the same keys twice would duplicate the dictionaries, so only add
# them when the packaged Info.plist does not already declare this icon.
declared=$(/usr/bin/plutil -extract CFBundleIcons.CFBundlePrimaryIcon.CFBundleIconName raw -o - \
  "$TARGET_BUILD_DIR/$INFOPLIST_PATH" 2>/dev/null || true)
if [ "$declared" = "$FAOT_APP_ICON_NAME" ]; then
  exit 0
fi
# PlistBuddy's Merge is the supported way to add actool's icon keys; it leaves
# existing entries untouched and rewrites the packaged Info.plist in place.
/usr/libexec/PlistBuddy -c "Merge $FAOT_APP_ICON_DIR/partial.plist" "$TARGET_BUILD_DIR/$INFOPLIST_PATH"
