"""Reject graphics artifacts whose recorded source snapshot is stale or incomplete."""
import unittest
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "tools"))
from graphics_common import verify_source_manifest


class GraphicsSourceFingerprintTests(unittest.TestCase):
    def test_exact_source_snapshot_is_accepted(self):
        snapshot = {"source/A.java": "a" * 64, "source/B.m": "b" * 64}
        verify_source_manifest(snapshot, dict(snapshot))

    def test_changed_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "changed: source/A.java"):
            verify_source_manifest({"source/A.java": "a" * 64},
                                   {"source/A.java": "c" * 64})

    def test_new_unrecorded_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unrecorded: source/B.java"):
            verify_source_manifest({"source/A.java": "a" * 64},
                                   {"source/A.java": "a" * 64,
                                    "source/B.java": "b" * 64})

    def test_removed_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown: source/B.java"):
            verify_source_manifest({"source/A.java": "a" * 64,
                                    "source/B.java": "b" * 64},
                                   {"source/A.java": "a" * 64})


if __name__ == "__main__":
    unittest.main()
