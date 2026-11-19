"""An unsigned IPA is the build's own app, stripped and zipped - never a re-signed one."""
from __future__ import annotations

import json
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import package_unsigned_ipa as pack
from mcfao import tree_files, write_json
from mod_file_policy import is_metadata


def make_app(build: Path, status: str = "SIGNED_DEVICE_APP") -> Path:
    """A fake device app: real Info.plist, a payload file, and a development signature."""
    app = build / "package" / "attempt" / "product" / "C0Harness.app"
    (app / "_CodeSignature").mkdir(parents=True)
    (app / "Frameworks").mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "org.example.test",
        "CFBundleShortVersionString": "0.1",
        "CFBundleVersion": "6",
        "MinimumOSVersion": "17.0",
    }))
    (app / "C0Harness").write_bytes(b"not really a mach-o")
    (app / "Frameworks" / "libglfw.dylib").write_bytes(b"dylib placeholder")
    (app / "_CodeSignature" / "CodeResources").write_bytes(b"signature")
    (app / "embedded.mobileprovision").write_bytes(b"profile")
    write_json(build / "result.json", {
        "status": status,
        "target": "ios-arm64",
        "app": "package/attempt/product/C0Harness.app",
        "appFilesSHA256": tree_files(app),
    })
    return app


class PackageUnsignedIpaTests(unittest.TestCase):
    def test_a_build_that_never_finished_cannot_be_packaged(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory) / "build"
            make_app(build, status="ANALYZED")
            with self.assertRaisesRegex(ValueError, "completed"):
                pack.run(build, Path(directory) / "ipa")

    def test_an_app_that_drifted_from_its_manifest_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory) / "build"
            app = make_app(build)
            (app / "C0Harness").write_bytes(b"changed after the build")
            with self.assertRaisesRegex(ValueError, "differs from the build manifest"):
                pack.run(build, Path(directory) / "ipa")

    def test_the_ipa_is_payload_shaped_and_carries_no_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory) / "build"
            app = make_app(build)
            (app / "Frameworks/._libglfw.dylib").write_bytes(bytes.fromhex("00051607"))
            (app / "__MACOSX").mkdir()
            (app / "__MACOSX/Info.plist").write_bytes(b"metadata")
            (app / ".DS_Store").write_bytes(b"metadata")
            (app / "C0Harness").chmod(0o755)
            result = pack.run(build, Path(directory) / "ipa")
            ipa = Path(result["ipa"])
            self.assertTrue(ipa.is_file())
            with zipfile.ZipFile(ipa) as archive:
                names = archive.namelist()
                self.assertTrue((archive.getinfo("Payload/C0Harness.app/C0Harness").external_attr >> 16) & 0o111)
            self.assertIn("Payload/C0Harness.app/C0Harness", names)
            self.assertIn("Payload/C0Harness.app/Info.plist", names)
            self.assertFalse([n for n in names if "_CodeSignature" in n or
                              "embedded.mobileprovision" in n],
                             "the development signature must not survive into the IPA")
            self.assertFalse([n for n in names if is_metadata(n)],
                             "resource-fork entries are not part of an IPA")
            self.assertEqual(result["status"], "UNSIGNED_IPA_EXPORTED")
            self.assertFalse(result["signed"])
            self.assertEqual(result["bundleIdentifier"], "org.example.test")
            self.assertEqual(result["minimumOSVersion"], "17.0")
            self.assertEqual(result["deviceRun"], "NOT RUN")
            self.assertEqual(json.loads((ipa.parent / "result.json").read_text()), result)

    def test_the_output_directory_must_be_new(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory) / "build"
            make_app(build)
            output = Path(directory) / "ipa"
            output.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                pack.run(build, output)

    def test_failed_codesign_removal_is_reported_instead_of_creating_an_ipa(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory) / "build"
            app = make_app(build)
            output = Path(directory) / "ipa"
            with patch.object(pack, "macho_files", side_effect=lambda staged: [staged / "C0Harness"]), \
                 patch.object(pack, "capture", return_value={"exitCode": 1, "timedOut": False}) as run:
                with self.assertRaisesRegex(ValueError, "Could not remove the Mach-O signature"):
                    pack.run(build, output)
            staged_binary = Path(run.call_args.args[0][-1])
            self.assertFalse(staged_binary.is_relative_to(output.resolve()))
            self.assertFalse(staged_binary.exists())
            self.assertTrue((app / "_CodeSignature").is_dir())
            self.assertEqual(list(output.glob("*.ipa")), [])


if __name__ == "__main__":
    unittest.main()
