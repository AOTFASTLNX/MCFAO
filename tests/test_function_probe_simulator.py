"""The function probe refuses to run against anything but a passing smoke output."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import function_probe_simulator as probe


class ProbeGuardTests(unittest.TestCase):
    def make_smoke(self, root: Path, status: str) -> Path:
        pack = root / "artifacts" / "mcfao" / "fabric-pack-99"
        pack.mkdir(parents=True, exist_ok=True)
        out = Path(f"{pack}-simulator")
        out.mkdir(exist_ok=True)
        (out / "result.json").write_text(json.dumps({"status": status}))
        staged = out / "staged"
        staged.mkdir(exist_ok=True)
        (staged / "libglfw.dylib").write_bytes(b"stub")
        return pack

    def test_the_probed_world_is_the_smoke_world_not_an_invention(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_smoke(Path(directory), "SIMULATOR_WORLD_SMOKE_PASS")
            # smoke_mcfao_simulator.py writes the save as "MCFAO Smoke <output dir>"; the
            # probe derives the same name, so a typo can never point it at another save.
            self.assertEqual(probe.WORLD_NAME(pack), "MCFAO Smoke fabric-pack-99-simulator")

    def test_a_failed_or_diagnostic_smoke_cannot_host_the_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            for status in ("SIMULATOR_WORLD_DIAGNOSTIC_PASS", "FAILED", "NOT_RUN"):
                pack = self.make_smoke(Path(directory), status)
                with mock.patch.object(probe, "validate_dylib"), \
                     self.assertRaises(ValueError):
                    probe.run(mock.Mock(pack=pack))

    def test_missing_smoke_output_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory) / "fabric-pack-99"
            pack.mkdir()
            with self.assertRaises(OSError):
                probe.run(mock.Mock(pack=pack))


if __name__ == "__main__":
    unittest.main()


class AttachmentNamingTests(unittest.TestCase):
    """The evidence table cites the test's own labels, not xcresult's UUID file names."""

    def test_uuid_exports_are_renamed_to_the_label_the_test_attached(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "0A1B.png").write_bytes(b"joined")
            (out / "0A1B.png").with_name("2C3D.png").write_bytes(b"moved")
            manifest = [{"attachments": [
                {"exportedFileName": "0A1B.png",
                 "suggestedHumanReadableName": "probe-joined_0_AAAA.png"},
                {"exportedFileName": "2C3D.png",
                 "suggestedHumanReadableName": "probe-moved_0_BBBB.png"},
            ]}]
            names = probe.retain_attachment_names(manifest, out)
            self.assertEqual(names, ["probe-joined_0_AAAA.png", "probe-moved_0_BBBB.png"])
            self.assertEqual((out / names[0]).read_bytes(), b"joined")
            self.assertFalse((out / "0A1B.png").exists())

    def test_two_attachments_sharing_a_label_cannot_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "AA.png").write_bytes(b"first")
            (out / "BB.png").write_bytes(b"second")
            manifest = [{"attachments": [
                {"exportedFileName": "AA.png", "suggestedHumanReadableName": "frame.png"},
                {"exportedFileName": "BB.png", "suggestedHumanReadableName": "frame.png"},
            ]}]
            names = probe.retain_attachment_names(manifest, out)
            self.assertEqual(len(set(names)), 2)
            self.assertEqual({(out / name).read_bytes() for name in names},
                             {b"first", b"second"})
