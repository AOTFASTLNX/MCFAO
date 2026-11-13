from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_aot_classpath import parse_probe_output


class ClasspathProbeResultTests(unittest.TestCase):
    def test_failed_child_never_passes(self):
        with self.assertRaisesRegex(RuntimeError, "exited"):
            parse_probe_output(SimpleNamespace(returncode=1, stdout="", stderr="failure"), 100)

    def test_incomplete_output_never_passes(self):
        for text in ("", "SUMMARY\t0\t0", "SUMMARY\t100\t1"):
            with self.subTest(text=text), self.assertRaisesRegex(RuntimeError, "Incomplete"):
                parse_probe_output(SimpleNamespace(returncode=0, stdout=text, stderr=""), 100)

    def test_complete_result_preserves_exact_failure(self):
        failures, total, failed = parse_probe_output(SimpleNamespace(
            returncode=0, stdout="FAIL\tmod.Broken\tVerifyError: constructor\nSUMMARY\t2\t1", stderr=""), 2)
        self.assertEqual((total, failed), (2, 1))
        self.assertEqual(failures, [{"class": "mod.Broken", "cause": "VerifyError: constructor"}])
