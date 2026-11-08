import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from locate_local_client import inspect_profile


class LocalClientTests(unittest.TestCase):
    def fixture(self, root):
        profile = root / "profiles/Example"
        profile.mkdir(parents=True)
        version = root / "meta/versions/26.1.2"
        version.mkdir(parents=True)
        jar = version / "26.1.2.jar"
        with zipfile.ZipFile(jar, "w") as archive:
            archive.writestr("fixture/Main.class", b"first-party structural fixture")
        metadata = root / "version.json"
        metadata.write_text(json.dumps({"id": "26.1.2", "mainClass": "fixture.Main",
                                       "downloads": {"client": {"size": jar.stat().st_size,
                                                                 "sha1": hashlib.sha1(jar.read_bytes()).hexdigest()}}}))
        return profile, metadata, jar

    def test_shared_client_found_without_reading_account_or_world_data(self):
        with tempfile.TemporaryDirectory() as directory:
            profile, metadata, jar = self.fixture(Path(directory))
            (profile.parent.parent / "data").mkdir()
            (profile.parent.parent / "data/data.db").write_bytes(b"invalid-private-database")
            result = inspect_profile(profile, metadata)
            self.assertTrue(result["matchesVersionMetadata"])
            self.assertEqual(result["clientJar"], str(jar.resolve()))
            self.assertEqual(result["gateA0"], "BLOCKED")
            self.assertEqual(result["ownership"], "NOT CHECKED")

    def test_modified_client_is_not_a_matching_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            profile, metadata, jar = self.fixture(Path(directory))
            with zipfile.ZipFile(jar, "a") as archive:
                archive.writestr("modified.txt", b"changed")
            self.assertFalse(inspect_profile(profile, metadata)["matchesVersionMetadata"])

    def test_missing_shared_client_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            profile, metadata, jar = self.fixture(Path(directory))
            jar.unlink()
            self.assertFalse(inspect_profile(profile, metadata)["clientJarPresent"])

    def test_wrong_minecraft_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            profile, metadata, jar = self.fixture(Path(directory))
            metadata.write_text('{"id":"1.21.2"}')
            with self.assertRaisesRegex(ValueError, "exact Minecraft"):
                inspect_profile(profile, metadata)


if __name__ == "__main__":
    unittest.main()
