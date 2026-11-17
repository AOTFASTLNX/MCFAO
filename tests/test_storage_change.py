import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import storage_change as change
import storage_config as config


class StorageChangeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = patch.dict(os.environ, {'MCFAO_STORAGE_CONFIG': str(self.root / 'settings.json')})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.old = {role: self.root / ('old-' + role) for role in config.ROLES}
        self.new = {role: str(self.root / 'chosen' / role) for role in config.ROLES}
        config.save_paths({k: str(v) for k, v in self.old.items()}, self.root)
        for path in self.old.values():
            path.mkdir()
            (path / 'file.bin').write_bytes(b'fixture contents')

    def plan(self):
        return change.plan(self.new, self.root)

    def apply(self, policy):
        return change.apply(self.new, policy, self.plan()['token'], self.root)

    def test_plan_is_read_only_and_lists_all_roles(self):
        before = (self.root / 'settings.json').read_bytes()
        plan = self.plan()
        self.assertEqual(len(plan['rows']), 4)
        self.assertEqual([r['count'] for r in plan['rows']], [1] * 4)
        self.assertEqual(before, (self.root / 'settings.json').read_bytes())
        self.assertFalse((self.root / 'chosen').exists())

    def test_keep_only_saves_paths(self):
        self.apply('keep')
        self.assertTrue(all((path / 'file.bin').exists() for path in self.old.values()))
        self.assertTrue(all(not Path(path).exists() for path in self.new.values()))

    def test_migration_verifies_files_and_remaps_task_metadata(self):
        job = self.old['jobs'] / 'a' / 'job.json'
        job.parent.mkdir()
        job.write_text(json.dumps({'folder': str(job.parent), 'build': str(self.old['builds'] / 'build'), 'request': {'config': str(self.old['jobs'] / 'configs/a.json')}}))
        (self.old['builds'] / 'game.ipa').write_bytes(b'retain identical bytes')
        result = self.apply('migrate')
        self.assertEqual(result['migration'], 'VERIFIED')
        self.assertTrue(all(not list(path.iterdir()) for path in self.old.values()))
        self.assertTrue(all((Path(path) / 'file.bin').read_bytes() == b'fixture contents' for path in self.new.values()))
        data = json.loads((Path(self.new['jobs']) / 'a/job.json').read_text())
        self.assertEqual(data['build'], self.new['builds'] + '/build')
        self.assertEqual((Path(self.new['builds']) / 'game.ipa').read_bytes(), b'retain identical bytes')

    def test_delete_only_reviewed_roots_and_unlinks_internal_links(self):
        private = self.root / 'private.txt'
        private.write_text('retain')
        (self.old['cache'] / 'outside').symlink_to(private)
        self.apply('delete')
        self.assertTrue(all(path.exists() and not list(path.iterdir()) for path in self.old.values()))
        self.assertEqual(private.read_text(), 'retain')

    def test_stale_plan_cannot_delete_changed_contents(self):
        token = self.plan()['token']
        (self.old['cache'] / 'new').write_text('new content')
        with self.assertRaisesRegex(ValueError, '变化'):
            change.apply(self.new, 'delete', token, self.root)
        self.assertEqual(config.storage_paths(self.root), self.old)
        self.assertTrue((self.old['cache'] / 'new').exists())

    def test_existing_target_is_never_overwritten(self):
        target = Path(self.new['builds'])
        target.mkdir(parents=True)
        (target / 'user-file').write_text('retain')
        with self.assertRaisesRegex(ValueError, '目标已存在'):
            self.apply('migrate')
        self.assertTrue((target / 'user-file').exists())
        self.assertEqual(config.storage_paths(self.root), self.old)

    def test_copy_failure_keeps_originals_and_settings(self):
        with patch.object(change.shutil, 'copytree', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): self.apply('migrate')
        self.assertEqual(config.storage_paths(self.root), self.old)
        self.assertTrue(all((path / 'file.bin').exists() for path in self.old.values()))

    def test_verification_failure_keeps_originals(self):
        with patch.object(change, 'digest', side_effect=[b'original', b'bad']):
            with self.assertRaisesRegex(ValueError, '校验失败'): self.apply('migrate')
        self.assertEqual(config.storage_paths(self.root), self.old)

    def test_failed_settings_write_rolls_back_installed_copies(self):
        with patch.object(change, 'save_paths', side_effect=OSError('config failure')):
            with self.assertRaises(OSError): self.apply('migrate')
        self.assertTrue(all(not Path(path).exists() for path in self.new.values()))
        self.assertTrue(all((path / 'file.bin').exists() for path in self.old.values()))

    def test_overlapping_paths_are_rejected(self):
        self.new['cache'] = str(self.old['cache'] / 'inside')
        with self.assertRaisesRegex(ValueError, '互相包含'): self.plan()

    def test_absolute_links_into_migrated_roots_are_remapped(self):
        (self.old['cache'] / 'link').symlink_to(self.old['builds'] / 'file.bin')
        self.apply('migrate')
        link = Path(self.new['cache']) / 'link'
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_bytes(), b'fixture contents')

    def test_source_root_links_are_preserved(self):
        actual = self.old['cache']
        alias = self.root / 'cache-alias'
        alias.symlink_to(actual)
        config.save_paths({k: str(alias if k == 'cache' else v) for k, v in self.old.items()}, self.root)
        self.apply('migrate')
        self.assertTrue(alias.is_symlink())
        self.assertTrue(actual.is_dir())
        self.assertFalse(list(actual.iterdir()))

    def test_late_source_changes_are_retained_with_warning_after_switch(self):
        save = change.save_paths
        def save_and_modify(*args):
            result = save(*args)
            (self.old['cache'] / 'late-file').write_text('retain')
            return result
        with patch.object(change, 'save_paths', side_effect=save_and_modify):
            result = self.apply('delete')
        self.assertTrue(result['warnings'])
        self.assertTrue((self.old['cache'] / 'late-file').exists())
        self.assertEqual(str(config.storage_paths(self.root)['cache']), self.new['cache'])

    def test_external_metadata_link_cannot_be_modified(self):
        private = self.root / 'private.json'
        private.write_text('{"retain":true}')
        task = self.old['jobs'] / 'task'
        task.mkdir()
        (task / 'job.json').symlink_to(private)
        with self.assertRaisesRegex(ValueError, '元数据'):
            self.apply('migrate')
        self.assertEqual(private.read_text(), '{"retain":true}')
        self.assertEqual(config.storage_paths(self.root), self.old)


if __name__ == '__main__': unittest.main()
