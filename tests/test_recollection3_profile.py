from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from stage_recollection3 import CONFIG_KEYS, inventory_config


class RecollectionProfileTests(unittest.TestCase):
    def test_inventory_config_accepts_only_numeric_known_settings(self):
        source = ("\n".join(f"{key}=0" for key in sorted(CONFIG_KEYS)) + "\n").encode()
        self.assertEqual(inventory_config(source), source)
        with self.assertRaisesRegex(ValueError, "Unexpected Mouse Tweaks config"):
            inventory_config(source + b"Debug=0\n")
        with self.assertRaisesRegex(ValueError, "Unexpected Mouse Tweaks config"):
            inventory_config(source + b"unknown=1\n")
