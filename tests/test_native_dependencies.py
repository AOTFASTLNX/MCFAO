import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_dependencies as d
import desktop_workbench as w


def image(payload=b'first-party fixture', platform=2):
    return struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 0, 6, 1, 24, 0, 0) + struct.pack('<IIIIII', 0x32, 24, platform, 0x110000, 0x110000, 0) + payload


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'config.json'
        self.paths = {}
        w.CANCELLED = False
        for key, _, builder, *_ in d.SPECS:
            path = self.root / ('tools/' + builder + '.py')
            path.parent.mkdir(exist_ok=True)
            path.write_text('first-party ' + key)
        source = self.root / 'ios/glfw-lite/window.c'
        source.parent.mkdir(parents=True)
        source.write_text('first-party source')
        prepared = self.root / 'prepared'
        prepared.mkdir()
        client = prepared / '26.1.2.jar'
        client.write_bytes(b'first-party client fixture')
        w.write_json(prepared / 'result.json', dict(status='PREPARED', referenceLibraries=[
            dict(path=str(client), sha256=d.sha256(client))]))
        self.paths['prepared'] = prepared
        for key in ('glfw', 'lwjgl'):
            directory = self.root / ('old-' + key)
            self.emit(directory, key, self.paths)
            self.paths[key] = directory
        w.write_json(self.config, {k: str(v) for k, v in self.paths.items()})
        self.original = self.config.read_bytes()
        self.updates = []
        registration = patch('graphics_common.register_tree')
        registration.start()
        self.addCleanup(registration.stop)

    def emit(self, directory, key, paths, payload=b'fixture'):
        directory.mkdir()
        for name in d.BY_KEY[key][5]:
            (directory / name).write_bytes(image(payload))
        report = dict(status=d.BY_KEY[key][3], target='arm64-apple-ios17.0',
                      sourcesSHA256=d.sources(self.root, key), binarySHA256=d.sha256(directory / d.BY_KEY[key][5][0]))
        if key == 'glfw':
            report['clientSHA256'] = d.sha256(self.paths['prepared'] / '26.1.2.jar')
        if key == 'lwjgl':
            report['glfwLibrarySHA256'] = d.sha256(paths['glfw'] / 'libglfw.dylib')
            report['overlaysSHA256'] = {}
            for name in ('lwjgl-ios.jar', 'lwjgl-glfw-ios.jar', 'lwjgl-stb-ios.jar', 'lwjgl-openal-ios.jar'):
                path = directory / name
                path.write_bytes(b'first-party jar fixture')
                report['overlaysSHA256'][str(path)] = d.sha256(path)
        if key == 'metal':
            report.update(glfwSHA256=d.sha256(paths['glfw'] / 'libglfw.dylib'),
                          jarSHA256=d.sha256(directory / 'metal-backend.jar'),
                          metallibSHA256=d.sha256(directory / 'fabricaot-present.metallib'))
        w.write_json(directory / 'result.json', report)

    def execute(self, argv, key):
        directory = Path(argv[argv.index('--output') + 1])
        paths = {**self.paths}
        if '--glfw-library' in argv:
            paths['glfw'] = Path(argv[argv.index('--glfw-library') + 1]).parent
        self.emit(directory, key, paths, payload=b'new source native result')

    def rebuild(self, keys, execute=None, cancelled=lambda: False):
        return d.rebuild(self.root, self.config, keys, self.root / 'new-output', execute or self.execute,
                         cancelled, lambda **v: self.updates.append(v), w.write_json)

    def test_inventory_verifies_current_sources_and_explicit_changed_files(self):
        self.assertEqual(d.inspect(self.root, self.paths, 'glfw')['state'], 'current')
        source = self.root / 'ios/glfw-lite/window.c'
        source.write_text('changed')
        row = d.inspect(self.root, self.paths, 'glfw')
        self.assertEqual(row['state'], 'stale')
        self.assertEqual(row['changedFiles'], ['ios/glfw-lite/window.c'])

    def test_inventory_missing_invalid_and_wrong_architecture(self):
        self.assertEqual(d.inspect(self.root, {}, 'glfw')['state'], 'missing')
        binary = self.paths['glfw'] / 'libglfw.dylib'
        binary.write_bytes(b'tampered')
        self.assertEqual(d.inspect(self.root, self.paths, 'glfw')['state'], 'invalid')
        binary.unlink()
        self.assertEqual(d.inspect(self.root, self.paths, 'glfw')['state'], 'missing')
        binary.write_bytes(image(platform=7))
        report = d.read(self.paths['glfw'] / 'result.json')
        report['binarySHA256'] = d.sha256(binary)
        w.write_json(self.paths['glfw'] / 'result.json', report)
        self.assertIn('not an iOS', d.inspect(self.root, self.paths, 'glfw')['reasons'][0])

    def test_glfw_changed_without_following_lwjgl_is_rejected_before_aot(self):
        self.rebuild(['glfw'])
        paths = d.config_paths(self.config)
        row = d.inspect(self.root, paths, 'lwjgl')
        self.assertEqual(row['state'], 'stale')
        self.assertIn('GLFW-lite 哈希已变更', ' '.join(row['reasons']))
        with self.assertRaisesRegex(ValueError, 'LWJGL-lite'):
            d.preflight(self.root, self.config)

    def test_lwjgl_is_stale_even_before_glfw_binary_rebuilt(self):
        (self.root / 'ios/glfw-lite/window.c').write_text('changed source')
        row = next(r for r in d.inventory(self.root, self.config)['libraries'] if r['key'] == 'lwjgl')
        self.assertEqual(row['state'], 'stale')
        with self.assertRaisesRegex(ValueError, '请先重建 GLFW-lite'):
            self.rebuild(['lwjgl'])
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_dependency_order_is_topological_for_any_selection(self):
        order = d.plan(list(reversed(d.BY_KEY)))
        for key in order:
            for dep in d.BY_KEY[key][4]:
                self.assertLess(order.index(dep), order.index(key))
        self.assertEqual(d.plan(['lwjgl', 'glfw']), ['glfw', 'lwjgl'])

    def test_unavailable_optional_input_fails_before_any_compile(self):
        called = []
        with patch.object(d, 'command', side_effect=ValueError('shader inputs absent')):
            with self.assertRaisesRegex(ValueError, '输入不完整'):
                self.rebuild(['glfw'], lambda argv, key: called.append(key))
        self.assertEqual(called, [])
        self.assertFalse((self.root / 'new-output').exists())

    def test_metal_detects_changed_lwjgl_overlay_even_when_native_binary_unchanged(self):
        self.rebuild(['metal'])
        paths = d.config_paths(self.config)
        native_hash = d.sha256(paths['lwjgl'] / 'liblwjgl.dylib')
        overlay = paths['lwjgl'] / 'lwjgl-ios.jar'
        overlay.write_bytes(b'updated first-party overlay')
        report = d.read(paths['lwjgl'] / 'result.json')
        report['overlaysSHA256'][str(overlay)] = d.sha256(overlay)
        w.write_json(paths['lwjgl'] / 'result.json', report)
        row = d.inspect(self.root, paths, 'metal')
        self.assertEqual(d.sha256(paths['lwjgl'] / 'liblwjgl.dylib'), native_hash)
        self.assertEqual(row['state'], 'stale')
        self.assertIn('依赖库哈希已变更', ' '.join(row['reasons']))

    def test_action_whitelist_rejects_injected_or_unknown_library(self):
        for keys in ([], ['sh'], ['glfw;touch /tmp/bad'], ['glfw', 'glfw'], 'glfw', [None]):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                d.plan(keys)
        self.assertNotIn('run-job', w.PUBLIC_ACTIONS)
        self.assertIn('dependencies', w.PUBLIC_ACTIONS)

    def test_success_switches_config_and_binds_lwjgl_to_new_glfw(self):
        called = []
        def execute(argv, key):
            called.append(key)
            self.execute(argv, key)
        self.rebuild(['lwjgl', 'glfw'], execute)
        self.assertEqual(called, ['glfw', 'lwjgl'])
        paths = d.config_paths(self.config)
        self.assertEqual(d.inspect(self.root, paths, 'lwjgl')['state'], 'current')
        manifest = d.read(paths['lwjgl'] / d.MANIFEST)
        self.assertEqual(manifest['dependencies']['glfw']['libglfw.dylib'], d.sha256(paths['glfw'] / 'libglfw.dylib'))
        self.assertTrue((self.paths['glfw'] / 'libglfw.dylib').is_file())
        self.assertEqual(paths['glfw'], self.root / 'new-output/glfw')

    def test_failure_in_second_build_keeps_original_config_and_partial_outputs(self):
        def execute(argv, key):
            if key == 'lwjgl':
                raise ValueError('fixture compiler failed')
            self.execute(argv, key)
        with self.assertRaisesRegex(ValueError, 'compiler failed'):
            self.rebuild(['glfw', 'lwjgl'], execute)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertTrue((self.root / 'new-output/glfw/result.json').is_file())

    def test_cancel_before_commit_keeps_old_configuration(self):
        stopped = False
        def execute(argv, key):
            nonlocal stopped
            self.execute(argv, key)
            stopped = True
        with self.assertRaises(InterruptedError):
            self.rebuild(['glfw'], execute, lambda: stopped)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_modified_source_during_build_does_not_commit(self):
        def execute(argv, key):
            self.execute(argv, key)
            (self.root / 'ios/glfw-lite/window.c').write_text('changed during compile')
        with self.assertRaisesRegex(ValueError, '构建过程中'):
            self.rebuild(['glfw'], execute)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_corrupt_new_binary_cannot_replace_selected_configuration(self):
        def execute(argv, key):
            self.execute(argv, key)
            directory = Path(argv[argv.index('--output') + 1])
            (directory / 'libglfw.dylib').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, '哈希校验失败'):
            self.rebuild(['glfw'], execute)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_runtime_report_cannot_override_pinned_osmesa_hash(self):
        with self.assertRaisesRegex(ValueError, '固定版本哈希'):
            d.artifacts(self.root, 'gl41', {'filesSHA256': {'libOSMesa.8.dylib': 'tampered'}})

    def test_external_config_edit_is_preserved(self):
        def execute(argv, key):
            self.execute(argv, key)
            self.config.write_text('{"userEdit":"preserved"}')
        with self.assertRaisesRegex(ValueError, '配置已被修改'):
            self.rebuild(['glfw'], execute)
        self.assertEqual(d.read(self.config), {'userEdit': 'preserved'})

    def test_added_and_removed_sources_are_detected_after_managed_build(self):
        self.rebuild(['glfw'])
        (self.root / 'ios/glfw-lite/window.c').unlink()
        (self.root / 'ios/glfw-lite/new.c').write_text('new')
        row = d.inspect(self.root, d.config_paths(self.config), 'glfw')
        self.assertEqual(row['changedFiles'], ['ios/glfw-lite/new.c', 'ios/glfw-lite/window.c'])

    def test_workbench_start_dispatch_uses_existing_job_mechanism(self):
        with patch.object(w, 'start_dependencies', return_value={'id': 'fixture'}) as start:
            self.assertEqual(w._start({'kind': 'dependencies'}), {'id': 'fixture'})
            start.assert_called_once()

    def test_dependency_job_uses_selected_storage_for_outputs_and_records(self):
        paths = dict(builds=self.root / 'chosen/builds', jobs=self.root / 'chosen/jobs')
        request = dict(workspace=str(self.root), config=str(self.config), dependencyKeys=['glfw'])
        with patch.object(w, 'workspace_path', return_value=self.root), patch.object(w, 'storage_paths', return_value=paths), patch.object(w, 'require_mount'), patch.object(w, 'require_space'), patch.object(w, 'history', return_value=[]), patch.object(w.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 12345
            job = w.start_dependencies(request)
        self.assertTrue(Path(job['build']).is_relative_to(paths['builds'] / 'native-dependencies'))
        self.assertTrue(Path(job['folder']).is_relative_to(paths['jobs']))
        self.assertTrue((Path(job['folder']) / 'job.json').is_file())

    def test_workbench_rejects_stale_dependencies_before_process_launch(self):
        (self.root / 'ios/glfw-lite/window.c').write_text('changed')
        request = dict(workspace=str(self.root), config=str(self.config), loader='vanilla', unsigned=True, output=str(self.root / 'ipa'))
        with patch.object(w, 'ROOT', self.root), patch.object(w, 'workspace_path', return_value=self.root), patch.object(w, 'config_summary'), patch.object(w.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'GLFW-lite'):
                w._start(request)
        spawn.assert_not_called()

    def test_workbench_worker_success_switches_config_after_validation(self):
        folder = self.root / 'job'
        folder.mkdir()
        (folder / 'launch').touch()
        path = folder / 'job.json'
        w.write_json(path, dict(id='a' * 32, kind='dependencies', state='queued', build=str(self.root / 'outputs'),
                               request=dict(config=str(self.config), dependencyKeys=['glfw', 'lwjgl'])))
        with patch.object(w, 'ROOT', self.root), patch.object(w, 'require_mount'), patch.object(w.signal, 'signal'), patch.object(w, 'execute', side_effect=lambda argv, folder, key, *args: self.execute(argv, key)):
            w.run_job(path)
        result = w.read_json(path)
        self.assertEqual(result['state'], 'succeeded', result.get('error'))
        self.assertEqual(result['dependencyProgress']['completed'], 2)
        self.assertEqual(result['configFields'], w.read_json(self.config))

    def test_workbench_worker_dispatch_and_failure_status(self):
        folder = self.root / 'job'
        folder.mkdir()
        (folder / 'launch').touch()
        path = folder / 'job.json'
        job = dict(id='a' * 32, kind='dependencies', state='queued', build=str(self.root / 'outputs'),
                   request=dict(config=str(self.config), dependencyKeys=['glfw']))
        w.write_json(path, job)
        with patch.object(w, 'require_mount'), patch.object(w.signal, 'signal'), patch.object(d, 'rebuild', side_effect=ValueError('compiler fixture failure')) as build:
            w.run_job(path)
        build.assert_called_once()
        self.assertEqual(w.read_json(path)['state'], 'failed')
        self.assertIn('compiler fixture failure', w.read_json(path)['error'])
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_workbench_catalog_dispatch_returns_inventory(self):
        with patch.object(sys, 'argv', ['desktop_workbench.py', 'dependencies', '--request', json.dumps({'config': str(self.config)})]), patch.object(w, 'workspace_path', return_value=self.root), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(w.main(), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data['libraries']), 7)


if __name__ == '__main__':
    unittest.main()
