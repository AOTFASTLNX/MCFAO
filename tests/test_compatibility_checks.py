import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from run_compatibility_checks import select


class CompatibilityChecksTests(unittest.TestCase):
    def test_multiple_mechanisms_use_only_known_deduplicated_suites(self):
        tests, missing, device = select({"mods": [
            {"relevantChecks": ["image-pixel-contract", "runtime-resource-read", "ios-sandbox-filesystem"]},
            {"relevantChecks": ["dynamic-class-contract", "../other.py", "serialization-round-trip"]},
        ]})
        self.assertEqual(tests, [
            "test_aot_compatibility.py", "test_resource_closure.py", "test_runtime_lowering.py",
        ])
        self.assertEqual(missing, ["../other.py", "serialization-round-trip"])
        self.assertEqual(device, ["ios-sandbox-filesystem"])

    def test_older_reports_select_no_arbitrary_tests(self):
        self.assertEqual(select({"stages": {"aot": "PASS"}}), ([], [], []))
