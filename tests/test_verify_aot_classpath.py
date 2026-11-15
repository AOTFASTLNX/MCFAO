from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_aot_classpath import JAVA, parse_probe_output, verify_entries


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

    @unittest.skipUnless((JAVA / "java").is_file() and (JAVA / "javac").is_file(),
                         "Requires the pinned local Java toolchain")
    def test_reusable_member_probe_checks_a_selected_classpath(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "src/mod/Test.java"
            classes = root / "classes"
            source.parent.mkdir(parents=True)
            classes.mkdir()
            source.write_text("package mod; public final class Test { public void read() {} }")
            subprocess.run([str(JAVA / "javac"), "-d", str(classes), str(source)],
                           check=True, capture_output=True, timeout=60)
            report = verify_entries([classes], JAVA, verify_members=True, timeout=60)
        self.assertEqual(report["classes"], 1)
        self.assertEqual(report["unloadable"], 0)
        self.assertEqual(report["memberResolution"], True)
        self.assertEqual(report["status"], "PASS")
