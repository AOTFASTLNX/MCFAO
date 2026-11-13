import plistlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HighRefreshTests(unittest.TestCase):
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
