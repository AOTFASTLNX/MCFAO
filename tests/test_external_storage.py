import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import external_storage


class ExternalStorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.volume = self.root / 'K'
        self.data = self.volume / 'MCFAO-data'
        self.data.mkdir(parents=True)
        self.work = self.root / 'MCFAO'
        self.work.mkdir()
        rows = [{'link': 'artifacts/mcfao', 'external': 'artifacts/mcfao'},
                {'link': '.cache', 'external': 'cache'}]
        self.config = self.work / 'external-storage.json'
        self.config.write_text(json.dumps({'volume': '/Volumes/K', 'directories': rows}))
        for row in rows:
            external = self.data / row['external']
            external.mkdir(parents=True)
            link = self.work / row['link']
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(external, target_is_directory=True)

    def check(self):
        return external_storage.mount_check(VOLUME=self.volume, DATA=self.data,
                                           CONFIG=self.config, ROOT=self.work)

    def test_mounted_links_are_available(self):
        with patch('external_storage.os.path.ismount', return_value=True):
            status = self.check()
        self.assertTrue(status['available'])
        self.assertEqual(len(status['links']), 2)

    def test_unmounted_volume_is_unavailable(self):
        with patch('external_storage.os.path.ismount', return_value=False):
            status = self.check()
        self.assertFalse(status['available'])
        self.assertEqual(status['reason'], 'volume-not-mounted')

    def test_data_directory_must_exist(self):
        import shutil
        shutil.rmtree(self.data)
        with patch('external_storage.os.path.ismount', return_value=True):
            status = self.check()
        self.assertEqual(status['reason'], 'data-directory-missing')

    def test_missing_external_directory_blocks_the_build(self):
        (self.data / 'cache').rename(self.data / 'cache-absent')
        with patch('external_storage.os.path.ismount', return_value=True):
            status = self.check()
        self.assertEqual(status['reason'], 'missing-links')
        self.assertIn('cache', status['missing'])

    def test_plain_directory_instead_of_link_is_reported(self):
        link = self.work / '.cache'
        link.unlink()
        link.mkdir()
        with patch('external_storage.os.path.ismount', return_value=True):
            status = self.check()
        self.assertIn('.cache:not-a-symlink', status['missing'])

    def test_require_mount_pauses_with_action_context(self):
        with patch('external_storage.os.path.ismount', return_value=False):
            with self.assertRaises(external_storage.ExternalStorageUnavailable) as caught:
                external_storage.require_mount('mcfao build', VOLUME=self.volume,
                                               DATA=self.data, CONFIG=self.config, ROOT=self.work)
        self.assertIn('mcfao build', str(caught.exception))
        self.assertIn('PAUSED', str(caught.exception))

    def test_require_mount_returns_status_when_ready(self):
        with patch('external_storage.os.path.ismount', return_value=True):
            status = external_storage.require_mount('mcfao build', VOLUME=self.volume,
                                                   DATA=self.data, CONFIG=self.config, ROOT=self.work)
        self.assertTrue(status['available'])

    def test_absent_personal_manifest_imposes_no_mount_requirement(self):
        self.config.unlink()
        with patch('external_storage.os.path.ismount', return_value=False):
            status = external_storage.mount_check(CONFIG=self.config, ROOT=self.work)
        self.assertTrue(status['available'])
        self.assertNotIn('volume-not-mounted', status.get('reason', ''))
        self.assertEqual(status['links'], [])


if __name__ == '__main__':
    unittest.main()
