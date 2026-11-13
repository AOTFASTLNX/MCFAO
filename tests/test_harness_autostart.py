from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HarnessAutostartTests(unittest.TestCase):
    def test_console_screen_starts_automatically_without_obsolete_controls(self):
        source = (ROOT / "ios/C0Harness/main.m").read_text(encoding="utf-8")
        harness = source.split("@implementation FAOTHarnessController", 1)[1].split("@interface FAOTSceneDelegate", 1)[0]
        self.assertIn("[self start]", harness)
        self.assertIn("if (self.started) return", harness)
        self.assertIn("copyTapped", harness)
        self.assertNotIn("spacePicker", harness)
        self.assertNotIn("extraArgs", harness)
        self.assertNotIn("runTapped", harness)
        self.assertNotIn("启动客户端", harness)


if __name__ == "__main__":
    unittest.main()
