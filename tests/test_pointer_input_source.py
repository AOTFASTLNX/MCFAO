"""Regression checks for the UIKit/GameController input bridge.

These checks complement the macOS workflow's real iPhoneOS Clang build and the
host-side GLFW cursor-state fixture; they do not claim hardware acceptance.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SURFACE = (ROOT / "ios/glfw-lite/uikit_surface.m").read_text()
GLFW = (ROOT / "ios/glfw-lite/glfw_lite.c").read_text()
BUILDER = (ROOT / "tools/build_glfw_lite.py").read_text()


class PointerBridgeTests(unittest.TestCase):
    def test_gamecontroller_is_linked_with_the_bridge(self):
        self.assertIn("#import <GameController/GameController.h>", SURFACE)
        self.assertIn('"-framework","GameController"', BUILDER)

    def test_relative_mouse_motion_requires_actual_pointer_lock(self):
        self.assertIn("mouseMovedHandler", SURFACE)
        self.assertIn("view.captured&&view.pointerIsLocked", SURFACE)
        self.assertIn("FAOT_EVENT_CURSOR_DELTA,dx,-dy", SURFACE)
        self.assertIn("w->cursorMode==GLFW_CURSOR_DISABLED", GLFW)

    def test_pointer_lock_follows_game_capture_and_not_just_requested_state(self):
        self.assertIn("prefersPointerLocked", SURFACE)
        self.assertIn("setNeedsUpdateOfPrefersPointerLocked", SURFACE)
        self.assertIn("UIPointerLockStateDidChangeNotification", SURFACE)
        self.assertIn("scene.pointerLockState.isLocked", SURFACE)

    def test_normal_menu_uses_absolute_hover_input(self):
        self.assertIn("UIHoverGestureRecognizer", SURFACE)
        self.assertIn("pointerHovered:", SURFACE)
        self.assertIn("FAOT_EVENT_CURSOR,p.x,p.y", SURFACE)

    def test_unlocked_game_falls_back_to_hover_deltas_without_affecting_locked_motion(self):
        self.assertIn("else if(!self.pointerIsLocked)", SURFACE)
        self.assertIn("faot_pointer_hover_delta(&_hoverMotion,p.x,p.y,&dx,&dy)", SURFACE)
        self.assertIn("FAOT_EVENT_CURSOR_DELTA,dx,dy", SURFACE)
        self.assertIn("[view resetHoverMotion]", SURFACE)
        self.assertIn("hover.cancelsTouchesInView=NO", SURFACE)

    def test_hardware_mouse_buttons_do_not_duplicate_uikit_pointer_touches(self):
        self.assertIn("nativeMouseButton:index pressed:pressed", SURFACE)
        self.assertIn("touch.type==UITouchTypeIndirectPointer", SURFACE)
        self.assertIn("self.nativeMouseConnected", SURFACE)
        self.assertIn("releaseNativeMouseButtons", SURFACE)

    def test_device_lifetime_is_managed(self):
        self.assertIn("GCMouseDidConnectNotification", SURFACE)
        self.assertIn("GCMouseDidDisconnectNotification", SURFACE)
        self.assertIn("[surface attachMouse:nil]", SURFACE)
        self.assertIn("old.mouseMovedHandler=nil", SURFACE)


if __name__ == "__main__":
    unittest.main()
