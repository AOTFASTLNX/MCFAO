"""Check CI prerequisite reporting without proprietary game files."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("worlddevice_inputs", ROOT / "tools/check_worlddevice_inputs.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WorldDeviceInputsTests(unittest.TestCase):
    def test_missing_empty_and_complete_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            inputs, assets = base / "input", base / "assets"
            with patch.object(module, "INPUT", inputs), patch.object(module, "ASSETS", assets):
                self.assertEqual(len(module.missing_inputs()), 8)
                for name in ("client-graph.dylib", "liblwjgl.dylib", "libfaot_metal.dylib",
                             "libopenal.dylib", "fabricaot-present.metallib", "fabricaot-shaders/index.json"):
                    path = inputs / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"x")
                index = assets / "indexes/30.json"
                index.parent.mkdir(parents=True)
                index.write_bytes(b"x")
                (assets / "objects").mkdir()
                self.assertEqual(module.missing_inputs(), [])
                index.write_bytes(b"")
                self.assertEqual(module.missing_inputs(), [index])


if __name__ == "__main__":
    unittest.main()
