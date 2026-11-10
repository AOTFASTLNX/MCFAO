"""Regression tests for the method-splitter driver's provenance checks.

The splitter itself is Java (`compiler/splitter`) and is exercised by the recorded experiments under
`artifacts/c0/client-split-*`. These tests cover the Python side: that a substituted ASM library or a
stale/missing build record cannot be used silently, and that the record keeps only the counters it
claims to keep.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from bootstrap_toolchain import sha256  # noqa: E402
from split_methods import classpath_from_file, report_counts, splitter_classpath  # noqa: E402


class SplitterClasspathTest(unittest.TestCase):
    def make_tool(self, root: Path, status="BUILT", tamper=False):
        tool = root / "tool"
        (tool / "classes").mkdir(parents=True)
        jar = root / "asm-9.9.jar"
        jar.write_bytes(b"asm-bytes")
        record = {
            "status": status,
            "classesDirectory": str(tool / "classes"),
            "asmJars": [{"name": "asm-9.9.jar", "path": str(jar), "sha256": sha256(jar)}],
        }
        (tool / "result.json").write_text(json.dumps(record))
        if tamper:
            jar.write_bytes(b"substituted-asm")
        return tool

    def test_verified_libraries_produce_the_classpath(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool = self.make_tool(root)
            value = splitter_classpath(tool)
            self.assertEqual(value, "%s:%s" % (tool / "classes", root / "asm-9.9.jar"))

    def test_missing_record_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                splitter_classpath(Path(tmp) / "absent")

    def test_failed_build_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = self.make_tool(Path(tmp), status="FAILED")
            with self.assertRaises(SystemExit):
                splitter_classpath(tool)

    def test_substituted_library_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = self.make_tool(Path(tmp), tamper=True)
            with self.assertRaises(SystemExit):
                splitter_classpath(tool)

    def test_record_without_libraries_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / "tool"
            tool.mkdir()
            (tool / "result.json").write_text(json.dumps({"status": "BUILT", "classesDirectory": "x"}))
            with self.assertRaises(SystemExit):
                splitter_classpath(tool)


class ClasspathFileTest(unittest.TestCase):
    def test_colon_separated_paths_survive_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            listing = Path(tmp) / "cp.txt"
            listing.write_text("/a b/one.jar:/c/two.jar")
            self.assertEqual(classpath_from_file(listing), [Path("/a b/one.jar"), Path("/c/two.jar")])

    def test_trailing_separator_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            listing = Path(tmp) / "cp.txt"
            listing.write_text("/only.jar:")
            self.assertEqual(classpath_from_file(listing), [Path("/only.jar")])


class ReportCountsTest(unittest.TestCase):
    def test_only_documented_counters_are_kept(self):
        report = {"classesRead": 3, "classesWritten": 2, "classesRejected": 1,
                  "methodsSplit": 4, "partsCreated": 9, "classes": [{"huge": "detail"}], "scope": "x"}
        self.assertEqual(report_counts(report),
                         {"classesRead": 3, "classesWritten": 2, "classesRejected": 1,
                          "methodsSplit": 4, "partsCreated": 9})

    def test_absent_counters_stay_absent(self):
        self.assertEqual(set(report_counts({"classesRead": 1})),
                         {"classesRead", "classesWritten", "classesRejected", "methodsSplit",
                          "partsCreated"})


if __name__ == "__main__":
    unittest.main()
