import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from test_desktop_workbench import jar_bytes, w
from import_instance import import_instance


class ModDownloadCacheTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.cache = self.root / 'compiler-cache/mods'
        self.cache.mkdir(parents=True)
        self.enterContext(patch.dict(os.environ, {'MCFAO_CACHE_DIR': str(self.cache.parent)}))
        self.jar = jar_bytes('cache_fixture')

    def pack(self, destination='mods/example.jar', *, name='pack', data=None, **fields):
        data = self.jar if data is None else data
        row = dict(path=destination, fileSize=len(data),
                   hashes={algorithm: hashlib.new(algorithm, data).hexdigest()
                           for algorithm in ('sha1', 'sha512')},
                   downloads=['https://cdn.modrinth.com/example.jar'])
        row.update(fields)
        source = self.root / (name + '.mrpack')
        with ZipFile(source, 'w') as archive:
            archive.writestr('modrinth.index.json', json.dumps(dict(
                formatVersion=1, game='minecraft', name=name, versionId='1', files=[row],
                dependencies={'minecraft': '26.1.2', 'fabric-loader': '0.19.3'})))
        return source

    def unexpected_download(self, *args):
        self.fail('an exact local Mod should not need the network')

    def test_existing_jar_matches_by_content_even_when_renamed(self):
        (self.cache / 'example.jar').write_bytes(bytes(len(self.jar)))
        original = self.cache / 'renamed.JAR'
        original.write_bytes(self.jar)
        pack = self.pack()
        messages = []
        with patch.object(w, 'download', side_effect=self.unexpected_download):
            _, game = w.stage_source(pack, self.root / 'gui', messages.append)
        cli = self.root / 'cli'
        import_instance(pack, cli, self.unexpected_download)
        original.unlink()
        for folder in (game, cli):
            self.assertEqual((folder / 'mods/example.jar').read_bytes(), self.jar)
        self.assertTrue(any('复用本地 Mod' in message for message in messages))
        self.assertEqual((self.cache / 'example.jar').read_bytes(), bytes(len(self.jar)))

    def test_download_is_reused_across_packs_and_repaired_after_corruption(self):
        object_path = self.cache / 'objects' / (hashlib.sha512(self.jar).hexdigest() + '.jar')
        original = self.pack()
        renamed = self.pack('mods/renamed.jar', name='other-pack')
        with patch.object(w, 'download', side_effect=lambda entry, target: target.write_bytes(self.jar)) as download:
            w.stage_source(original, self.root / 'first')
            _, game = w.stage_source(renamed, self.root / 'second')
        self.assertEqual(download.call_count, 1)
        self.assertEqual((game / 'mods/renamed.jar').read_bytes(), self.jar)
        self.assertEqual(object_path.read_bytes(), self.jar)

        object_path.write_bytes(bytes(len(self.jar)))  # Same size; SHA checks must catch it.
        cli = self.root / 'cli'
        with patch('import_instance.download', return_value=self.jar) as download:
            import_instance(renamed, cli, download)
        download.assert_called_once()
        self.assertEqual(object_path.read_bytes(), self.jar)
        self.assertEqual((cli / 'mods/renamed.jar').read_bytes(), self.jar)
        with patch.object(w, 'download', side_effect=self.unexpected_download):
            w.stage_source(original, self.root / 'third')

    def test_links_and_appledouble_do_not_supply_mods_or_redirect_cache_writes(self):
        outside = self.root / 'outside'
        outside.mkdir()
        blob = outside / (hashlib.sha512(self.jar).hexdigest() + '.jar')
        blob.write_bytes(self.jar)
        (self.cache / 'example.jar').symlink_to(blob)
        (self.cache / 'objects').symlink_to(outside, target_is_directory=True)
        (self.cache / '._example.jar').write_bytes(self.jar)
        with patch.object(w, 'download', side_effect=lambda entry, target: target.write_bytes(self.jar)) as download:
            _, game = w.stage_source(self.pack(), self.root / 'gui')
        download.assert_called_once()
        self.assertEqual((game / 'mods/example.jar').read_bytes(), self.jar)
        self.assertEqual(set(outside.iterdir()), {blob})
        self.assertEqual(blob.read_bytes(), self.jar)
        self.assertTrue((self.cache / 'objects').is_symlink())

    def test_matching_sha512_alone_does_not_bypass_sha1_or_cache_the_download(self):
        (self.cache / 'example.jar').write_bytes(self.jar)
        pack = self.pack(hashes={'sha1': '0' * 40, 'sha512': hashlib.sha512(self.jar).hexdigest()})
        with patch('import_instance.download', return_value=self.jar) as download:
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                import_instance(pack, self.root / 'cli', download)
        download.assert_called_once()
        self.assertFalse((self.cache / 'objects').exists())

    def test_matching_cached_bytes_still_run_mod_preflight(self):
        broken = b'not a jar'
        (self.cache / 'example.jar').write_bytes(broken)
        pack = self.pack(data=broken)
        with patch.object(w, 'download', side_effect=self.unexpected_download):
            with self.assertRaisesRegex(ValueError, 'Mod 检查'):
                w.stage_source(pack, self.root / 'gui')
        with self.assertRaisesRegex(ValueError, 'Mod metadata failed preflight'):
            import_instance(pack, self.root / 'cli', self.unexpected_download)
