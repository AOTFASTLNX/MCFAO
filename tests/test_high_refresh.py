import plistlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HighRefreshTests(unittest.TestCase):
    def test_three_drawables_and_frame_slots_share_a_bounded_depth(self):
        source = (ROOT / "ios/metal-bridge/metal_bridge.m").read_text()
        self.assertIn("FAOT_PRESENTATION_DEPTH = 3", source)
        self.assertIn("layer.maximumDrawableCount=FAOT_PRESENTATION_DEPTH", source)
        self.assertIn("dispatch_semaphore_create(FAOT_PRESENTATION_DEPTH)", source)

    def test_offscreen_work_is_committed_before_drawable_wait_on_same_queue(self):
        source = (ROOT / "ios/metal-bridge/metal_bridge.m").read_text()
        present = source.split("MetalNative_presentFrame", 1)[1].split("@interface FAOTMetalPipeline", 1)[0]
        self.assertLess(present.index("dispatch_semaphore_wait"), present.index("commit(ctx,render)"))
        self.assertLess(present.index("commit(ctx,render)"), present.index("[ctx.layer nextDrawable]"))
        self.assertNotIn("waitUntilCompleted", present)
        self.assertNotIn("newCommandQueue", present)

    def test_phone_promotion_is_enabled_in_world_device_plist(self):
        config = (ROOT / "ios/C0Harness/WorldDevice.xcconfig").read_text()
        self.assertIn("INFOPLIST_FILE = Info.WorldSimulator.plist", config)
        with (ROOT / "ios/C0Harness/Info.WorldSimulator.plist").open("rb") as stream:
            self.assertIs(plistlib.load(stream)["CADisableMinimumFrameDurationOnPhone"], True)

    def test_default_and_existing_fps_options_allow_120(self):
        source = (ROOT / "ios/C0Harness/main.m").read_text(encoding="utf-8")
        self.assertIn('fps > 120 ? line : @"maxFps:120"', source)
        self.assertIn('if (!fpsPresent) [updated addObject:@"maxFps:120"]', source)
        self.assertIn('maxFps:120\\n', source)


if __name__ == "__main__":
    unittest.main()
