import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bootstrap_toolchain import sha256
from capture import ROOT
from graphics_common import verify_gl41_bridge
from native_game_checks import DIAGNOSTIC_MARKERS, GAME_SYMBOLS, verify_game_image


class NativeGameChecks(unittest.TestCase):
    def test_entry_abi_without_gameplay_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image"
            image.write_bytes(b"run_main")
            with patch("native_game_checks.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout="_run_main")):
                with self.assertRaisesRegex(ValueError, "Minecraft_runTick"):
                    verify_game_image(image)

    def test_old_diagnostics_are_rejected_even_with_game_symbols(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image"
            image.write_bytes(b"diagnostics_start stallSeconds")
            with patch("native_game_checks.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=" ".join(GAME_SYMBOLS))):
                with self.assertRaisesRegex(ValueError, "tickStallSeconds"):
                    verify_game_image(image)

    def test_current_image_accepts_both_native_string_encodings(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image"
            for encoding in ("utf-8", "utf-16-le"):
                image.write_bytes(" ".join(DIAGNOSTIC_MARKERS).encode(encoding))
                with patch("native_game_checks.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=" ".join(GAME_SYMBOLS))):
                    self.assertEqual(verify_game_image(image)["status"], "GAME_CODE_PRESENT")

    def test_historical_bridge_report_requires_current_gl41_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            report = directory / "result.json"
            report.write_text(json.dumps({"status": "STATIC_JNI_BRIDGE_BUILT", "sourcesSHA256": {}}))
            with self.assertRaisesRegex(ValueError, "predates"):
                verify_gl41_bridge(directory)
            names = ("compiler/lwjgl-lite/Overlay.java", "compiler/lwjgl-lite/src/org/lwjgl/system/Library.java")
            report.write_text(json.dumps({"sourcesSHA256": {name: sha256(ROOT / name) for name in names}}))
            verify_gl41_bridge(directory)
