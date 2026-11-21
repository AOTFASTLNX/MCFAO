import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_gl41_mesa as builder
import fetch_gl41_runtime as runtime


def image(marker):
    return struct.pack("<IiiIIIII", 0xFEEDFACF, 0x0100000C, 0, 6, 1, 24, 0, 0) + struct.pack("<IIIIII", 0x32, 24, 2, 0x110000, 0x110000, 0) + marker


class MesaRuntimeTests(unittest.TestCase):
    def test_unpatched_report_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source provenance"):
            runtime.validate_runtime(Path("/nonexistent"), {"filesSHA256": {e["name"]:e["sha256"] for e in runtime.FILES}})

    def test_provenance_and_actual_bytes_must_agree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("libOSMesa.8.dylib", "libMoltenVK.dylib"):
                (root / name).write_bytes(image(name.encode()))
            mesa_hash = builder.digest(root / "libOSMesa.8.dylib")
            entries = [{"name":p.name,"sha256":builder.digest(p)} for p in root.iterdir()]
            report = {"mesa":{"source":builder.MESA,"headers":builder.MVK_HEADERS,
                              "patchIdentity":builder.patch_identity(),"sha256":mesa_hash},
                      "filesSHA256":{"libOSMesa.8.dylib":mesa_hash}}
            with patch.object(runtime, "FILES", entries):
                runtime.validate_runtime(root, report)
                for key, replacement in (("patchIdentity","old"),("source",{}),("headers",{}),("sha256","wrong")):
                    modified = copy.deepcopy(report); modified["mesa"][key] = replacement
                    with self.assertRaises(ValueError): runtime.validate_runtime(root, modified)
                (root / "libOSMesa.8.dylib").write_bytes(image(b"tampered"))
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    runtime.validate_runtime(root, report)

    def test_cached_result_cannot_hide_missing_or_corrupt_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "libOSMesa.8.dylib"; binary.write_bytes(b"verified fixture")
            (root / "result.json").write_text(json.dumps({"patchIdentity":builder.patch_identity(),"sha256":builder.digest(binary)}))
            self.assertEqual(builder.build(root), binary.resolve())
            binary.unlink()
            with self.assertRaisesRegex(ValueError, "binary changed"): builder.build(root)
            binary.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "binary changed"): builder.build(root)

    def test_macho_platform_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.dylib"; path.write_bytes(b"short")
            with self.assertRaises(ValueError): runtime.macho_platform(path)


if __name__ == "__main__":
    unittest.main()
