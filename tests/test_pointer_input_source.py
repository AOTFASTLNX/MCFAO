"""Source-contract checks for the UIKit/GameController input bridge.

These checks complement the macOS workflow's real iPhoneOS Clang build, the
host-side GLFW cursor-state fixture and the pointer policy fixture. They never
claim hardware acceptance.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SURFACE = (ROOT / "ios/glfw-lite/uikit_surface.m").read_text()
GLFW = (ROOT / "ios/glfw-lite/glfw_lite.c").read_text()
POLICY = (ROOT / "ios/glfw-lite/pointer_state.c").read_text()
BUILDER = (ROOT / "tools/build_glfw_lite.py").read_text()


class PointerBridgeTests(unittest.TestCase):
    def test_gamecontroller_is_linked_with_the_bridge(self):
        self.assertIn("#import <GameController/GameController.h>", SURFACE)
        self.assertIn('"-framework","GameController"', BUILDER)
        self.assertIn('source/"pointer_state.c"', BUILDER)

    def test_camera_motion_follows_capture_with_a_documented_lock_fallback(self):
        self.assertIn("mouseMovedHandler", SURFACE)
        self.assertIn("mouseMovedDX:dx dy:dy", SURFACE)
        self.assertIn("faot_pointer_should_forward_motion", POLICY)
        self.assertIn("sendRelativeX:dx y:-dy", SURFACE)
        self.assertIn("w->cursorMode==GLFW_CURSOR_DISABLED", GLFW)
        # The old implementation dropped all motion unless the system approved the lock;
        # that is the real-device failure this branch fixes.
        self.assertNotIn("view.captured&&view.pointerIsLocked", SURFACE)

    def test_pointer_lock_follows_scene_full_screen_and_capture(self):
        self.assertIn("prefersPointerLocked", SURFACE)
        self.assertIn("wantsPointerLock", SURFACE)
        self.assertIn("setNeedsUpdateOfPrefersPointerLocked", SURFACE)
        self.assertIn("UIPointerLockStateDidChangeNotification", SURFACE)
        self.assertIn("scene.pointerLockState.isLocked", SURFACE)
        self.assertIn("sceneFillsScreen", SURFACE)
        self.assertIn("faot_pointer_prefers_lock", POLICY)

    def test_normal_menu_uses_absolute_hover_input(self):
        self.assertIn("UIHoverGestureRecognizer", SURFACE)
        self.assertIn("pointerHovered:", SURFACE)
        self.assertIn("FAOT_EVENT_CURSOR,p.x,p.y", SURFACE)
        self.assertIn("faot_pointer_should_send_menu_cursor", POLICY)

    def test_trackpad_scroll_is_a_scroll_event_not_a_finger_pan(self):
        self.assertIn("UIPanGestureRecognizer", SURFACE)
        self.assertIn("allowedScrollTypesMask=UIScrollTypeMaskAll", SURFACE)
        self.assertIn("UIEventTypeScroll", SURFACE)
        self.assertIn("scrollPanned:", SURFACE)
        self.assertIn("sendScrollX:", SURFACE)

    def test_trackpad_without_gcmouse_has_a_hover_delta_fallback(self):
        self.assertIn("faot_pointer_should_forward_hover_delta", POLICY)
        self.assertIn('source:@"hover"', SURFACE)
        self.assertIn("nativeMouseConnected", SURFACE)
        self.assertIn("hiddenPointerStyle", SURFACE)
        self.assertIn("UIPointerInteraction", SURFACE)

    def test_hardware_mouse_buttons_do_not_duplicate_uikit_pointer_touches(self):
        self.assertIn("nativeMouseButton:index pressed:pressed", SURFACE)
        self.assertIn("touch.type==UITouchTypeIndirectPointer", SURFACE)
        self.assertIn("self.captured&&indirect&&self.nativeMouseConnected", SURFACE)
        self.assertIn("releaseNativeMouseButtons", SURFACE)

    def test_device_lifetime_is_managed(self):
        self.assertIn("GCMouseDidConnectNotification", SURFACE)
        self.assertIn("GCMouseDidDisconnectNotification", SURFACE)
        self.assertIn("GCMouseDidBecomeCurrentNotification", SURFACE)
        self.assertIn("GCMouseDidStopBeingCurrentNotification", SURFACE)
        self.assertIn("[surface attachMouse:nil]", SURFACE)
        self.assertIn("old.mouseMovedHandler=nil", SURFACE)

    def test_geometry_and_lock_state_are_written_to_evidence_logs(self):
        self.assertIn("geometry points=", SURFACE)
        self.assertIn("drawable=%.0fx%.0f", SURFACE)
        self.assertIn("state reason=%@ captured=%d", SURFACE)
        self.assertIn("sceneFullScreen=%d", SURFACE)
        self.assertIn("pointerLockChanged", SURFACE)


if __name__ == "__main__":
    unittest.main()
