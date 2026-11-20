"""Unified storage scanner: accuracy, safety and incremental behaviour."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import storage_events
import storage_index
import storage_scan
import storage_service


class ScannerAccuracyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def blob(self, path, size=8192):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x' * size)
        return path.stat().st_blocks * 512

    def test_allocated_bytes_match_lstat_for_every_engine(self):
        total = sum(self.blob(self.root / 'a' / f'f{i}', 4096 + i) for i in range(12))
        total += self.blob(self.root / 'a/b/c/deep.bin', 100_000)
        for bulk in (True, False):
            result = storage_scan.scan(self.root, bulk=bulk)
            self.assertEqual(result.bytes, total, f'bulk={bulk}')
            self.assertEqual(result.files, 13)
            self.assertEqual(result.dirs, 3)
            self.assertTrue(result.complete)

    def test_symbolic_links_are_counted_but_never_followed(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(outside, ignore_errors=True))
        (outside / 'secret.bin').write_bytes(b'z' * 8192)
        amount = self.blob(self.root / 'inside.bin')
        (self.root / 'link').symlink_to(outside)
        (self.root / 'dangling').symlink_to(self.root / 'missing')
        result = storage_scan.scan(self.root)
        self.assertEqual(result.bytes, amount)
        self.assertEqual(result.files, 1)
        self.assertTrue((outside / 'secret.bin').is_file())

    def test_hard_links_are_counted_once_across_roots(self):
        amount = self.blob(self.root / 'one/data.bin')
        (self.root / 'two').mkdir()
        os.link(self.root / 'one/data.bin', self.root / 'two/data.bin')
        seen = set()
        first = storage_scan.scan(self.root / 'one', seen_hardlinks=seen)
        second = storage_scan.scan(self.root / 'two', seen_hardlinks=seen)
        self.assertEqual(first.bytes, amount)
        self.assertEqual(second.bytes, 0)

    def test_very_deep_tree_does_not_recurse(self):
        # PATH_MAX bounds the real depth; the point is that a depth well past
        # Python's recursion limit is handled by the iterative walk.
        path = self.root
        depth = 0
        while len(str(path)) < 900:
            path = path / 'dd'
            depth += 1
        path.mkdir(parents=True)
        (path / 'leaf.bin').write_bytes(b'x' * 4096)
        self.assertGreater(depth, 200)
        result = storage_scan.scan(self.root)
        self.assertEqual(result.files, 1)
        self.assertEqual(result.dirs, depth)

    def test_unreadable_directory_is_reported_not_zeroed(self):
        self.blob(self.root / 'visible.bin')
        (self.root / 'locked').mkdir()
        self.blob(self.root / 'locked/hidden.bin')
        real = storage_scan.list_directory

        def deny(path, *args, **kwargs):
            if path.endswith('locked'):
                raise PermissionError('denied')
            return real(path, *args, **kwargs)

        with patch.object(storage_scan, 'list_directory', side_effect=deny):
            result = storage_scan.scan(self.root)
        self.assertFalse(result.complete)
        self.assertEqual(result.error_count, 1)
        self.assertTrue(result.errors)

    def test_cancellation_stops_the_walk(self):
        for index in range(20):
            self.blob(self.root / f'dir{index}' / 'file.bin')
        calls = {'n': 0}

        def cancel():
            calls['n'] += 1
            return calls['n'] > 3

        with self.assertRaises(storage_scan.ScanCancelled):
            storage_scan.scan(self.root, cancel=cancel)

    def test_progress_reports_files_dirs_and_current_path(self):
        self.blob(self.root / 'a/b/file.bin')
        seen = []
        storage_scan.scan(self.root, progress=seen.append, progress_interval=0)
        self.assertTrue(seen)
        last = seen[-1]
        self.assertIn('current', last)
        self.assertGreaterEqual(last['files'], 1)
        self.assertGreaterEqual(last['dirs'], 0)

    def test_largest_items_include_top_level_files(self):
        big = self.blob(self.root / 'archive.bin', 200_000)
        small = self.blob(self.root / 'nested/small.bin', 4096)
        result = storage_scan.scan(self.root)
        self.assertEqual(result.children['archive.bin'], big)
        self.assertEqual(result.children['nested'], small)


class IndexTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index_path = self.root / 'state/index.sqlite3'

    def test_reopening_an_index_keeps_nodes_and_snapshot(self):
        index = storage_index.open_index(self.index_path)
        index.upsert_root('/tmp/fixture', complete=1, engine=storage_scan.ENGINE_VERSION)
        root_id = index.root('/tmp/fixture')['id']
        index.replace_nodes(root_id, {'': (1, 2, 3, 4, 5, 6, 0, 0, 0, 0, 0, 0, 0, 1)})
        index.save_snapshot('key', {'managedBytes': 5})
        index.close()
        reopened = storage_index.open_index(self.index_path)
        self.assertEqual(reopened.snapshot('key')['managedBytes'], 5)
        self.assertIn('', reopened.nodes(root_id))
        reopened.close()

    def test_future_schema_is_rebuilt_instead_of_read(self):
        index = storage_index.open_index(self.index_path)
        index.upsert_root('/tmp/fixture')
        index.connect().execute('PRAGMA user_version=9999')
        index.close()
        rebuilt = storage_index.open_index(self.index_path)
        self.assertIsNone(rebuilt.root('/tmp/fixture'))
        self.assertEqual(rebuilt.stats()['schema'], storage_index.SCHEMA_VERSION)
        rebuilt.close()

    def test_corrupt_database_returns_no_index(self):
        self.index_path.parent.mkdir(parents=True)
        self.index_path.write_bytes(b'not a database at all' * 100)
        self.assertIsNone(storage_index.open_index(self.index_path))

    def test_invalidate_drops_only_the_changed_subtree(self):
        index = storage_index.open_index(self.index_path)
        root_id = index.upsert_root('/tmp/fixture')
        nodes = {rel: (1, 2, 3, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1)
                 for rel in ('', 'a', 'a/b', 'a/bc', 'c')}
        index.replace_nodes(root_id, nodes)
        index.invalidate(root_id, ['a/b'])
        remaining = set(index.nodes(root_id))
        self.assertEqual(remaining, {'', 'a', 'a/bc', 'c'})
        index.close()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.index_path = self.root / 'state/index.sqlite3'
        self.environment = patch.dict(os.environ, {
            'MCFAO_STORAGE_INDEX': str(self.index_path),
            'MCFAO_STORAGE_CONFIG': str(self.root / 'storage.json'),
            'MCFAO_CACHE_DIR': str(self.data / 'cache'),
            'MCFAO_BUILDS_DIR': str(self.data / 'builds'),
            'MCFAO_JOBS_DIR': str(self.data / 'jobs'),
            'MCFAO_RUST_DIR': str(self.data / 'rust'),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def blob(self, path, size=8192):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x' * size)
        return path.stat().st_blocks * 512

    def paths(self):
        return dict(cache=self.data / 'cache', builds=self.data / 'builds')

    def test_second_open_uses_the_snapshot_without_traversing(self):
        amount = self.blob(self.data / 'cache/blob.bin')
        first = storage_service.inventory(self.paths(), store=True)
        self.assertEqual(first['managedBytes'], amount)
        with patch.object(storage_scan, 'Scanner') as scanner:
            cached = storage_service.snapshot(self.paths())
        self.assertFalse(scanner.called)
        self.assertEqual(cached['managedBytes'], amount)
        self.assertEqual(cached['scanState'], 'cached')
        self.assertTrue(cached['cached'])

    def test_missing_role_is_reported_unavailable_not_empty(self):
        (self.data / 'cache').mkdir()
        # builds is deliberately left uncreated but is redirected below to a
        # disconnected link, which is a different situation from "never made".
        broken = self.data / 'builds'
        broken.symlink_to(self.root / 'disconnected')
        report = storage_service.inventory(self.paths())
        row = next(r for r in report['usage'] if r['role'] == 'builds')
        self.assertFalse(row['available'])
        self.assertTrue(report['warnings'])
        self.assertFalse((self.root / 'disconnected').exists())

    def test_cancelled_scan_never_commits(self):
        self.blob(self.data / 'cache/blob.bin')
        with self.assertRaises(storage_scan.ScanCancelled):
            storage_service.measure(self.paths(), cancel=lambda: True)
        self.assertIsNone(storage_service.snapshot(self.paths()))

    def test_incremental_refresh_only_walks_changed_directories(self):
        for index in range(8):
            self.blob(self.data / 'cache' / f'dir{index}' / 'file.bin')
        storage_service.inventory(self.paths(), store=True)
        index = storage_index.open_index()
        cursor = storage_events.current_event_id()
        if cursor is None:
            self.skipTest('FSEvents unavailable')
        for path in self.paths().values():
            index.upsert_root(str(path.resolve()), event_id=cursor, event_valid=1)
        index.close()
        time.sleep(0.15)
        self.blob(self.data / 'cache' / 'dir3' / 'extra.bin', 65536)
        time.sleep(0.25)
        updated = storage_service.refresh(self.paths())
        if updated is None:
            self.skipTest('journal replay reported a gap')
        full = storage_service.inventory(self.paths())
        self.assertEqual(updated['managedBytes'], full['managedBytes'])
        self.assertEqual(updated['files'], full['files'])
        self.assertTrue(updated['incremental'])
        # Only the changed directory is re-listed; the other seven leaves are
        # skipped. `walked` counts visited nodes, so compare the difference.
        self.assertGreaterEqual(updated['reused'], 7)
        self.assertLessEqual(updated['walked'] - updated['reused'], 3)

    def test_build_completion_invalidates_only_the_written_directory(self):
        for index in range(4):
            self.blob(self.data / 'cache' / f'dir{index}' / 'file.bin')
        storage_service.inventory(self.paths(), store=True)
        index = storage_index.open_index()
        root_id = index.root(str((self.data / 'cache').resolve()))['id']
        before = set(index.nodes(root_id))
        index.close()
        self.assertIn('dir2', before)
        storage_service.invalidate(self.paths(), [self.data / 'cache' / 'dir2'])
        index = storage_index.open_index()
        after = set(index.nodes(root_id))
        index.close()
        self.assertNotIn('dir2', after)
        # Only the affected subtree is dropped; everything else stays cached.
        self.assertEqual(after, before - {'dir2'})
        refreshed = storage_service.refresh(self.paths())
        self.assertIsNotNone(refreshed)
        full = storage_service.inventory(self.paths())
        self.assertEqual(refreshed['managedBytes'], full['managedBytes'])

    def test_refresh_falls_back_when_the_index_has_no_cursor(self):
        self.blob(self.data / 'cache/blob.bin')
        storage_service.inventory(self.paths(), store=True)
        index = storage_index.open_index()
        for path in self.paths().values():
            index.upsert_root(str(path.resolve()), event_id=None, event_valid=0)
        index.close()
        self.assertIsNone(storage_service.refresh(self.paths()))

    def test_commit_records_a_journal_cursor_for_the_next_refresh(self):
        self.blob(self.data / 'cache/blob.bin')
        storage_service.inventory(self.paths(), store=True)
        index = storage_index.open_index()
        record = index.root(str((self.data / 'cache').resolve()))
        index.close()
        if storage_events.current_event_id() is None:
            self.skipTest('FSEvents unavailable')
        self.assertEqual(record['event_valid'], 1)
        self.assertIsInstance(record['event_id'], int)


if __name__ == '__main__':
    unittest.main()
