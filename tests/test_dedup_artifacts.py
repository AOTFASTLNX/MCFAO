import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import dedup_artifacts


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class DedupArtifactsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, rel, payload, age=7200):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
        return path

    def test_identical_files_collapse_and_stay_readable(self):
        payload = b"mach-o" * 400_000
        first = self.write("a/client-graph.dylib", payload)
        second = self.write("b/client-graph.dylib", payload)

        summary = dedup_artifacts.run(
            root=str(self.root), min_age=0, min_bytes=0, dry=False
        )

        self.assertEqual(summary["replaced"], 1)
        self.assertEqual(summary["logicalBytes"], len(payload))
        self.assertTrue(first.is_file() and second.is_file())
        self.assertEqual(digest(first), digest(second))
        self.assertEqual(second.stat().st_size, len(payload))

    def test_canonical_copy_is_the_oldest(self):
        payload = b"x" * 200_000
        self.write("new/client-graph.dylib", payload, age=60)
        old = self.write("old/client-graph.dylib", payload, age=9000)

        summary = dedup_artifacts.run(
            root=str(self.root), min_age=0, min_bytes=0, dry=False
        )

        self.assertEqual(len(summary["files"]), 1)
        self.assertEqual(summary["files"][0]["canonical"], str(old))

    def test_recent_files_are_left_alone(self):
        payload = b"y" * 200_000
        self.write("a/client-graph.dylib", payload, age=5)
        self.write("b/client-graph.dylib", payload, age=5)

        summary = dedup_artifacts.run(
            root=str(self.root), min_age=900, min_bytes=0, dry=False
        )

        self.assertEqual(summary["replaced"], 0)
        self.assertGreater(summary["skipped"], 0)

    def test_different_content_is_not_merged(self):
        self.write("a/client-graph.dylib", b"a" * 200_000)
        self.write("b/client-graph.dylib", b"b" * 200_000)

        summary = dedup_artifacts.run(
            root=str(self.root), min_age=0, min_bytes=0, dry=False
        )

        self.assertEqual(summary["replaced"], 0)
        self.assertEqual(summary["logicalBytes"], 0)

    def test_second_run_is_a_no_op(self):
        payload = b"z" * 300_000
        self.write("a/client-graph.dylib", payload)
        self.write("b/client-graph.dylib", payload)
        self.write("c/client-graph.dylib", payload)

        first = dedup_artifacts.run(
            root=str(self.root), min_age=0, min_bytes=0, dry=False
        )
        second = dedup_artifacts.run(
            root=str(self.root), min_age=0, min_bytes=0, dry=False
        )

        self.assertEqual(first["replaced"], 2)
        # clones keep identical bytes, so the ledger is what stops a re-run
        # from re-reporting gigabytes it already collapsed
        self.assertEqual(second["replaced"], 0)
        self.assertEqual(second["logicalBytes"], 0)

    def test_dry_run_touches_nothing(self):
        payload = b"q" * 200_000
        paths = [
            self.write(f"d{i}/client-graph.dylib", payload) for i in range(3)
        ]
        before = [digest(p) for p in paths]
        stamps = [p.stat().st_mtime for p in paths]

        summary = dedup_artifacts.run(
            root=str(self.root), min_age=0, min_bytes=0, dry=True
        )

        self.assertEqual(summary["replaced"], 2)
        self.assertEqual([digest(p) for p in paths], before)
        self.assertEqual([p.stat().st_mtime for p in paths], stamps)

    def test_only_the_requested_suffix_is_considered(self):
        payload = b"w" * 200_000
        self.write("a/client-graph.dylib", payload)
        self.write("a/client-graph.jar", payload)

        summary = dedup_artifacts.run(
            root=str(self.root), min_age=0, min_bytes=0, dry=False
        )

        self.assertEqual(summary["replaced"], 0)


if __name__ == "__main__":
    unittest.main()
