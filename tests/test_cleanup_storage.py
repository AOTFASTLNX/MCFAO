import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import cleanup_storage as cleanup


class CleanupStorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.artifacts = self.root / 'artifacts'
        self.cache = self.root / 'cache'
        self.artifacts.mkdir()
        self.cache.mkdir()

    def make_build(self, name, status='SIGNED_DEVICE_APP', stages=('aot', 'package'), ipa=False):
        build = self.artifacts / name
        build.mkdir()
        (build / 'result.json').write_text(json.dumps({'status': status}))
        for stage in stages:
            directory = build / stage
            directory.mkdir()
            (directory / 'blob.bin').write_bytes(b'x' * 4096)
        if ipa:
            (build / 'FabricAOT.ipa').write_bytes(b'ipa')
        return build

    def plan(self, **kwargs):
        return cleanup.plan(data_root=self.root, **kwargs)

    def test_plan_is_read_only(self):
        build = self.make_build('build-a')
        before = sorted(p.name for p in build.rglob('*'))
        self.plan()
        self.assertEqual(before, sorted(p.name for p in build.rglob('*')))

    def test_cache_and_rust_are_separate_groups(self):
        (self.cache / 'upstream').mkdir()
        (self.cache / 'upstream' / 'jdk.tar.gz').write_bytes(b'y' * 2048)
        rust = self.root / 'desktop/src-tauri/target'
        rust.mkdir(parents=True)
        (rust / 'debug').write_bytes(b'z' * 1024)
        groups = {group['id']: group for group in self.plan()['groups']}
        self.assertIn('cache', groups)
        self.assertIn('rust', groups)
        self.assertEqual(groups['cache']['count'], 1)
        self.assertEqual(groups['rust']['count'], 1)

    def test_build_with_ipa_is_never_offered_for_removal(self):
        self.make_build('old-with-ipa', ipa=True)
        for index in range(3):
            self.make_build(f'old-{index}')
        plan = self.plan(keep_builds=0)
        offered = [item['path'] for group in plan['groups']
                   if group['id'] == 'builds' for item in group['items']]
        self.assertFalse(any('old-with-ipa' in path for path in offered))

    def test_recent_builds_are_kept(self):
        builds = [self.make_build(f'build-{index}') for index in range(3)]
        for offset, build in enumerate(builds):
            build.touch()
            import os
            os.utime(build, (1000 + offset, 1000 + offset))
        plan = self.plan(keep_builds=1)
        offered = {Path(item['path']).name for group in plan['groups']
                   if group['id'] == 'builds' for item in group['items']}
        self.assertEqual(offered, {'build-0', 'build-1'})

    def test_intermediates_skip_finished_ipa_builds(self):
        self.make_build('done-build', ipa=True)
        self.make_build('partial-build', status='UNSIGNED_DEVICE_APP')
        plan = self.plan(keep_builds=5)
        paths = [item['path'] for group in plan['groups']
                 if group['id'] == 'intermediates' for item in group['items']]
        self.assertTrue(paths)
        self.assertFalse(any('done-build' in path for path in paths))
        self.assertTrue(any('partial-build' in path for path in paths))

    def test_running_build_blocks_cleanup(self):
        jobs = self.artifacts / 'desktop-jobs' / 'abc123'
        jobs.mkdir(parents=True)
        (jobs / 'job.json').write_text(json.dumps({'state': 'running', 'pid': 4242,
                                                   'build': str(self.artifacts / 'live')}))
        with patch('cleanup_storage.subprocess.run') as run:
            run.return_value.stdout = 'python3 desktop_workbench.py run-job'
            plan = self.plan()
        self.assertTrue(plan['blocked'])
        with self.assertRaises(ValueError):
            cleanup.apply(data_root=self.root, groups=['cache'])

    def test_stale_process_does_not_block(self):
        jobs = self.artifacts / 'desktop-jobs' / 'abc123'
        jobs.mkdir(parents=True)
        (jobs / 'job.json').write_text(json.dumps({'state': 'running', 'pid': 4242}))
        with patch('cleanup_storage.subprocess.run') as run:
            run.return_value.stdout = ''
            plan = self.plan()
        self.assertFalse(plan['blocked'])
        self.assertEqual(plan['activeJobs'][0]['state'], 'running')
        self.assertFalse(plan['activeJobs'][0]['alive'])

    def test_apply_removes_only_selected_group(self):
        (self.cache / 'graphics').mkdir()
        (self.cache / 'graphics' / 'blob').write_bytes(b'q' * 4096)
        build = self.make_build('keep-me')
        result = cleanup.apply(data_root=self.root, groups=['cache'])
        self.assertEqual(result['status'], 'STORAGE_CLEANED')
        self.assertFalse((self.cache / 'graphics').exists())
        self.assertTrue(build.is_dir())
        self.assertTrue((build / 'result.json').is_file())

    def test_unknown_group_is_refused(self):
        self.make_build('one')
        with self.assertRaises(ValueError):
            cleanup.apply(data_root=self.root, groups=['everything'])

    def test_symlinked_directory_is_not_followed(self):
        outside = self.root.parent / (self.root.name + '-outside')
        outside.mkdir()
        self.addCleanup(lambda: [p.unlink() for p in outside.iterdir()] + [outside.rmdir()])
        (outside / 'secret').write_bytes(b'keep')
        (self.cache / 'upstream').symlink_to(outside, target_is_directory=True)
        plan = self.plan()
        cache = next((g for g in plan['groups'] if g['id'] == 'cache'), None)
        self.assertIsNone(cache)
        self.assertTrue((outside / 'secret').is_file())

    def test_missing_data_root_is_reported(self):
        code = cleanup.main(['plan', '--data-root', str(self.root / 'absent')])
        self.assertEqual(code, 2)

    def test_apply_requires_groups(self):
        self.assertEqual(cleanup.main(['apply', '--data-root', str(self.root)]), 2)

    def test_builds_under_mcfao_subdirectory_are_found(self):
        nested = self.artifacts / 'mcfao'
        nested.mkdir()
        build = nested / 'cli-build'
        build.mkdir()
        (build / 'result.json').write_text(json.dumps({'status': 'SIGNED_DEVICE_APP'}))
        (build / 'aot').mkdir()
        (build / 'aot' / 'blob').write_bytes(b'a' * 1024)
        plan = self.plan()
        paths = [item['path'] for group in plan['groups']
                 if group['id'] == 'intermediates' for item in group['items']]
        self.assertTrue(any('cli-build' in path for path in paths))

    def test_removing_a_build_keeps_its_manifest(self):
        build = self.make_build('old-build', ipa=False)
        (build / 'inputs.json').write_text('{}')
        cleanup.apply(data_root=self.root, groups=['builds'], keep_builds=0)
        self.assertTrue((build / 'result.json').is_file())
        self.assertTrue((build / 'inputs.json').is_file())
        self.assertFalse((build / 'aot').exists())
        self.assertFalse((build / 'package').exists())

    def test_build_cleanup_reports_actual_freed_bytes(self):
        build = self.make_build('old-build')
        (build / 'aot' / 'blob.bin').write_bytes(b'x' * 100_000)
        result = cleanup.apply(data_root=self.root, groups=['builds'], keep_builds=0)
        self.assertGreater(result['freedBytes'], 90_000)
        self.assertLessEqual(result['freedBytes'], result['freedBytes'])

    def test_nested_and_top_level_builds_are_both_counted(self):
        self.make_build('top-level')
        nested = self.artifacts / 'mcfao'
        nested.mkdir()
        other = nested / 'nested-build'
        other.mkdir()
        (other / 'result.json').write_text(json.dumps({'status': 'SIGNED_DEVICE_APP'}))
        paths = {Path(item['path']).name for group in self.plan()['groups']
                 if group['id'] == 'intermediates' for item in group['items']}
        self.assertIn('aot', paths)


if __name__ == '__main__':
    unittest.main()
