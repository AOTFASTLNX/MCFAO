import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from native_image_home import native_image_home


class NativeImageHomeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name).resolve() / "Home"
        self.builder = self.home / "lib/svm/builder"
        self.builder.mkdir(parents=True)
        self.launcher = self.home / "lib/svm/bin/native-image"
        self.launcher.parent.mkdir()
        self.launcher.write_text("fixture launcher")
        self.launcher.chmod(0o755)
        (self.home / "bin").mkdir()
        (self.home / "bin/native-image").symlink_to("../lib/svm/bin/native-image")
        (self.builder / "svm.jar").write_bytes(b"fixture jar")

    def test_clean_home_is_used_in_place(self):
        (self.home / ".DS_Store").touch()
        with native_image_home(self.home) as selected:
            self.assertEqual(selected, self.home)

    def test_staging_filters_metadata_preserves_content_and_cleans_up_on_failure(self):
        sidecar = self.builder / "._svm.jar"
        sidecar.write_bytes(bytes.fromhex("00051607"))
        (self.builder / ".ordinary-resource").write_text("keep")
        (self.builder / "__MACOSX").mkdir()
        (self.builder / "__MACOSX/not-a-module.jar").touch()
        with self.assertRaisesRegex(RuntimeError, "failed build"):
            with native_image_home(self.home) as selected:
                self.assertNotEqual(selected, self.home)
                launcher = selected / "bin/native-image"
                self.assertEqual(launcher.resolve(), selected / "lib/svm/bin/native-image")
                self.assertTrue(os.access(launcher, os.X_OK))
                self.assertEqual({p.name for p in (selected / "lib/svm/builder").iterdir()},
                                 {"svm.jar", ".ordinary-resource"})
                self.assertEqual((selected / "lib/svm/builder/svm.jar").read_bytes(), b"fixture jar")
                raise RuntimeError("failed build")
        self.assertFalse(selected.exists())
        self.assertTrue(sidecar.is_file())

    def test_staging_refuses_links_outside_the_toolchain(self):
        (self.builder / "._svm.jar").touch()
        outside = self.home.parent / "outside"
        outside.touch()
        (self.builder / "other.jar").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Cannot stage GraalVM link"):
            with native_image_home(self.home):
                self.fail("The external link was accepted")
