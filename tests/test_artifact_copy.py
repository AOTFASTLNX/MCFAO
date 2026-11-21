import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import artifact_copy
from artifact_copy import copy_artifact


class ArtifactCopyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "client-graph.dylib"
        self.source.write_bytes(b"native image bytes" * 4096)
        os.chmod(self.source, 0o640)

    def test_clone_keeps_independent_inode_and_bytes(self):
        destination = self.root / "stage" / "client-graph.dylib"
        destination.parent.mkdir()
        mode = copy_artifact(self.source, destination)
        self.assertEqual(destination.read_bytes(), self.source.read_bytes())
        self.assertNotEqual(destination.stat().st_ino, self.source.stat().st_ino)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o640)
        if sys.platform == "darwin":
            self.assertEqual(mode, "clone")
        destination.write_bytes(b"resigned")
        self.assertEqual(self.source.read_bytes(), b"native image bytes" * 4096)

    def test_fallback_copy_when_clone_is_unavailable(self):
        destination = self.root / "copy.dylib"
        with patch.object(artifact_copy, "_clonefile", return_value=False):
            self.assertEqual(copy_artifact(self.source, destination), "copy")
        self.assertEqual(destination.read_bytes(), self.source.read_bytes())

    def test_existing_destination_is_replaced(self):
        destination = self.root / "existing.dylib"
        destination.write_bytes(b"old build")
        copy_artifact(self.source, destination)
        self.assertEqual(destination.read_bytes(), self.source.read_bytes())

    def test_directory_destination_is_rejected(self):
        destination = self.root / "folder"
        destination.mkdir()
        with self.assertRaises(IsADirectoryError):
            copy_artifact(self.source, destination)


if __name__ == "__main__":
    unittest.main()
