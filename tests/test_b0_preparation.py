from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_b0 import jar_bytes
from run_b0_reference import negative_control_ok, sandbox_policy


class B0PreparationTests(unittest.TestCase):
    def test_jar_rejects_parent_escape(self):
        with self.assertRaises(ValueError):
            jar_bytes({"../escape": b"no"})

    def test_jar_rejects_absolute_or_windows_path(self):
        for path in ("/escape", "a\\b"):
            with self.assertRaises(ValueError):
                jar_bytes({path: b"no"})

    def test_nested_resource_bytes_round_trip(self):
        nested = jar_bytes({"resource.txt": b"nested-resource-v1\n"})
        parent = jar_bytes({"META-INF/jars/nested.jar": nested})
        with zipfile.ZipFile(io.BytesIO(parent)) as archive:
            with zipfile.ZipFile(io.BytesIO(archive.read("META-INF/jars/nested.jar"))) as child:
                self.assertEqual(child.read("resource.txt"), b"nested-resource-v1\n")

    def test_jar_bytes_are_stable_across_insertion_order(self):
        self.assertEqual(jar_bytes({"b": b"2", "a": b"1"}), jar_bytes({"a": b"1", "b": b"2"}))

    def test_unrelated_negative_failure_does_not_pass(self):
        self.assertFalse(negative_control_ok({"exitCode": 1, "timedOut": False}, "", "ClassNotFoundException"))

    def test_expected_negative_reason_passes(self):
        self.assertTrue(negative_control_ok({"exitCode": 1, "timedOut": False}, "",
                                           "java.lang.AssertionError: real Mixin did not change result to 42"))

    def test_timeout_or_success_never_passes_negative(self):
        reason = "AssertionError: real Mixin did not change result to 42"
        for code, timeout in [(0, False), (-9, True)]:
            self.assertFalse(negative_control_ok({"exitCode": code, "timedOut": timeout}, "", reason))

    def test_success_marker_rejects_negative(self):
        self.assertFalse(negative_control_ok({"exitCode": 1, "timedOut": False}, "B0_REPLAY_PASS\n",
                                            "AssertionError: real Mixin did not change result to 42"))

    def test_policy_grants_only_explicit_jars_and_work_writes(self):
        policy = sandbox_policy(Path('/task/work'), Path('/tools/jdk'), [Path('/libs/a"b.jar')])
        self.assertIn('(deny default)', policy)
        self.assertIn('(literal "/libs/a\\"b.jar")', policy)
        self.assertIn('(allow file-write* (subpath "/task/work") (literal "/dev/null"))', policy)
        self.assertNotIn('(allow network', policy)
        self.assertNotIn('(subpath "/Users")', policy)
        self.assertIn('(literal "/")', policy)
        self.assertNotIn('(subpath "/")', policy)


if __name__ == "__main__":
    unittest.main()
