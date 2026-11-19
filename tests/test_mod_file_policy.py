"""Shared macOS metadata policy and integration regressions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import desktop_workbench as w
from build_lwjgl_lite import filter_overlay_metadata
from import_instance import import_instance
from mcfao import Build, instance_files, tree_files, write_json
from mod_file_policy import clean_staged_metadata, is_metadata
from prepare_fabric_aot import mod_files
from test_desktop_workbench import jar_bytes


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.good = jar_bytes()

    def prism(self):
        source = self.root / 'prism'
        (source / 'mods').mkdir(parents=True)
        (source / 'mods/example.JAR').write_bytes(self.good)
        write_json(source / 'mmc-pack.json', {'components': [
            {'uid': 'net.minecraft', 'version': '26.1.2'},
            {'uid': 'net.fabricmc.fabric-loader', 'version': '0.19.3'}]})
        return source

    def pack(self, metadata=True, broken=False, remote=False):
        source = self.root / 'pack.mrpack'
        rows = []
        if remote:
            for name, data in [('mods/example.jar', self.good), ('mods/._example.jar', b'sidecar')]:
                rows.append({'path': name, 'fileSize': len(data), 'hashes': {
                    algo: hashlib.new(algo, data).hexdigest() for algo in ('sha1', 'sha512')},
                    'downloads': ['https://cdn.modrinth.com/' + Path(name).name]})
        with ZipFile(source, 'w') as archive:
            archive.writestr('modrinth.index.json', json.dumps({'formatVersion': 1, 'game': 'minecraft',
                'name': 'fixture', 'versionId': '1', 'dependencies': {
                    'minecraft': '26.1.2', 'fabric-loader': '0.19.3'}, 'files': rows}))
            if not remote:
                archive.writestr('overrides/mods/example.jar', b'broken' if broken else self.good)
            if metadata:
                for name in ['overrides/mods/._example.jar', 'overrides/.DS_Store',
                             'overrides/mods/__MACOSX/fake.jar', '__MACOSX/._pack',
                             'client-overrides/config/._settings.json']:
                    archive.writestr(name, b'not a ZIP')
        return source

    def assert_clean(self, root):
        self.assertTrue(all(not is_metadata(p.relative_to(root)) for p in root.rglob('*')))
        self.assertTrue(all(not is_metadata(name) for name in instance_files(root)))

    def test_local_scan_and_both_importers_preserve_jar_and_selection(self):
        source = self.prism()
        before = w.scan_pack(source)
        (source / 'mods/._example.jar').write_bytes(b'\x00\x05\x16\x07sidecar')
        (source / 'mods/.DS_Store').write_bytes(b'sidecar')
        (source / 'mods/__MACOSX').mkdir()
        (source / 'mods/__MACOSX/fake.jar').write_bytes(b'broken')
        after = w.scan_pack(source)
        self.assertFalse(after['fatal'])
        self.assertEqual(before['resources_fingerprint'], after['resources_fingerprint'])
        self.assertEqual(len(after['mods']), 1)
        self.assertEqual(mod_files(source / 'mods'), [source / 'mods/example.JAR'])
        cli = self.root / 'cli'
        import_instance(source, cli)
        selection = dict(source=before['source'], fingerprint=before['resources_fingerprint'],
                         included=[row['id'] for row in before['resources'] if row['default_selected']])
        _, gui = w.stage_source(source, self.root / 'gui', selection=selection)
        for folder in (cli, gui):
            self.assertEqual((folder / 'mods/example.JAR').read_bytes(), self.good)
            self.assert_clean(folder)

    def test_mrpack_macosx_import_and_stable_selection(self):
        source = self.pack(metadata=False)
        before = w.scan_pack(source)['resources_fingerprint']
        self.pack(metadata=True)
        self.assertEqual(before, w.scan_pack(source)['resources_fingerprint'])
        cli = self.root / 'cli'
        import_instance(source, cli)
        _, gui = w.stage_source(source, self.root / 'gui')
        for folder in (cli, gui):
            self.assertEqual((folder / 'mods/example.jar').read_bytes(), self.good)
            self.assert_clean(folder)
            self.assertFalse((folder / 'mods/__MACOSX').exists())
        with ZipFile(source, 'a') as archive:
            archive.writestr('overrides/config/settings.json', '{}')
        self.assertNotEqual(before, w.scan_pack(source)['resources_fingerprint'])

    def test_metadata_downloads_are_never_requested(self):
        source = self.pack(remote=True)
        calls = []
        def fetch(url, limit):
            calls.append(url)
            return self.good
        import_instance(source, self.root / 'cli', fetch)
        self.assertEqual(calls, ['https://cdn.modrinth.com/example.jar'])
        def gui_fetch(entry, target):
            calls.append(entry['path'])
            target.write_bytes(self.good)
        with patch.object(w, 'download', side_effect=gui_fetch):
            w.stage_source(source, self.root / 'gui')
        self.assertEqual(calls[-1], 'mods/example.jar')
        self.assertEqual(len(calls), 2)

    def test_real_broken_jars_remain_blocked_for_every_importer(self):
        for kind in ('prism', 'mrpack'):
            source = self.prism() if kind == 'prism' else self.pack(broken=True)
            if kind == 'prism': (source / 'mods/example.JAR').write_bytes(b'broken')
            report = w.scan_pack(source)
            self.assertTrue(report['fatal'])
            self.assertIn('INVALID_MOD_JAR', [row['code'] for row in report['findings']])
            for importer in (import_instance, w.stage_source):
                with self.assertRaises(ValueError):
                    importer(source, self.root / (kind + importer.__name__))

    def test_downloaded_broken_jar_with_valid_hash_is_blocked(self):
        source = self.pack(remote=True)
        with ZipFile(source) as archive:
            manifest = json.loads(archive.read('modrinth.index.json'))
        row = manifest['files'][0]
        row.update(fileSize=6, hashes={algo: hashlib.new(algo, b'broken').hexdigest() for algo in ('sha1', 'sha512')})
        with ZipFile(source, 'w') as archive:
            archive.writestr('modrinth.index.json', json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'metadata failed'):
            import_instance(source, self.root / 'cli', lambda *args: b'broken')
        with patch.object(w, 'download', side_effect=lambda entry, target: target.write_bytes(b'broken')):
            with self.assertRaisesRegex(ValueError, 'Mod 检查'):
                w.stage_source(source, self.root / 'gui')

    def test_fabric_metadata_and_member_crc_errors_are_reported(self):
        source = self.prism()
        jar = source / 'mods/example.JAR'
        with ZipFile(jar, 'w') as archive:
            archive.writestr('fabric.mod.json', '{broken')
        self.assertTrue(w.scan_pack(source)['fatal'])
        with ZipFile(jar, 'w') as archive:
            archive.writestr('fabric.mod.json', json.dumps({'id':'example', 'version':'1'}))
            archive.writestr('example.class', b'first-party test content')
        jar.write_bytes(jar.read_bytes().replace(b'first-party test content', b'Xirst-party test content', 1))
        self.assertTrue(w.scan_pack(source)['fatal'])

    def test_copy_generated_sidecars_are_cleaned_before_manifest_creation(self):
        source = self.prism()
        copy = w.shutil.copyfile
        def copying(src, dst, *args, **kwargs):
            result = copy(src, dst, *args, **kwargs)
            Path(dst).with_name('._' + Path(dst).name).write_bytes(b'sidecar')
            return result
        with patch.object(w.shutil, 'copyfile', side_effect=copying):
            _, game = w.stage_source(source, self.root / 'stage')
        self.assertFalse((game / 'mods/._example.JAR').exists())
        self.assertEqual((game / 'mods/example.JAR').read_bytes(), self.good)
        self.assert_clean(game)

    def test_appledouble_bytes_under_real_jar_name_are_invalid(self):
        source = self.prism()
        (source / 'mods/example.JAR').write_bytes(b'\x00\x05\x16\x07sidecar')
        report = w.scan_pack(source)
        self.assertTrue(report['fatal'])
        self.assertIn('INVALID_MOD_JAR', [row['code'] for row in report['findings']])

    def test_cleanup_preserves_real_files_links_and_instance_fingerprint(self):
        _, game = w.stage_source(self.prism(), self.root / 'stage')
        before = instance_files(game)
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / '._private.jar').write_bytes(b'preserve')
        (game / 'mods/._link').symlink_to(outside, target_is_directory=True)
        (game / 'mods/._example.JAR').write_bytes(b'sidecar')
        (game / '.DS_Store').write_bytes(b'sidecar')
        (game / '__MACOSX').mkdir()
        (game / '__MACOSX/ordinary.jar').write_bytes(self.good)
        self.assertEqual(before, instance_files(game))
        self.assertEqual(clean_staged_metadata(game), ['.DS_Store', 'mods/._example.JAR'])
        self.assertTrue((outside / '._private.jar').exists())
        self.assertTrue((game / 'mods/._link').is_symlink())
        self.assertEqual((game / '__MACOSX/ordinary.jar').read_bytes(), self.good)
        self.assertEqual(before, instance_files(game))
        (game / 'mods/example.JAR').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'): instance_files(game)
        (game / 'mods/new.jar').write_bytes(self.good)
        with self.assertRaisesRegex(ValueError, 'undeclared'): instance_files(game)

    def test_checkpoint_reuses_metadata_only_changes_and_rebuilds_real_changes(self):
        build = self.root / 'build'
        product = build / 'fixture/attempt/product'
        product.mkdir(parents=True)
        (product / 'example.jar').write_bytes(self.good)
        write_json(product.parent.parent / 'checkpoint.json', dict(key='fixture', argv=['unused'],
                   attempt='attempt', filesSHA256=tree_files(product)))
        (product / '._example.jar').write_bytes(b'sidecar')
        pipeline = Build(build, 'fixture')
        with patch('mcfao.capture', side_effect=AssertionError('cache unexpectedly rebuilt')):
            self.assertEqual(pipeline.step('fixture', ['unused']), product)
        (product / 'example.jar').write_bytes(b'changed')
        with patch('mcfao.capture', side_effect=RuntimeError('rebuild required')):
            with self.assertRaisesRegex(RuntimeError, 'rebuild required'):
                pipeline.step('fixture', ['unused'])

    def test_bundled_preflight_contains_shared_policy(self):
        repo = Path(__file__).resolve().parents[1]
        config = json.loads((repo / 'desktop/src-tauri/tauri.conf.json').read_text())
        self.assertEqual(config['bundle']['resources']['../../tools/mod_file_policy.py'], 'tools/mod_file_policy.py')

    def test_generated_lwjgl_overlay_filters_only_metadata(self):
        jar = self.root / 'lwjgl-ios.jar'
        with ZipFile(jar, 'w') as archive:
            archive.writestr('org/lwjgl/Fixture.class', b'fixture class')
            archive.writestr('org/lwjgl/._Fixture.class', bytes.fromhex('00051607'))
            archive.writestr('org/lwjgl/.ordinary-hidden', b'resource')
        filter_overlay_metadata(jar)
        with ZipFile(jar) as archive:
            self.assertEqual(archive.namelist(), ['org/lwjgl/Fixture.class', 'org/lwjgl/.ordinary-hidden'])
            self.assertEqual(archive.read('org/lwjgl/Fixture.class'), b'fixture class')
            self.assertIsNone(archive.testzip())
        clean = jar.read_bytes()
        filter_overlay_metadata(jar)
        self.assertEqual(jar.read_bytes(), clean)

    @unittest.skipUnless(Path('/usr/bin/rsync').is_file(), 'Requires the macOS resource-copy tool')
    def test_xcode_instance_seed_preserves_hidden_content_and_skips_metadata(self):
        source = self.root / 'source'
        (source / 'config/__MACOSX').mkdir(parents=True)
        for name in ('config/game.json', 'config/.ordinary-hidden', 'config/._game.json',
                     'config/.DS_Store', 'config/__MACOSX/game.json'):
            (source / name).write_bytes(b'data')
        script = Path(__file__).resolve().parents[1] / 'ios/C0Harness/embed_graphics_libraries.sh'
        target = self.root / 'target'
        subprocess.run(['/bin/sh', str(script)], check=True, capture_output=True, timeout=30,
                       env={'PATH': os.defpath, 'FAOT_INSTANCE_DATA_DIR': str(source), 'TARGET_BUILD_DIR': str(target),
                            'UNLOCALIZED_RESOURCES_FOLDER_PATH': 'Test.app'})
        seed = target / 'Test.app/instance-seed'
        self.assertEqual({p.relative_to(seed).as_posix() for p in seed.rglob('*') if p.is_file()},
                         {'config/game.json', 'config/.ordinary-hidden'})
        self.assertTrue((source / 'config/._game.json').is_file())


if __name__ == '__main__': unittest.main()
