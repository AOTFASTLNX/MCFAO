import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mcfao
from renderer_profile import libraries, config_names, validate_runtime

class RendererProfileTests(unittest.TestCase):
    def test_gl41_config_does_not_require_native_metal_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            names = set(mcfao.CONFIG_PATHS) - {"metal", "shaders"}
            names.update(config_names("gl41"))
            config = root / "config.json"
            config.write_text(json.dumps({key: str(root) for key in names}))
            self.assertNotIn("metal", mcfao.load_config(config, "gl41"))
            with self.assertRaises(ValueError):
                mcfao.load_config(config, "metal")

    def test_gl41_contract_rejects_missing_libraries_and_does_not_read_metal_shaders(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp); frameworks = app / "Frameworks"; frameworks.mkdir()
            for name in libraries("gl41"):
                (frameworks / name).touch()
            (app / "assets/indexes").mkdir(parents=True)
            (app / "assets/indexes/30.json").write_text("{}")
            (app / "assets/objects/aa").mkdir(parents=True)
            (app / "assets/objects/aa/object").write_bytes(b"fixture")
            with patch("build_c0_harness.validate_dylib") as validate:
                validate_runtime(app, "gl41")
                self.assertEqual(validate.call_count, 7)
                (frameworks / "libOSMesa.8.dylib").unlink()
                with self.assertRaisesRegex(ValueError, "libOSMesa"):
                    validate_runtime(app, "gl41")

    def test_placeholder_and_host_libraries_cannot_pass_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp); directory = app / "Frameworks"; directory.mkdir()
            for name in libraries("gl41"):
                (directory / name).write_bytes(b"not a dylib")
            with self.assertRaises((ValueError, OSError, SystemExit)):
                validate_runtime(app, "gl41")

    def test_unsigned_gl41_xcode_argv_is_literal_and_uses_distinct_bundle(self):
        argv = mcfao.device_xcode(Path("/tmp/stage with spaces"), Path("/tmp/assets"),
                                  renderer="gl41", unsigned=True, bundle_id="org.fabricaot.integration.gl41")
        self.assertIn("CODE_SIGNING_ALLOWED=NO", argv)
        self.assertIn("FAOT_RENDERER=gl41", argv)
        self.assertIn("PRODUCT_BUNDLE_IDENTIFIER=org.fabricaot.integration.gl41", argv)
        self.assertIn("FAOT_GRAPHICS_NATIVE_DIR=/tmp/stage with spaces", argv)

    def test_gl41_patch_preserves_split_chain_and_rejects_tampering(self):
        from bootstrap_toolchain import sha256
        from probe_client_graph import verify_split_runtime_input
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); split = root / "split"; split.mkdir(); patched = root / "gl41"; patched.mkdir()
            original = split / "client.jar"; original.write_bytes(b"split fixture")
            (split / "result.json").write_text(json.dumps({"status": "SPLIT", "outputJarSHA256": sha256(original),
                "classes": [{"methodsSplit": 1, "finalFieldsUnfinalised": 2}]}))
            jar = patched / "client.jar"; jar.write_bytes(b"patched fixture")
            (patched / "result.json").write_text(json.dumps({"status": "GL41_CLIENT_PATCHED",
                "outputJarSHA256": sha256(jar), "client": str(original), "clientSHA256": sha256(original)}))
            self.assertEqual(verify_split_runtime_input(jar)["split"]["finalFieldsUnfinalised"], 2)
            original.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                verify_split_runtime_input(jar)
