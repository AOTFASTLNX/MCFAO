"""Regression coverage for the C0 iOS harness driver.

The interesting failures here are silent ones: signing a macOS object into an iOS app, or
reporting an IPA as installable when the embedded profile lists no devices.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
import subprocess
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from build_c0_harness import (DEFAULT_DYLIB, parse_platform, parse_profile_devices,
                              provisioned_devices, validate_dylib, archive, export_archive,validate_shader_bundle,verify_simulator_embedded_libraries)  # noqa: E402
import json
import hashlib

class EmbeddedLibraryTests(unittest.TestCase):
    def test_native_input_must_actually_be_copied_to_app(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);app=root/'App.app';(app/'Frameworks').mkdir(parents=True)
            record={'path':'/input/libopenal.dylib','sha256':hashlib.sha256(b'library fixture').hexdigest()}
            with self.assertRaisesRegex(ValueError,'missing or changed'):verify_simulator_embedded_libraries(app,[record])
            target=app/'Frameworks/libopenal.dylib';target.write_bytes(b'library fixture')
            self.assertIn('libopenal.dylib',verify_simulator_embedded_libraries(app,[record]))
            target.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'missing or changed'):verify_simulator_embedded_libraries(app,[record])

class ShaderBundleTests(unittest.TestCase):
    def fixture(self,root):
        directory=root/'bundle';directory.mkdir();key='a'*64;binary=directory/(key+'.metallib');binary.write_bytes(b'first-party metadata fixture')
        index=directory/'index.json';index.write_text(json.dumps({'schema':1,'programs':[{'key':key,'status':'TRANSLATED','metallibSHA256':hashlib.sha256(binary.read_bytes()).hexdigest()}]}))
        (root/'result.json').write_text(json.dumps({'status':'VANILLA_SHADERS_PRECOMPILED','sdk':'iphonesimulator','indexSHA256':hashlib.sha256(index.read_bytes()).hexdigest()}))
        return directory,binary
    def test_shader_bundle_sdk_is_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            directory,_=self.fixture(Path(temp));self.assertEqual(validate_shader_bundle(directory,True)['programs'],1)
            with self.assertRaisesRegex(ValueError,'selected SDK'):validate_shader_bundle(directory,False)
    def test_modified_metallib_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory,binary=self.fixture(Path(temp));binary.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'fingerprint changed'):validate_shader_bundle(directory,True)
    def test_unexpected_shader_bundle_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory,_=self.fixture(Path(temp));(directory/'unrelated').write_text('unexpected')
            with self.assertRaisesRegex(ValueError,'Unexpected'):validate_shader_bundle(directory,True)


class OutputPreservationTests(unittest.TestCase):
    def test_independent_log_writers_preserve_host_exit_record(self):
        compiler = shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        source = Path(__file__).resolve().parent.parent / "interop/diagnostics/C0LogAppendProbe.c"
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "append-log-probe"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", str(source), "-o", str(binary)],
                           check=True, capture_output=True, timeout=30)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.stdout.strip(), "C0_APPEND_LOG_PASS")

    def test_existing_archive_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);old=root/"C0Harness.xcarchive";old.mkdir();marker=old/"keep.txt";marker.write_text("evidence")
            with patch("build_c0_harness.HARNESS_DIR",root),patch("build_c0_harness.run") as run:
                with self.assertRaisesRegex(RuntimeError,"choose a new --output"):
                    archive(Path("image.dylib"),"Debug",10)
                run.assert_not_called()
            self.assertEqual(marker.read_text(),"evidence")
    def test_existing_export_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);old=root/"export";old.mkdir();marker=old/"keep.txt";marker.write_text("evidence")
            with patch("build_c0_harness.HARNESS_DIR",root),patch("build_c0_harness.run") as run:
                with self.assertRaisesRegex(RuntimeError,"choose a new --output"):
                    export_archive(10)
                run.assert_not_called()
            self.assertEqual(marker.read_text(),"evidence")

VTOOL_IOS = """
client-graph.dylib:
Load command 2
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform IOS
    minos 17.0
      sdk 27.2
"""

VTOOL_MACOS = VTOOL_IOS.replace("platform IOS", "platform MACOS")
LIPO_ARM64 = ("Non-fat file: client-graph.dylib is architecture: arm64\n")


class PlatformParsingTests(unittest.TestCase):
    def test_ios_arm64_is_recognised(self):
        facts = parse_platform(VTOOL_IOS, LIPO_ARM64)
        self.assertEqual(facts["platform"], "IOS")
        self.assertEqual(facts["minos"], "17.0")
        self.assertIn("arm64", facts["architectures"])

    def test_macos_object_is_not_ios(self):
        facts = parse_platform(VTOOL_MACOS, LIPO_ARM64)
        self.assertEqual(facts["platform"], "MACOS")
        self.assertNotEqual(facts["platform"], "IOS")

    def test_missing_build_version_yields_none(self):
        facts = parse_platform("", "")
        self.assertIsNone(facts["platform"])
        self.assertIsNone(facts["minos"])
        self.assertIsNone(facts["architectures"])


class ProfileParsingTests(unittest.TestCase):
    PROFILE = """<dict>
        <key>Name</key><string>iOS Team Provisioning Profile: org.example</string>
        <key>ProvisionedDevices</key>
        <array>
            <string>00008160-001A78620A600036</string>
            <string>00008112001218ea0aa3401e</string>
        </array>
    </dict>"""

    def test_devices_are_extracted_in_both_udid_shapes(self):
        self.assertEqual(
            parse_profile_devices(self.PROFILE),
            sorted(["00008112001218ea0aa3401e", "00008160-001A78620A600036"]))

    def test_empty_array_means_no_registered_devices(self):
        text = self.PROFILE.replace(
            "<string>00008160-001A78620A600036</string>\n            "
            "<string>00008112001218ea0aa3401e</string>", "")
        self.assertEqual(parse_profile_devices(text), [])

    def test_missing_key_means_no_registered_devices(self):
        self.assertEqual(parse_profile_devices("<dict><key>Name</key><string>x</string></dict>"), [])

    def test_device_outside_the_array_is_ignored(self):
        text = ("<dict><key>Name</key><string>00008160-001A78620A600036</string>"
                "<key>ProvisionedDevices</key><array></array></dict>")
        self.assertEqual(parse_profile_devices(text), [])

    def test_archive_without_profile_lists_nothing(self):
        self.assertEqual(provisioned_devices(Path("/nonexistent/C0Harness.xcarchive")), [])


class DylibValidationTests(unittest.TestCase):
    def test_missing_dylib_is_refused(self):
        with self.assertRaises(SystemExit):
            validate_dylib(Path("/nonexistent/client-graph.dylib"))

    def test_linked_artifact_is_ios_arm64(self):
        if not DEFAULT_DYLIB.is_file():
            self.skipTest("no linked image present")
        facts = validate_dylib(DEFAULT_DYLIB)
        self.assertEqual(facts["platform"], "IOS")
        self.assertIn("arm64", facts["architectures"])
        self.assertEqual(len(facts["sha256"]), 64)
        self.assertGreater(facts["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
