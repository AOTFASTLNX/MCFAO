set -eu
if [ -n "${FAOT_INSTANCE_DATA_DIR:-}" ]; then
  /usr/bin/ditto "$FAOT_INSTANCE_DATA_DIR" "$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/instance-seed"
fi
if [ -n "${FAOT_GAME_ASSETS_DIR:-}" ]; then
  if [ "${PLATFORM_NAME:-}" != iphoneos ] || [ "${TARGET_DEVICE_PLATFORM_NAME:-iphoneos}" != iphoneos ]; then
    echo "error: WorldDevice requires an iPhone device destination." >&2
    exit 1
  fi
  if [ ! -f "$FAOT_GAME_ASSETS_DIR/indexes/30.json" ] || [ ! -d "$FAOT_GAME_ASSETS_DIR/objects" ]; then
    echo "error: Verified local Minecraft assets are missing: $FAOT_GAME_ASSETS_DIR" >&2
    exit 1
  fi
  case "${FAOT_RENDERER:-metal}" in
    gl41) renderer_files="liblwjgl_opengl.dylib libOSMesa.8.dylib libMoltenVK.dylib" ;;
    metal) renderer_files="libfaot_metal.dylib fabricaot-present.metallib fabricaot-shaders/index.json" ;;
    *) echo "error: unknown FAOT_RENDERER" >&2; exit 1 ;;
  esac
  for name in libglfw.dylib liblwjgl.dylib libopenal.dylib $renderer_files; do
    if [ ! -f "$FAOT_GRAPHICS_NATIVE_DIR/$name" ]; then
      echo "error: iPhone game input is missing: $FAOT_GRAPHICS_NATIVE_DIR/$name" >&2
      exit 1
    fi
  done
  /usr/bin/ditto "$FAOT_GAME_ASSETS_DIR" "$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/assets"
fi
if [ -n "${FAOT_GRAPHICS_NATIVE_DIR:-}" ]; then
  if [ ! -d "$FAOT_GRAPHICS_NATIVE_DIR" ]; then
    echo "error: Graphics input directory is missing: $FAOT_GRAPHICS_NATIVE_DIR" >&2
    exit 1
  fi
  mkdir -p "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH"
  for name in libglfw.dylib liblwjgl.dylib libfaot_metal.dylib libopenal.dylib; do
    if [ ! -f "$FAOT_GRAPHICS_NATIVE_DIR/$name" ]; then continue; fi
    /usr/bin/ditto "$FAOT_GRAPHICS_NATIVE_DIR/$name" "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/$name"
    if [ "${CODE_SIGNING_ALLOWED:-NO}" = YES ] && [ -n "${EXPANDED_CODE_SIGN_IDENTITY:-}" ]; then
      /usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/$name"
    fi
  done
  for name in liblwjgl_opengl.dylib libOSMesa.8.dylib libMoltenVK.dylib; do
    if [ ! -f "$FAOT_GRAPHICS_NATIVE_DIR/$name" ]; then continue; fi
    /usr/bin/ditto "$FAOT_GRAPHICS_NATIVE_DIR/$name" "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/$name"
    if [ "${CODE_SIGNING_ALLOWED:-NO}" = YES ] && [ -n "${EXPANDED_CODE_SIGN_IDENTITY:-}" ]; then
      /usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/$name"
    fi
  done
  if [ -f "$FAOT_GRAPHICS_NATIVE_DIR/fabricaot-present.metallib" ]; then
    /usr/bin/ditto "$FAOT_GRAPHICS_NATIVE_DIR/fabricaot-present.metallib" "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/fabricaot-present.metallib"
  fi
  if [ -d "$FAOT_GRAPHICS_NATIVE_DIR/fabricaot-shaders" ]; then
    /usr/bin/ditto "$FAOT_GRAPHICS_NATIVE_DIR/fabricaot-shaders" "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/fabricaot-shaders"
  fi
fi
