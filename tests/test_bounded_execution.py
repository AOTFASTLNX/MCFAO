"""Exercise the resource controller with harmless first-party processes."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_b0_reference import execute


class BoundedExecutionTests(unittest.TestCase):
    def test_captures_both_streams_and_exit_status(self):
        with tempfile.TemporaryDirectory(prefix="fabricaot-process-") as name:
            root = Path(name)
            record = execute([sys.executable, "-B", "-c",
                "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)"],
                root / "evidence", root, timeout=5)
            self.assertEqual(record["exitCode"], 7)
            self.assertFalse(record["timedOut"])
            self.assertEqual((root / "evidence/stdout.log").read_text(), "out\n")
            self.assertEqual((root / "evidence/stderr.log").read_text(), "err\n")

    def test_deadline_survives_closed_output_streams(self):
        with tempfile.TemporaryDirectory(prefix="fabricaot-process-") as name:
            root = Path(name)
            started = time.monotonic()
            record = execute([sys.executable, "-B", "-c",
                "import os,time; os.close(1); os.close(2); time.sleep(60)"],
                root / "evidence", root, timeout=1)
            self.assertTrue(record["timedOut"])
            self.assertNotEqual(record["exitCode"], 0)
            self.assertLess(time.monotonic() - started, 8)

    def test_rejects_invalid_budgets_before_creating_evidence(self):
        with tempfile.TemporaryDirectory(prefix="fabricaot-process-") as name:
            root = Path(name)
            with self.assertRaises(ValueError):
                execute([], root / "evidence", root, timeout=0)
            self.assertFalse((root / "evidence").exists())


if __name__ == "__main__":
    unittest.main()
