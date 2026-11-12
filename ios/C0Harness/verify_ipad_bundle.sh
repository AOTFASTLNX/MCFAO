#!/bin/sh
# Fail a device build unless the processed Info.plist is a native iPad bundle.
# This runs from the "Embed Graphics Libraries" phase, after ProcessInfoPlistFile.
set -eu

plist="${TARGET_BUILD_DIR:?}/${INFOPLIST_PATH:?}"
[ -f "$plist" ] || {
    echo "error: processed Info.plist is missing: $plist" >&2
    exit 1
}

case ",${TARGETED_DEVICE_FAMILY:-}," in
    *,1,2,*|*,2,1,*) ;;
    *)
        echo "error: TARGETED_DEVICE_FAMILY is '${TARGETED_DEVICE_FAMILY:-}' but the WorldDevice build requires 1,2" >&2
        exit 1
        ;;
esac

family_first=$(/usr/libexec/PlistBuddy -c 'Print :UIDeviceFamily:0' "$plist" 2>/dev/null || true)
family_second=$(/usr/libexec/PlistBuddy -c 'Print :UIDeviceFamily:1' "$plist" 2>/dev/null || true)
if ! { [ "$family_first" = 1 ] && [ "$family_second" = 2 ]; } &&
   ! { [ "$family_first" = 2 ] && [ "$family_second" = 1 ]; }; then
    echo "error: final UIDeviceFamily must contain both 1 and 2 (got '${family_first:-}', '${family_second:-}')" >&2
    exit 1
fi

full_screen=$(/usr/libexec/PlistBuddy -c 'Print :UIRequiresFullScreen' "$plist" 2>/dev/null || true)
[ "$full_screen" = true ] || {
    echo "error: UIRequiresFullScreen must be true for the full-screen pointer-lock contract" >&2
    exit 1
}

indirect=$(/usr/libexec/PlistBuddy -c 'Print :UIApplicationSupportsIndirectInputEvents' "$plist" 2>/dev/null || true)
[ "$indirect" = true ] || {
    echo "error: UIApplicationSupportsIndirectInputEvents must be true" >&2
    exit 1
}

ipad_orientations=$(/usr/libexec/PlistBuddy -c 'Print :UISupportedInterfaceOrientations~ipad' "$plist" 2>/dev/null || true)
case "$ipad_orientations" in
    *UIInterfaceOrientationLandscapeLeft*|*UIInterfaceOrientationLandscapeRight*) ;;
    *)
        echo "error: UISupportedInterfaceOrientations~ipad must include a landscape orientation" >&2
        exit 1
        ;;
esac

platform=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleSupportedPlatforms:0' "$plist" 2>/dev/null || true)
[ "$platform" = iPhoneOS ] || {
    echo "error: CFBundleSupportedPlatforms:0 must be iPhoneOS (got '${platform:-}')" >&2
    exit 1
}

printf 'iPad bundle contract PASS: UIDeviceFamily=[1,2] TARGETED_DEVICE_FAMILY=%s fullScreen=%s indirectInput=%s\n' \
    "${TARGETED_DEVICE_FAMILY:-}" "$full_screen" "$indirect"
