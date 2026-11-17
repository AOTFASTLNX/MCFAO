from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import acquire_client
import bundle_source
import desktop_workbench as w
import first_run
import host_tools
import storage_config as storage
import verified_download as download
import build_method_splitter as splitter
import prepare_b0


class TemporaryInputs(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.env = patch.dict(os.environ, {'MCFAO_STORAGE_CONFIG': str(self.root / 'settings.json')})
        self.env.start()
        self.addCleanup(self.env.stop)


class StorageConfigurationTests(TemporaryInputs):
    def test_four_defaults_preserve_legacy_paths(self):
        paths = storage.storage_paths(self.root)
        self.assertEqual(paths['cache'], self.root / '.cache')
        self.assertEqual(paths['jobs'], self.root / 'artifacts/desktop-jobs')
        self.assertEqual(paths['rust'], self.root / 'desktop/src-tauri/target')

    def test_packaged_source_uses_user_directories(self):
        (self.root / 'bundle-manifest.json').write_text('{}')
        self.assertTrue(all(not p.is_relative_to(self.root) for p in storage.storage_paths(self.root).values()))

    def test_save_only_updates_configuration_and_retains_old_job_discovery(self):
        old = self.root / 'artifacts/desktop-jobs'
        old.mkdir(parents=True)
        (old / 'retained.txt').write_text('old task')
        paths = {k: str(self.root / ('new-' + k)) for k in storage.ROLES}
        result = storage.save_paths(paths, self.root)
        self.assertEqual(result['migration'], 'NONE')
        self.assertTrue((old / 'retained.txt').is_file())
        self.assertTrue(all(not Path(v).exists() for v in paths.values()))
        self.assertIn(old, storage.job_roots(self.root))
        self.assertEqual(storage.storage_paths(self.root)['jobs'], Path(paths['jobs']))

    def test_same_volume_requirements_are_added_together(self):
        with patch.object(storage.shutil, 'disk_usage', return_value=SimpleNamespace(free=10)):
            report = storage.space_report({'cache': self.root / 'a', 'builds': self.root / 'b'}, {'cache': 6, 'builds': 6})
        self.assertFalse(report['ready'])
        self.assertEqual(report['volumes'][0]['required'], 12)
        self.assertFalse((self.root / 'a').exists())

    def test_insufficient_space_blocks_before_any_directory_creation(self):
        with patch.object(storage.shutil, 'disk_usage', return_value=SimpleNamespace(free=1)):
            with self.assertRaisesRegex(ValueError, 'Insufficient'):
                storage.require_space({'cache': self.root / 'missing'})
        self.assertFalse((self.root / 'missing').exists())

    def test_absent_external_volume_and_broken_links_are_rejected(self):
        with patch.object(storage.os.path, 'ismount', return_value=False):
            with self.assertRaisesRegex(ValueError, 'not mounted'): storage.existing_parent('/Volumes/not-mounted/cache')
        (self.root / 'broken').symlink_to(self.root / 'absent')
        with self.assertRaisesRegex(ValueError, 'Disconnected'): storage.existing_parent(self.root / 'broken/child')

    def test_unmounted_guard_keeps_pause_exit_code(self):
        import external_storage
        with patch.object(external_storage, 'mount_check', return_value={'available':False,'reason':'volume-not-mounted'}), patch('builtins.print'):
            self.assertEqual(external_storage.main(['--json']), 3)

    def test_overlapping_and_source_directories_are_rejected(self):
        values = {k: str(self.root / k) for k in storage.ROLES}
        for bad in (dict(values, jobs=values['cache']), dict(values, jobs=values['cache'] + '/jobs'), dict(values, cache=str(self.root / 'tools/cache'))):
            with self.assertRaises(ValueError): storage.save_paths(bad, self.root)
        self.assertFalse((self.root / 'settings.json').exists())

    def test_old_job_remains_accessible_after_changing_jobs_location(self):
        old = self.root / 'artifacts/desktop-jobs' / ('a' * 32) / 'job.json'
        old.parent.mkdir(parents=True)
        old.write_text('{}')
        storage.save_paths({k: str(self.root / ('new-' + k)) for k in storage.ROLES}, self.root)
        self.assertEqual(w.job_path(self.root, 'a' * 32), old)

    def test_custom_directory_cleanup_is_read_only_until_a_separate_plan_is_confirmed(self):
        storage.save_paths({k: str(self.root / ('new-' + k)) for k in storage.ROLES}, self.root)
        with patch.object(w.cleanup_storage, 'apply') as apply:
            report = w.storage('storage-plan', {})
            self.assertTrue(report['blocked'])
            self.assertEqual(report['groups'], [])
            with self.assertRaises(ValueError): w.storage('storage-clean', {'groups':['cache']})
        apply.assert_not_called()


class UnsignedWorkflowTests(TemporaryInputs):
    def test_unsigned_request_needs_no_export_plist_or_team(self):
        with patch.object(w, 'workspace_path', return_value=self.root), patch.object(w, 'config_summary'), patch.object(w.native_dependencies, 'preflight'):
            request = dict(workspace=str(self.root), loader='vanilla', unsigned=True, team='invalid', config='unused', output=str(self.root / 'output'))
            self.assertEqual(w.validate_request(request), self.root)
            with self.assertRaises(KeyError): w.validate_request(dict(request, unsigned=False))
            with self.assertRaises(ValueError): w.validate_request(dict(request, unsigned='yes'))

    def test_unsigned_build_flag_reaches_cli(self):
        with patch.object(w, 'execute') as execute:
            error, _ = w.compile_build(['python', 'mcfao.py'], self.root, dict(loader='vanilla', config=str(self.root / 'config'), unsigned=True), self.root / 'build', None, None, lambda **_: None, {})
        self.assertIsNone(error)
        self.assertIn('--unsigned', execute.call_args.args[0])

    def ipa_fixture(self):
        content = b'first-party fixture'
        ipa = self.root / 'build.ipa'
        with zipfile.ZipFile(ipa, 'w') as z: z.writestr('Payload/Test.app/fixture', content)
        result = dict(status='UNSIGNED_DEVICE_APP', signature='UNSIGNED', ipa=str(ipa), app='package/Test.app',
                      bytes=ipa.stat().st_size, sha256=hashlib.sha256(ipa.read_bytes()).hexdigest(),
                      appFilesSHA256={'fixture': hashlib.sha256(content).hexdigest()})
        (self.root / 'result.json').write_text(json.dumps(result))
        return ipa, result

    def test_unsigned_ipa_verifies_every_member_against_application(self):
        ipa, result = self.ipa_fixture()
        with patch('mcfao.verify') as verify:
            self.assertEqual(w.verify_unsigned_build(self.root), result)
            verify.assert_called_once_with(self.root, None)
        with zipfile.ZipFile(ipa, 'w') as z: z.writestr('Payload/Test.app/fixture', b'modified')
        with patch('mcfao.verify'), self.assertRaisesRegex(ValueError, 'differs'):
            w.verify_unsigned_build(self.root)

    def test_unsigned_ipa_outside_build_is_rejected_before_native_verification(self):
        _, result = self.ipa_fixture()
        result['ipa'] = str(self.root.parent / 'escape.ipa')
        (self.root / 'result.json').write_text(json.dumps(result))
        with patch('mcfao.verify') as verify, self.assertRaises((ValueError, FileNotFoundError)):
            w.verify_unsigned_build(self.root)
        verify.assert_not_called()

    def test_unsigned_worker_finishes_without_export_archive_or_signing_commands(self):
        _, result = self.ipa_fixture()
        folder = self.root / 'job'; folder.mkdir(); (folder / 'launch').touch()
        request = dict(unsigned=True, existingBuild=str(self.root), loader='vanilla', output=str(self.root))
        path = folder / 'job.json'
        path.write_text(json.dumps(dict(id='a'*32, request=request, build=str(self.root), state='queued')))
        with patch.object(w, 'validate_request'), patch.object(w, 'verify_unsigned_build', return_value=result), patch.object(w, 'execute') as execute, patch.object(w.signal, 'signal'):
            w.run_job(path)
        execute.assert_not_called()
        saved = json.loads(path.read_text())
        self.assertEqual(saved['state'], 'succeeded')
        self.assertEqual(saved['signature'], 'UNSIGNED')
        self.assertIn('不能直接装机', saved['warning'])


class DownloadAndBootstrapTests(TemporaryInputs):
    def bootstrap_fixture(self):
        compiler = self.root / 'source/compiler'; compiler.mkdir(parents=True)
        paths = {key: self.root / 'storage' / key for key in storage.ROLES}
        paths['cache'].mkdir(parents=True)
        state = paths['jobs'] / 'setup/status.json'; state.parent.mkdir(parents=True)
        specs = []
        def archive(relative, files):
            path = paths['cache'] / relative; path.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(path, 'w:gz') as tar:
                for name, content in files.items():
                    entry = tarfile.TarInfo(name); entry.size = len(content)
                    tar.addfile(entry, io.BytesIO(content))
            spec = dict(url='https://repo.maven.apache.org/' + path.name, size=path.stat().st_size,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            specs.append((Path(relative), spec))
            return spec
        archive('toolchains/graal.tar.gz', {'jdk/Contents/Home/bin/native-image':b'never executed'})
        (compiler / 'toolchains.lock.json').write_text(json.dumps({'graalvm':{'file':'graal.tar.gz'}}))
        upstream = {}
        for key, commit, prefix in [('jdk','abc','labs-openjdk'),('graal','def','graal')]:
            spec = archive(f'upstream/{key}-{commit}.tar.gz', {f'{prefix}-{commit}/LICENSE':b'fixture notice'})
            upstream[key] = dict(commit=commit,archiveSHA256=spec['sha256'],licenseFiles=['LICENSE'])
        (compiler / 'upstream.lock.json').write_text(json.dumps(upstream))
        return paths, state, specs

    def test_first_run_worker_downloads_and_extracts_data_without_executing_scripts(self):
        paths, state, specs = self.bootstrap_fixture()
        with patch.object(first_run, 'ROOT', self.root / 'source'), patch.object(first_run, 'storage_paths', return_value=paths), patch.object(first_run, 'download_specs', return_value=specs), patch.object(first_run, 'require_mount'), patch.object(first_run, 'require_space'), patch.object(first_run.subprocess, 'Popen') as process, patch.object(acquire_client, 'acquire') as game:
            self.assertEqual(first_run.run(state), 0)
        process.assert_not_called(); game.assert_not_called()
        result = json.loads(state.read_text())
        self.assertEqual(result['state'], 'ready')
        self.assertEqual(result['completedBytes'], sum(spec['size'] for _, spec in specs))
        self.assertTrue((paths['cache'] / 'upstream/jdk.json').is_file())
        self.assertFalse((paths['cache'] / 'owned-client').exists())

    def test_first_run_worker_rejects_modified_archives_and_preserves_them(self):
        paths, state, specs = self.bootstrap_fixture()
        target = paths['cache'] / specs[0][0]; target.write_bytes(b'modified archive')
        with patch.object(first_run, 'ROOT', self.root / 'source'), patch.object(first_run, 'storage_paths', return_value=paths), patch.object(first_run, 'download_specs', return_value=specs), patch.object(first_run, 'require_mount'), patch.object(first_run, 'require_space'):
            self.assertEqual(first_run.run(state), 2)
        self.assertEqual(json.loads(state.read_text())['state'], 'failed')
        self.assertEqual(target.read_bytes(), b'modified archive')

    def response(self, content, url='https://repo.maven.apache.org/input'):
        response = io.BytesIO(content); response.url = url; response.status = 200
        return response

    def test_verified_download_checks_size_hash_and_cached_content(self):
        content = b'pinned first-party test data'
        spec = dict(url='https://repo.maven.apache.org/input', size=len(content), sha256=hashlib.sha256(content).hexdigest())
        target = self.root / 'download'
        with patch.object(download, 'opener') as opener:
            opener.return_value.open.return_value = self.response(content)
            download.fetch(spec, target)
            download.fetch(spec, target)
            self.assertEqual(opener.return_value.open.call_count, 1)
        target.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Modified cached'): download.fetch(spec, target)

    def test_over_budget_and_bad_hash_downloads_never_become_final_files(self):
        for content, size in [(b'excess', 3), (b'wrong', 5)]:
            target = self.root / ('download-' + str(size))
            with patch.object(download, 'opener') as opener:
                opener.return_value.open.return_value = self.response(content)
                with self.assertRaises(ValueError): download.fetch(dict(url='https://repo.maven.apache.org/input', size=size, sha256='0'*64), target)
            self.assertFalse(target.exists())
        self.assertEqual(len(list(self.root.glob('*.part'))), 2)

    def test_untrusted_initial_and_final_urls_are_rejected(self):
        for url in ('http://repo.maven.apache.org/a', 'https://127.0.0.1/a', 'https://repo.maven.apache.org.evil/a', 'https://user@repo.maven.apache.org/a'):
            with self.assertRaises(ValueError): download.check_url(url, download.TOOL_HOSTS)
        with patch.object(download, 'opener') as opener:
            opener.return_value.open.return_value = self.response(b'x', 'https://127.0.0.1/a')
            with self.assertRaises(ValueError): download.fetch(dict(url='https://repo.maven.apache.org/a',size=1,sha256='0'*64),self.root/'file')

    def test_ownership_is_required_before_network_or_directory_creation(self):
        with patch.object(acquire_client, 'metadata') as metadata:
            for value in (False, None, 'true', 1):
                with self.assertRaisesRegex(ValueError, 'ownership'): acquire_client.acquire(self.root / 'game', value)
            with patch.object(acquire_client, 'ROOT', self.root), self.assertRaisesRegex(ValueError, 'source repository'):
                acquire_client.acquire(self.root / 'game', True)
        metadata.assert_not_called()
        self.assertFalse((self.root / 'game').exists())

    def test_library_paths_cannot_escape_output(self):
        for name in ('../file', '/file', 'C:\\file', 'a/../../b'):
            with self.assertRaises(ValueError): acquire_client.library_path(name)

    def test_five_asm_dependencies_are_fetched_and_hash_pinned(self):
        with patch.object(splitter, 'CACHE', self.root), patch.object(splitter, 'fetch') as fetch:
            splitter.fetch_missing()
        self.assertEqual(fetch.call_count, 5)
        self.assertEqual({c.args[0]['file'].split('-9.9')[0] for c in fetch.call_args_list}, {'asm','asm-tree','asm-analysis','asm-util','asm-commons'})
        self.assertTrue(all(len(c.args[0]['sha256']) == 64 for c in fetch.call_args_list))

    def test_first_run_plan_excludes_minecraft_and_has_a_fixed_hash_for_every_download(self):
        specs = first_run.download_specs()
        self.assertGreater(sum(spec['size'] for _, spec in specs), 500 * 1024**2)
        self.assertTrue(all('sha256' in spec for _, spec in specs))
        self.assertFalse(any('mojang.com' in spec['url'] or 'minecraft.net' in spec['url'] for _, spec in specs))

    def test_first_run_launch_is_guarded_and_does_not_run_a_shell(self):
        path = self.root / 'setup/status.json'
        with patch.object(first_run, 'state_path', return_value=path), patch.object(first_run, 'require_mount') as mount, patch.object(first_run, 'require_space') as space, patch.object(first_run.subprocess, 'Popen', return_value=SimpleNamespace(pid=12345)) as popen:
            result = first_run.start()
        mount.assert_called_once(); space.assert_called_once()
        self.assertEqual(result['state'], 'queued')
        self.assertNotIn('--owned', popen.call_args.args[0])
        self.assertNotIn('shell', popen.call_args.kwargs)

    def test_external_client_preparation_never_synthesizes_a0_evidence(self):
        path = self.root / 'meta/versions/26.1.2/26.1.2.jar'; path.parent.mkdir(parents=True); path.write_bytes(b'owned fixture')
        inventory = dict(status='OWNED_CLIENT_INPUTS_VERIFIED', gateA0='BLOCKED', jars=[dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())])
        (self.root / 'client-inputs.json').write_text(json.dumps(inventory))
        actual, meta = prepare_b0.preparation_inputs(self.root)
        self.assertEqual(actual['gateA0'], 'BLOCKED'); self.assertEqual(meta, self.root / 'meta')
        path.write_bytes(b'tampered')
        with self.assertRaises(ValueError): prepare_b0.preparation_inputs(self.root)


class SourceAndHostPortabilityTests(TemporaryInputs):
    def test_actual_distributed_tree_contains_build_sources_and_runs_without_checkout(self):
        output = self.root / 'source'
        manifest = bundle_source.stage(output)
        for name in ('interop/fabric/tool/mcfao/build/AotExport.java',
                     'interop/b0/resources/fabricaot-b0.classtweaker',
                     'interop/fabric/fixture/resources/assets/mcfao_fixture/proof.txt'):
            self.assertIn(name, manifest['filesSHA256'])
        self.assertFalse((output / '.git').exists())
        self.assertEqual(bundle_source.source_identity(output)['sourceCommit'], manifest['sourceCommit'])
        for tool in ('mcfao.py', 'desktop_workbench.py', 'prepare_b0.py'):
            result = subprocess.run([sys.executable, '-B', str(output / 'tools' / tool), '--help'],
                                    cwd=self.root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_bundle_filter_excludes_sensitive_and_generated_inputs(self):
        for name in ('artifacts/client.jar','compiler/client.jar','ios/C0Harness/build/Info.plist','tools/client.local.json',
                     'tools/credentials.json','docs/evidence/accounts.json','../tools/a.py','ios/private.mobileprovision'):
            self.assertFalse(bundle_source.allowed(name), name)
        for name in ('tools/mcfao.py','compiler/fabric.lock.json','ios/C0Harness/C0Harness.xcodeproj/project.pbxproj','interop/b0/src/Fixture.java'):
            self.assertTrue(bundle_source.allowed(name), name)

    def test_bundled_source_identity_works_without_git_and_rejects_changes(self):
        source = self.root / 'tools/fixture.py'; source.parent.mkdir(); source.write_text('first party')
        manifest = dict(sourceCommit='commit', sourceDiffSHA256='diff', filesSHA256={'tools/fixture.py':hashlib.sha256(source.read_bytes()).hexdigest()})
        (self.root / 'bundle-manifest.json').write_text(json.dumps(manifest))
        with patch.object(bundle_source.subprocess, 'check_output') as process:
            self.assertEqual(bundle_source.source_identity(self.root)['sourceCommit'], 'commit')
        process.assert_not_called()
        source.write_text('modified')
        with self.assertRaises(ValueError): bundle_source.source_identity(self.root)

    def test_xcode_uses_selected_installation_and_optional_absence_degrades(self):
        selected = self.root / 'Xcode-beta.app/Contents/Developer'; selected.mkdir(parents=True)
        with patch.dict(os.environ, {'DEVELOPER_DIR': str(selected)}):
            self.assertEqual(host_tools.developer_dir(), selected)
        with patch.dict(os.environ, {'DEVELOPER_DIR': '/absent/xcode'}):
            self.assertIsNone(host_tools.developer_dir(False))
            with self.assertRaises(ValueError): host_tools.developer_dir()
        with patch.object(host_tools.subprocess, 'check_output', return_value=str(selected / 'clang')) as discover:
            self.assertEqual(host_tools.xcode_tool('clang'), str(selected / 'clang'))
            self.assertEqual(discover.call_args.args[0], ['xcrun','--sdk','macosx','--find','clang'])

    def test_missing_aar_retains_registration_request(self):
        from graphics_common import register_tree
        with patch.dict(os.environ, {}, clear=True), patch('graphics_common.shutil.which', return_value=None), patch('graphics_common.subprocess.run', side_effect=FileNotFoundError):
            result = register_tree(self.root, ['python3','first-party.py'])
        self.assertEqual(result['status'], 'REGISTRATION_PENDING')
        self.assertTrue((self.root / 'registration-pending.json').is_file())

    def test_ci_portability_validator_makes_no_changes(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-B', str(root / 'ci/patch_src.py'), str(root)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("'sourceMutations': 0",result.stdout)
        scripts = [root / 'ci/build_mac.sh', root / 'ci/build_sim.sh']
        syntax = subprocess.run(['bash','-n', *map(str, scripts)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        for script in scripts:
            text = script.read_text()
            self.assertNotIn('/Applications/Xcode.app', text)
            self.assertNotIn('$XC', text)
            self.assertNotIn('.ci/bin/aar', text)
            self.assertNotIn('x-access-token:', text)
            self.assertIn('CLIENT_DIR="$WORK/client-inputs"', text)


if __name__ == '__main__': unittest.main()
