import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_b1_probe import validate_b0_snapshot


class B1InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "b0"
        self.root.mkdir()
        self.file = self.root / "target.class"
        self.file.write_bytes(b"first-party-test-snapshot")
        self.report = {"gateB0":"PASS", "sandboxProbe":"PASS", "filesSHA256":{
            "target.class": hashlib.sha256(self.file.read_bytes()).hexdigest()}}

    def save(self):
        (self.root / "result.json").write_text(json.dumps(self.report))

    def test_intact_snapshot_is_accepted(self):
        self.save()
        self.assertEqual(validate_b0_snapshot(self.root)["gateB0"], "PASS")

    def test_unpassed_b0_is_rejected(self):
        self.report["gateB0"] = "BLOCKED"
        self.save()
        with self.assertRaises(ValueError): validate_b0_snapshot(self.root)

    def test_sandbox_proof_is_required(self):
        del self.report["sandboxProbe"]
        self.save()
        with self.assertRaises(ValueError): validate_b0_snapshot(self.root)

    def test_changed_export_is_rejected(self):
        self.save()
        self.file.write_bytes(b"changed")
        with self.assertRaises(ValueError): validate_b0_snapshot(self.root)

    def test_parent_path_cannot_be_read(self):
        self.report["filesSHA256"] = {"../outside": "0" * 64}
        self.save()
        with self.assertRaises(ValueError): validate_b0_snapshot(self.root)

    def test_symlink_export_is_rejected(self):
        link = self.root / "alias.class"
        link.symlink_to(self.file)
        self.report["filesSHA256"] = {"alias.class": self.report["filesSHA256"]["target.class"]}
        self.save()
        with self.assertRaises(ValueError): validate_b0_snapshot(self.root)
