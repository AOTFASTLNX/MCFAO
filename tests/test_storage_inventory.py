import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from storage_inventory import inventory


class StorageInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def blob(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x' * 8192)
        return path.stat().st_blocks * 512

    def test_capacity_is_grouped_by_filesystem_and_nested_roots_count_once(self):
        builds = self.root / 'builds'
        jobs = builds / 'jobs'
        a = self.blob(builds / 'aot/object')
        b = self.blob(jobs / 'job.json')
        report = inventory(dict(builds=builds, jobs=jobs))
        self.assertEqual([r['bytes'] for r in report['usage']], [a, b])
        self.assertEqual(report['managedBytes'], a + b)
        self.assertEqual(len(report['volumes']), 1)
        self.assertEqual(report['volumes'][0]['managedBytes'], a + b)
        self.assertGreater(report['volumes'][0]['totalBytes'], 0)

    def test_explicit_root_link_is_resolved_but_child_links_are_not_followed(self):
        cache = self.root / 'cache'
        amount = self.blob(cache / 'upstream/archive')
        outside = self.root / 'outside'
        self.blob(outside / 'private')
        (cache / 'linked-child').symlink_to(outside)
        linked = self.root / '.cache'
        linked.symlink_to(cache)
        report = inventory(dict(cache=linked))
        self.assertEqual(report['managedBytes'], amount)
        self.assertEqual(len(report['usage'][0]['items']), 1)
        self.assertEqual(report['usage'][0]['path'], str(linked))
        self.assertTrue((outside / 'private').exists())

    def test_same_root_alias_and_hardlinks_are_not_double_counted(self):
        amount = self.blob(self.root / 'cache/data')
        os.link(self.root / 'cache/data', self.root / 'cache/copy')
        report = inventory(dict(cache=self.root / 'cache', rust=self.root / 'cache'))
        self.assertEqual(report['managedBytes'], amount)
        self.assertTrue(report['warnings'])

    def test_disconnected_root_is_visible_without_creating_it(self):
        missing = self.root / 'absent'
        link = self.root / 'cache'
        link.symlink_to(missing)
        report = inventory(dict(cache=link))
        self.assertFalse(report['usage'][0]['available'])
        self.assertEqual(report['volumes'], [])
        self.assertTrue(report['warnings'])
        self.assertFalse(missing.exists())

    def test_looping_root_does_not_hide_other_roots(self):
        loop = self.root / 'loop'
        loop.symlink_to(loop)
        amount = self.blob(self.root / 'cache/blob')
        report = inventory(dict(rust=loop, cache=self.root / 'cache'))
        self.assertFalse(report['usage'][0]['available'])
        self.assertEqual(report['managedBytes'], amount)
        self.assertTrue(report['warnings'])

    def test_partial_scan_reports_error_instead_of_silently_claiming_empty(self):
        cache = self.root / 'cache'
        cache.mkdir()
        with patch('storage_inventory.os.scandir', side_effect=PermissionError('denied')):
            report = inventory(dict(cache=cache))
        self.assertIn('error', report['usage'][0])
        self.assertTrue(report['warnings'])

    def test_largest_items_are_sorted_and_bounded_without_truncating_total(self):
        total = sum(self.blob(self.root / 'cache' / str(i)) for i in range(15))
        report = inventory(dict(cache=self.root / 'cache'))
        row = report['usage'][0]
        self.assertEqual(row['itemCount'], 15)
        self.assertEqual(len(row['items']), 12)
        self.assertEqual(row['bytes'], total)

    def test_new_uncreated_directory_has_capacity_and_zero_usage(self):
        report = inventory(dict(jobs=self.root / 'future/jobs'))
        self.assertTrue(report['usage'][0]['available'])
        self.assertEqual(report['usage'][0]['bytes'], 0)
        self.assertEqual(len(report['volumes']), 1)
        self.assertFalse((self.root / 'future').exists())


if __name__ == '__main__':
    unittest.main()
