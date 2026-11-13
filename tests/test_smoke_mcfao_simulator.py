import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from smoke_mcfao_simulator import FABRIC_MARKERS, required_markers, world_ready


class SmokeCriteriaTests(unittest.TestCase):
    def test_fabric_without_fixture_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "result.json"
            build = {"loader": "fabric", "loaderReport": str(report)}
            report.write_text(json.dumps({"mods": [{"id": "appleskin"}]}))
            with self.assertRaisesRegex(ValueError, "requires mcfao_fixture"):
                required_markers(build, "fabric")
            report.write_text(json.dumps({"mods": [{"id": "mcfao_fixture"}]}))
            self.assertEqual(required_markers(build, "fabric"), FABRIC_MARKERS)

    def test_diagnostic_markers_are_explicit(self):
        self.assertEqual(required_markers({"loader": "fabric"}, "fabric", ["proof"]),
                         ("proof",))
        self.assertEqual(required_markers({"loader": "vanilla"}, "vanilla"), ())
        with self.assertRaisesRegex(ValueError, "Expected fabric"):
            required_markers({"loader": "vanilla"}, "fabric", ["proof"])

    def test_partial_world_evidence_does_not_pass(self):
        self.assertFalse(world_ready("Dev joined the game", "fabric", FABRIC_MARKERS))
        markers = "\n".join(FABRIC_MARKERS)
        self.assertFalse(world_ready(markers, "fabric", FABRIC_MARKERS))
        full = markers + "\nDev joined the game"
        self.assertTrue(world_ready(full, "fabric", FABRIC_MARKERS))
        with self.assertRaisesRegex(ValueError, "Vanilla image"):
            world_ready(full, "vanilla", ())

    def test_crash_after_join_is_rejected(self):
        full = "\n".join((*FABRIC_MARKERS, "Dev joined the game"))
        for fatal in ("[FAOT] run_main returned 1", "---- Minecraft Crash Report ----",
                      "#@!@# Game crashed!"):
            with self.subTest(fatal=fatal), self.assertRaisesRegex(RuntimeError, "crashed"):
                world_ready(full + "\n" + fatal, "fabric", FABRIC_MARKERS)
