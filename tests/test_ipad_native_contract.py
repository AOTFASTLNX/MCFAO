"""Regression contract for the native iPad bundle and input state machine.

The real-device failure was caused by the *processed* app plist declaring
UIDeviceFamily=[1] while the project source claimed 1,2. These tests cover the
build inputs, the processed-bundle verifier and the platform-independent pointer
policy; they are not device acceptance.
"""
from __future__ import annotations

import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verify_ipad_bundle import check_info  # noqa: E402

HARNESS = ROOT / "ios/C0Harness"
DEVICE_XCCONFIG = (HARNESS / "WorldDevice.xcconfig").read_text()
WORLD_PLIST = plistlib.loads((HARNESS / "Info.WorldSimulator.plist").read_bytes())
C0_PLIST = plistlib.loads((HARNESS / "Info.plist").read_bytes())
PROJECT = (HARNESS / "C0Harness.xcodeproj/project.pbxproj").read_text()
EMBED = (HARNESS / "embed_graphics_libraries.sh").read_text()
WORKFLOW = (ROOT / ".github/workflows/ipados-pointer-build.yml").read_text()


def valid_info() -> dict:
    return {
        "CFBundleIdentifier": "org.fabricaot.research.c0.kexin",
        "CFBundleExecutable": "C0Harness",
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "MinimumOSVersion": "17.0",
        "UIDeviceFamily": [1, 2],
        "UIRequiresFullScreen": True,
        "UIApplicationSupportsIndirectInputEvents": True,
        "UISupportedInterfaceOrientations~ipad": [
            "UIInterfaceOrientationLandscapeLeft",
            "UIInterfaceOrientationLandscapeRight",
        ],
    }


class NativeIPadBundleContractTests(unittest.TestCase):
    def test_worlddevice_xcconfig_targets_both_families(self):
        self.assertRegex(DEVICE_XCCONFIG, r"(?m)^TARGETED_DEVICE_FAMILY\s*=\s*1,2\s*$")
        self.assertRegex(DEVICE_XCCONFIG, r"(?m)^INFOPLIST_FILE\s*=\s*Info\.WorldSimulator\.plist\s*$")

    def test_worlddevice_info_plist_is_a_native_ipad_bundle(self):
        # UIDeviceFamily is injected by Xcode from TARGETED_DEVICE_FAMILY. Keeping a
        # hand-written copy triggers an Xcode warning and is overwritten anyway.
        self.assertNotIn("UIDeviceFamily", WORLD_PLIST)
        self.assertIs(WORLD_PLIST["UIRequiresFullScreen"], True)
        self.assertIs(WORLD_PLIST["UIApplicationSupportsIndirectInputEvents"], True)
        self.assertIn(
            "UIInterfaceOrientationLandscapeLeft",
            WORLD_PLIST["UISupportedInterfaceOrientations~ipad"],
        )

    def test_c0_info_plist_is_also_ipad_native(self):
        self.assertNotIn("UIDeviceFamily", C0_PLIST)
        self.assertIs(C0_PLIST["UIRequiresFullScreen"], True)
        self.assertIs(C0_PLIST["UIApplicationSupportsIndirectInputEvents"], True)

    def test_project_has_no_iphone_only_app_configuration(self):
        values = re.findall(r"TARGETED_DEVICE_FAMILY\s*=\s*([^;]+);", PROJECT)
        self.assertTrue(values)
        for value in values:
            self.assertIn(value.strip().strip('"'), {"1,2", "2,1"}, value)

    def test_embed_phase_does_not_reject_device_builds(self):
        self.assertNotIn("FabricAOTWorld requires an iOS Simulator destination", PROJECT)
        self.assertNotIn("FabricAOTWorld requires an iOS Simulator destination", EMBED)
        self.assertIn("verify_ipad_bundle.sh", EMBED)

    def test_processed_plist_verifier_rejects_the_observed_failure(self):
        broken = valid_info()
        broken["UIDeviceFamily"] = [1]
        errors = check_info(broken)
        self.assertTrue(any("UIDeviceFamily" in error for error in errors), errors)

    def test_processed_plist_verifier_rejects_missing_fullscreen_and_input_keys(self):
        broken = valid_info()
        del broken["UIRequiresFullScreen"]
        del broken["UIApplicationSupportsIndirectInputEvents"]
        errors = check_info(broken)
        self.assertTrue(any("UIRequiresFullScreen" in error for error in errors), errors)
        self.assertTrue(
            any("UIApplicationSupportsIndirectInputEvents" in error for error in errors), errors
        )

    def test_processed_plist_verifier_accepts_the_contract(self):
        self.assertEqual(check_info(valid_info()), [])


class PointerPolicyFixtureTests(unittest.TestCase):
    def test_pointer_policy_state_transitions(self):
        clang = shutil.which("clang")
        if not clang:
            self.skipTest("clang is not available")
        with tempfile.TemporaryDirectory(prefix="mcfao-pointer-") as directory:
            binary = Path(directory) / "pointer-state-test"
            compile_result = subprocess.run(
                [
                    clang,
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-g",
                    "-fsanitize=address,undefined",
                    "-I",
                    str(ROOT / "ios/glfw-lite"),
                    str(ROOT / "ios/glfw-lite/pointer_state.c"),
                    str(ROOT / "interop/graphics/pointer_state_test.c"),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run_result.returncode, 0, run_result.stderr)
            self.assertIn("POINTER_STATE_PASS", run_result.stdout)

    def test_ci_runs_the_policy_fixture_and_processed_bundle_check(self):
        self.assertIn("pointer_state_test.c", WORKFLOW)
        self.assertIn("POINTER_STATE_PASS", WORKFLOW)
        self.assertIn("tools/verify_ipad_bundle.py", WORKFLOW)
        self.assertRegex(WORKFLOW, r"grep -Eq ['\"]TARGETED_DEVICE_FAMILY = 1,2['\"]")


if __name__ == "__main__":
    unittest.main()
