import hashlib
import io
import json
import os
import plistlib
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import desktop_workbench as w
from mcfao import instance_files, device_xcode


def jar_bytes(mod_id='workbench_fixture', depends=None):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr('fabric.mod.json', json.dumps({'schemaVersion': 1, 'id': mod_id, 'name': mod_id, 'version':'1.0.0', 'environment':'client', 'depends':depends or {}}))
    return data.getvalue()


class WorkbenchTests(unittest.TestCase):
    def selected(self, source, ids=None):
        report = w.scan_pack(source)
        return dict(source=report['source'], fingerprint=report['resources_fingerprint'], included=ids if ids is not None else [r['id'] for r in report['resources'] if r['default_selected']])

    def test_resource_choices_filter_real_files_and_keep_shader_folder(self):
        source = self.prism()
        base = source / '.minecraft'
        (base/'shaderpacks/shader/shaders').mkdir(parents=True)
        (base/'shaderpacks/shader/shaders/main.glsl').write_text('first-party fixture')
        (base/'resourcepacks/textures').mkdir(parents=True)
        (base/'resourcepacks/textures/pack.mcmeta').write_text('{}')
        (base/'mods/excluded.jar').write_bytes(jar_bytes())
        selection = self.selected(source, ['local:mods/fixture.jar', 'local:shaderpacks/shader'])
        _, game = w.stage_source(source, self.root/'stage', selection=selection)
        self.assertTrue((game/'mods/fixture.jar').exists())
        self.assertTrue((game/'shaderpacks/shader/shaders/main.glsl').exists())
        self.assertFalse((game/'mods/excluded.jar').exists())
        self.assertFalse((game/'resourcepacks').exists())
        self.assertFalse((game/'config').exists())
        self.assertEqual(w.read_json(game.parent/'source.json')['resourceSelection'], selection)

    def test_static_exclusion_plan_removes_owner_and_transitive_dependents_in_copy(self):
        source = self.prism()
        mods = source / '.minecraft/mods'
        (mods/'fixture.jar').unlink()
        (mods/'owner.jar').write_bytes(jar_bytes('owner'))
        (mods/'dependent.jar').write_bytes(jar_bytes('dependent', {'owner': '*'}))
        (mods/'keep.jar').write_bytes(jar_bytes('keep'))
        selection = self.selected(source)
        _, game = w.stage_source(source, self.root/'stage', selection=selection)
        facts = {
            'status': 'FABRIC_AOT_INPUT_PREPARED',
            'excludedMods': {'unsupported_nested': ['runtime defineClass is unsupported']},
            'mods': [
                {'id': 'owner', 'path': 'owner.jar'},
                {'id': 'unsupported_nested', 'path': 'owner.jar!META-INF/jars/unsafe.jar'},
                {'id': 'dependent', 'path': 'dependent.jar'},
            ],
        }
        plan = w.static_exclusion_plan(facts, self.root/'stage')
        self.assertEqual(set(plan['modFiles']), {'owner.jar', 'dependent.jar'})
        self.assertEqual(set(plan['excludedIds']), {'owner', 'dependent', 'unsupported_nested'})
        filtered = w.filtered_source_copy(self.root/'stage', self.root/'filtered', plan)
        filtered_game = filtered/'.minecraft'
        self.assertTrue((game/'mods/owner.jar').is_file())
        self.assertTrue((game/'mods/dependent.jar').is_file())
        self.assertFalse((filtered_game/'mods/owner.jar').exists())
        self.assertFalse((filtered_game/'mods/dependent.jar').exists())
        self.assertTrue((filtered_game/'mods/keep.jar').is_file())
        self.assertEqual(w.instance_files(filtered_game), w.read_json(filtered/'source.json')['filesSHA256'])
        self.assertEqual(w.read_json(filtered_game/'import.json')['staticAotExclusions'], plan['mods'])

    def test_exclusion_decision_requires_current_challenge(self):
        job_dir = self.root/'artifacts/desktop-jobs'/('a'*32)
        job_dir.mkdir(parents=True)
        job_path = job_dir/'job.json'
        w.write_json(job_path, {'id':'a'*32, 'state':'awaiting-exclusions', 'exclusionChallenge':{'id':'challenge-1'}})
        with self.assertRaisesRegex(ValueError, '当前没有等待'):
            w.resolve_exclusions(self.root, 'a'*32, {'challengeId':'stale','accepted':True})
        w.resolve_exclusions(self.root, 'a'*32, {'challengeId':'challenge-1','accepted':True})
        decision = w.read_json(job_path.parent/'exclusion-decision.json')
        self.assertEqual(decision['challengeId'], 'challenge-1')
        self.assertTrue(decision['accepted'])
        self.assertTrue(decision['respondedAt'])

    def test_exclusion_report_hashes_staged_mods_and_rejects_changed_input(self):
        source = self.prism()
        selection = self.selected(source)
        _, game = w.stage_source(source, self.root/'stage', selection=selection)
        attempt = 'c'*32
        product = self.root/'build/fabric'/attempt/'product'
        product.mkdir(parents=True)
        mods = game/'mods'
        w.write_json(self.root/'build/fabric/checkpoint.json', {'attempt':attempt})
        w.write_json(product/'result.json', {
            'status':'FABRIC_AOT_INPUT_PREPARED',
            'excludedMods':{'fixture':['runtime defineClass is unsupported']},
            'modSHA256':{str(p.resolve()): w.sha256(p) for p in w.mod_candidates(mods)},
        })
        facts = w.fabric_exclusion_report(self.root/'build', self.root/'stage')
        self.assertIn('fixture', facts['excludedMods'])
        (mods/'fixture.jar').write_bytes(jar_bytes('changed'))
        with self.assertRaisesRegex(ValueError, '不匹配'):
            w.fabric_exclusion_report(self.root/'build', self.root/'stage')

    def test_explicit_optional_selection_downloads_only_selected_file(self):
        data = jar_bytes()
        def remote(name): return dict(path='mods/'+name+'.jar', hashes=dict(sha1=hashlib.sha1(data).hexdigest(),sha512=hashlib.sha512(data).hexdigest()), downloads=['https://cdn.modrinth.com/data/'+name+'.jar'], fileSize=len(data), env=dict(client='optional'))
        source=self.mrpack(remote=[remote('chosen'),remote('excluded')])
        selection=self.selected(source,['manifest:mods/chosen.jar'])
        def fetch(entry,target): target.write_bytes(data)
        with patch.object(w,'download',side_effect=fetch) as download:
            _,game=w.stage_source(source,self.root/'stage',selection=selection)
        self.assertEqual(download.call_count,1)
        self.assertTrue((game/'mods/chosen.jar').exists())
        self.assertFalse((game/'mods/excluded.jar').exists())

    def test_resource_selection_rejects_changed_source_unknown_or_disabled_files(self):
        source=self.prism()
        (source/'.minecraft/mods/off.jar.disabled').write_bytes(b'not read')
        report=w.scan_pack(source)
        for ids in [[],['local:mods/missing.jar'],['local:mods/fixture.jar','local:mods/off.jar.disabled']]:
            with self.assertRaises(ValueError): w.resource_selection(report,self.selected(source,ids))
        selection=self.selected(source)
        (source/'.minecraft/config/fixture.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError,'已改变'): w.resource_selection(w.scan_pack(source),selection)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        w.CANCELLED = False

    def prism(self):
        source = self.root / 'Prism instance 中文'
        (source / '.minecraft/mods').mkdir(parents=True)
        (source / '.minecraft/config').mkdir()
        (source / '.minecraft/config/fixture.json').write_text('{"enabled":true}')
        (source / '.minecraft/mods/fixture.jar').write_bytes(jar_bytes())
        w.write_json(source / 'mmc-pack.json', {'components':[{'uid':'net.minecraft','version':'26.1.2'},{'uid':'net.fabricmc.fabric-loader','version':'0.19.3'}]})
        return source

    def mrpack(self, entries=(), remote=None):
        source = self.root / 'fixture.mrpack'
        manifest = {'formatVersion':1,'game':'minecraft','name':'GUI fixture','versionId':'1', 'dependencies':{'minecraft':'26.1.2','fabric-loader':'0.19.3'},'files':remote or []}
        with zipfile.ZipFile(source,'w') as z:
            z.writestr('modrinth.index.json',json.dumps(manifest))
            for name, data in entries: z.writestr(name,data)
        return source

    def test_prism_stages_mods_configuration_without_accounts_or_worlds(self):
        source = self.prism()
        (source / '.minecraft/saves').mkdir()
        (source / '.minecraft/saves/private-world').write_text('world')
        (source / 'accounts.json').write_text('private')
        mods, game = w.stage_source(source, self.root / 'stage')
        self.assertTrue((mods / 'fixture.jar').is_file())
        self.assertTrue((game / 'config/fixture.json').is_file())
        self.assertFalse((game / 'saves').exists())
        self.assertFalse((game / 'accounts.json').exists())
        self.assertFalse(w.read_json(game.parent / 'source.json')['report']['fatal'])

    def test_staging_rejects_nested_symlinks(self):
        source = self.prism()
        (source / '.minecraft/config/link').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError,'链接'):
            w.stage_source(source,self.root / 'stage')

    def test_force_loader_override_is_explicit_and_records_both_versions(self):
        report = dict(fatal=False, findings=[], fabric_loader_version='0.19.2')
        warned = w.source_overrides(report, '0.19.3')
        self.assertEqual(warned[0]['sourceLoader'], '0.19.2')
        self.assertEqual(warned[0]['code'], 'FABRIC_LOADER_OVERRIDE')
        self.assertEqual(w.source_overrides(report, '0.19.3', True), warned)
        self.assertEqual(w.source_overrides(report, '0.19.3', True)[0]['buildLoader'], '0.19.3')
        self.assertEqual(w.source_overrides(dict(report, fabric_loader_version='0.19.3'), '0.19.3', True), [])

    def test_force_does_not_bypass_invalid_source(self):
        source = self.mrpack([('overrides/../outside','bad')])
        with self.assertRaises(ValueError):
            w.stage_source(source, self.root / 'stage', force_compile=True)
        self.assertFalse((self.root / 'outside').exists())

    def test_force_stages_with_build_loader_and_preserves_source_report(self):
        source = self.prism()
        metadata = source / 'mmc-pack.json'
        data = w.read_json(metadata); data['components'][1]['version'] = '0.19.2'; w.write_json(metadata, data)
        messages = []
        w.stage_source(source, self.root / 'stage', messages.append)
        record = w.read_json(self.root / 'stage/source.json')
        self.assertEqual(record['sourceReport']['fabric_loader_version'], '0.19.2')
        self.assertEqual(record['report']['fabric_loader_version'], '0.19.3')
        self.assertEqual(record['compatibilityOverrides'][0]['code'], 'FABRIC_LOADER_OVERRIDE')
        self.assertEqual(w.read_json(metadata)['components'][1]['version'], '0.19.2')
        self.assertIn('0.19.2', messages[0])

    def test_force_request_persists_override_at_launch(self):
        from types import SimpleNamespace
        source = self.prism()
        metadata = source / 'mmc-pack.json'
        data = w.read_json(metadata); data['components'][1]['version'] = '0.19.2'; w.write_json(metadata, data)
        lock = self.root / 'compiler'; lock.mkdir(); w.write_json(lock / 'fabric.lock.json', {'fabricLoader':'0.19.3'})
        export = self.root / 'export.plist'; export.write_bytes(plistlib.dumps({'method':'debugging'}))
        request = dict(workspace=str(self.root), loader='fabric', source=str(source), output=str(self.root/'output'), config='unused', exportOptions=str(export))
        with patch.object(w, 'workspace_path', return_value=self.root), patch.object(w, 'config_summary'), patch.object(w.native_dependencies, 'preflight'):
            self.assertEqual(w.validate_request(request), self.root)
            self.assertEqual(w.validate_request(dict(request, audited=False)), self.root)
            with self.assertRaisesRegex(ValueError, '布尔'): w.validate_request(dict(request, forceCompile='true'))
            with patch.object(w.subprocess, 'Popen', return_value=SimpleNamespace(pid=12345)):
                job = w.start(request)
        saved = w.read_json(Path(job['folder'])/'job.json')
        self.assertEqual(saved['compatibilityOverrides'][0]['sourceLoader'], '0.19.2')

    def test_mrpack_client_override_has_precedence(self):
        source = self.mrpack([('overrides/mods/fixture.jar',jar_bytes()), ('overrides/config/a.json','base'), ('client-overrides/config/a.json','client')])
        _, game = w.stage_source(source,self.root / 'stage')
        self.assertEqual((game / 'config/a.json').read_text(),'client')

    def test_mrpack_rejects_path_traversal(self):
        source = self.mrpack([('overrides/../outside','bad')])
        with self.assertRaises(ValueError): w.stage_source(source,self.root / 'stage')
        self.assertFalse((self.root / 'outside').exists())

    def test_mrpack_reports_unsupported_required_file(self):
        source = self.mrpack([('overrides/mods/fixture.jar',jar_bytes()),('overrides/unsupported.bin','custom')])
        with self.assertRaisesRegex(ValueError,'必要路径'):
            w.stage_source(source,self.root / 'stage')

    def test_staging_can_be_cancelled(self):
        with self.assertRaises(InterruptedError): w.stage_source(self.prism(),self.root / 'stage',cancelled=lambda:True)

    def test_download_rejects_other_origin_without_network(self):
        with self.assertRaisesRegex(ValueError,'HTTPS'):
            w.download({'downloads':['https://localhost/secret']},self.root / 'file')

    def test_only_the_pinned_cdn_host_is_downloadable(self):
        self.assertEqual(w.download_url('https://cdn.modrinth.com/data/mod.jar'), 'https://cdn.modrinth.com/data/mod.jar')
        for url in ('http://cdn.modrinth.com/a', 'https://localhost/a', 'https://cdn.modrinth.com.evil.invalid/a',
                    'https://user@cdn.modrinth.com/a', 'https://cdn.modrinth.com:8443/a', 'https://cdn.modrinth.com/a#frag'):
            with self.assertRaisesRegex(ValueError, 'cdn.modrinth.com'): w.download_url(url)

    def test_redirects_are_rechecked_against_the_cdn(self):
        handler = w.DownloadRedirect()
        request = w.urllib.request.Request('https://cdn.modrinth.com/data/mod.jar')
        with self.assertRaisesRegex(ValueError, 'cdn.modrinth.com'):
            handler.redirect_request(request, None, 302, 'Found', {}, 'https://evil.invalid/mod.jar')

    def test_download_honours_environment_proxy(self):
        body = b'proxied'
        class Response:
            status = 200
            def read(self, _): return body
            def __enter__(self): return self
            def __exit__(self, *a): return False
        class Opener:
            def open(self, request, timeout):
                self.url = request.full_url
                return Response()
        opener = Opener()
        entry = {'downloads': ['https://cdn.modrinth.com/file.jar'], 'fileSize': len(body), 'hashes': {'sha512': hashlib.sha512(body).hexdigest()}}
        with patch.object(w.urllib.request, 'build_opener', return_value=opener), patch.object(w, 'download_opener', return_value=opener):
            w.download(entry, self.root / 'file')
        self.assertEqual((self.root / 'file').read_bytes(), body)
        self.assertEqual(opener.url, 'https://cdn.modrinth.com/file.jar')

    def test_download_opener_verifies_tls_certificates(self):
        context = w.tls_context()
        self.assertTrue(context.verify_mode.name == 'CERT_REQUIRED')
        self.assertGreater(context.cert_store_stats().get('x509_ca', 0), 0)

    def test_download_checks_size_and_all_fingerprints(self):
        body = b'fixture'
        class Response:
            status = 200
            def read(self, _): return body
            def __enter__(self): return self
            def __exit__(self, *a): return False
        class Connection:
            def open(self, request, timeout): return Response()
        entry = {'downloads':['https://cdn.modrinth.com/file.jar'],'fileSize':len(body),'hashes':{'sha1':hashlib.sha1(body).hexdigest(),'sha512':hashlib.sha512(body).hexdigest()}}
        with patch.object(w,'download_opener',return_value=Connection()):
            w.download(entry,self.root / 'file')
            self.assertEqual((self.root / 'file').read_bytes(),body)
            entry['hashes']['sha512']='0'*128
            with self.assertRaisesRegex(ValueError,'哈希'): w.download(entry,self.root / 'bad')
            self.assertFalse((self.root / 'bad').exists())
            entry['fileSize']=w.LIMIT+1
            with self.assertRaisesRegex(ValueError,'256 MiB'): w.download(entry,self.root / 'huge')

    def test_paths_reject_control_characters_and_ids(self):
        for bad in ('', 'a'+chr(0), 'a'+chr(10), 'a'+chr(13)):
            with self.assertRaises(ValueError): w.resolve(bad)
        with self.assertRaises(ValueError): w.job_path(self.root,'../etc')

    def test_packaged_configuration_is_verified(self):
        _, game = w.stage_source(self.prism(), self.root / 'stage')
        self.assertIn('config/fixture.json', instance_files(game))
        (game / 'config/fixture.json').write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed'): instance_files(game)
        (game / 'accounts.json').write_text('sensitive')
        with self.assertRaises(ValueError): instance_files(game)

    def test_xcode_receives_literal_pack_path(self):
        game = self.root / "中文 pack ' $(echo BAD)"
        argv = device_xcode(game,self.root,team='ABCDEFGHIJ',renderer='gl41')
        self.assertIn('FAOT_GRAPHICS_NATIVE_DIR='+str(game),argv)
        self.assertIn('FAOT_RENDERER=gl41',argv)
        self.assertIn('generic/platform=iOS',argv)

    def test_execute_runs_literal_argv_and_persists_output(self):
        value = "中文 ' $(echo BAD)"
        stages = []
        w.execute([sys.executable,'-c','import sys;print(sys.argv[1])',value],self.root,'fixture',lambda **v:stages.append(v),'aot',dict(os.environ))
        self.assertEqual((self.root / 'fixture.stdout.log').read_text().strip(),value)
        self.assertEqual(stages,[{'stage':'aot'}])

    def test_execute_reports_failed_command(self):
        with self.assertRaisesRegex(ValueError,'退出码 7'):
            w.execute([sys.executable,'-c',"import sys;print('reason',file=sys.stderr);sys.exit(7)"],self.root,'fixture',lambda **_:None,'aot',dict(os.environ))

    def test_failed_stage_reports_only_its_own_output(self):
        # A retry appends to the same log. An earlier exclusion message must not
        # mask the real reason a later stage failed.
        (self.root/'fixture.stderr.log').write_text(
            'mcfao build: Requested Fabric instance contains excluded Mods; review /x.\n')
        with self.assertRaises(ValueError) as caught:
            w.execute([sys.executable,'-c',"import sys;print('OutOfMemoryError: Java heap space',file=sys.stderr);sys.exit(2)"],
                      self.root,'fixture',lambda **_:None,'aot',dict(os.environ))
        message = str(caught.exception)
        self.assertIn('OutOfMemoryError', message)
        self.assertNotIn('contains excluded Mods', message)

    def test_failed_stage_falls_back_to_its_stdout(self):
        (self.root/'quiet.stderr.log').write_text('old stderr from a previous round\n')
        with self.assertRaises(ValueError) as caught:
            w.execute([sys.executable,'-c',"print('analysis said no');import sys;sys.exit(3)"],
                      self.root,'quiet',lambda **_:None,'aot',dict(os.environ))
        message = str(caught.exception)
        self.assertIn('analysis said no', message)
        self.assertNotIn('previous round', message)

    def test_execute_cancels_descendant_processes(self):
        pidfile=self.root / 'child.pid'
        import threading
        def cancel():
            deadline=time.monotonic()+5
            while not pidfile.exists() and time.monotonic()<deadline: time.sleep(.03)
            (self.root / 'cancel').touch()
        thread=threading.Thread(target=cancel);thread.start()
        script="import subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True);Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)"
        with self.assertRaises(InterruptedError):
            w.execute([sys.executable,'-c',script,str(pidfile)],self.root,'fixture',lambda **_:None,'aot',dict(os.environ))
        thread.join()
        pid=int(pidfile.read_text())
        result=subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='],capture_output=True,text=True)
        self.assertTrue(not result.stdout.strip() or result.stdout.strip().startswith('Z'))

    def test_job_success_requires_verified_ipa_result(self):
        request={'workspace':str(w.ROOT),'loader':'vanilla','config':'unused','exportOptions':'unused'}
        folder=self.root / 'job';folder.mkdir();(folder / 'launch').touch()
        build=self.root / 'build'
        job=dict(id='a'*32,state='queued',stage='validate',request=request,build=str(build),folder=str(folder))
        path=folder / 'job.json';w.write_json(path,job)
        calls=[]
        def execute(argv, folder, name, update, stage, env):
            calls.append(list(map(str,argv)))
            if name=='export':
                output=Path(argv[argv.index('--output')+1]);output.mkdir();ipa=output / 'fixture.ipa';ipa.write_bytes(b'fixture')
                w.write_json(output / 'result.json',{'status':'DEVELOPMENT_IPA_VERIFIED','ipa':str(ipa),'sha256':hashlib.sha256(b'fixture').hexdigest(),'bytes':7})
        with patch.object(w,'validate_request'),patch.object(w,'check',return_value={'ready':True,'checks':[]}),patch.object(w,'execute',side_effect=execute):
            w.run_job(path)
        result=w.read_json(path)
        self.assertEqual(result['state'],'succeeded', result.get('error'))
        self.assertTrue(result['ipa'].endswith('.ipa'))
        self.assertEqual([c[3] for c in calls],['doctor','build','export'])
        self.assertFalse(any('--prepare-only' in c for c in calls))

    def test_missing_export_manifest_cannot_succeed(self):
        folder=self.root / 'job';folder.mkdir();(folder / 'launch').touch()
        path=folder / 'job.json'
        w.write_json(path,dict(id='b'*32,state='queued',stage='validate',request={'workspace':str(w.ROOT),'loader':'vanilla','config':'x','exportOptions':'x'},build=str(self.root / 'build'),folder=str(folder)))
        with patch.object(w,'validate_request'),patch.object(w,'check',return_value={'ready':True,'checks':[]}),patch.object(w,'execute'):
            w.run_job(path)
        self.assertEqual(w.read_json(path)['state'],'failed')

    def test_forced_job_stages_source_and_invokes_actual_build_command(self):
        source = self.prism()
        metadata = source / 'mmc-pack.json'
        data = w.read_json(metadata); data['components'][1]['version'] = '0.19.2'; w.write_json(metadata, data)
        request = dict(workspace=str(w.ROOT), loader='fabric', source=str(source), config='unused', exportOptions='unused', forceCompile=True)
        folder = self.root/'job'; folder.mkdir(); (folder/'launch').touch()
        path = folder/'job.json'
        w.write_json(path, dict(id='a'*32, state='queued', stage='validate', request=request, build=str(self.root/'build'), folder=str(folder)))
        calls = []
        def execute(argv, folder, name, update, stage, env):
            calls.append(list(map(str, argv)))
            if name == 'export':
                output = Path(argv[argv.index('--output')+1]); output.mkdir()
                ipa = output/'fixture.ipa'; ipa.write_bytes(b'fixture')
                w.write_json(output/'result.json', dict(status='DEVELOPMENT_IPA_VERIFIED', ipa=str(ipa), sha256=hashlib.sha256(b'fixture').hexdigest(), bytes=7))
        with patch.object(w, 'validate_request'), patch.object(w, 'check', return_value=dict(ready=True, checks=[])), patch.object(w, 'execute', side_effect=execute):
            w.run_job(path)
        job = w.read_json(path)
        self.assertEqual(job['state'], 'succeeded', job.get('error'))
        self.assertEqual(job['compatibilityOverrides'][0]['sourceLoader'], '0.19.2')
        build_command = next(c for c in calls if c[3] == 'build')
        self.assertIn('--audited-mods', build_command)
        self.assertIn('--instance-data', build_command)
        self.assertEqual(build_command[build_command.index('--renderer')+1], 'gl41')
        self.assertEqual(next(c for c in calls if c[3] == 'doctor')[5], 'gl41')
        self.assertNotIn('--prepare-only', build_command)
        self.assertEqual(w.read_json(folder/'source/source.json')['report']['fabric_loader_version'], '0.19.3')

    def test_aot_heap_follows_the_compiler_half_of_memory_ceiling(self):
        self.assertEqual(w.aot_heap_gib(18 * 1024**3), 9)
        self.assertEqual(w.aot_heap_gib(16 * 1024**3), 8)
        self.assertEqual(w.aot_heap_gib(12 * 1024**3), 6)
        self.assertEqual(w.aot_heap_gib(64 * 1024**3), 9)

    def test_compile_build_moves_to_fresh_directory_when_reused_inputs_changed(self):
        folder = self.root/'retry-job'
        folder.mkdir()
        path = folder/'job.json'
        w.write_json(path, dict(id='d'*32, state='queued', stage='validate',
                               request={'loader':'fabric', 'config':str(self.root/'config.json'), 'output':str(self.root/'output')},
                               build=str(self.root/'stale-build'), folder=str(folder), previousBuilds=[]))
        calls = []
        def execute(argv, folder, name, update, stage, env):
            calls.append(Path(argv[argv.index('--output')+1]))
            if len(calls) == 1:
                raise ValueError('build 失败（退出码 2）\nmcfao build: Build inputs changed. Use a new output.')
        job = w.read_json(path)
        def update(**values):
            job.update(values)
            w.write_json(path, job)
        with patch.object(w, 'execute', side_effect=execute):
            error, build = w.compile_build(['python', 'mcfao.py'], folder,
                                           {'loader':'fabric', 'config':str(self.root/'config.json'), 'output':str(self.root/'output')},
                                           self.root/'stale-build', self.root/'mods', self.root/'game', update, {})
        self.assertIsNone(error)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0], calls[1])
        self.assertEqual(build, calls[1])
        job = w.read_json(path)
        self.assertEqual(job['build'], str(calls[1]))
        self.assertEqual(job['previousBuilds'][0]['path'], str(self.root/'stale-build'))

    def test_stale_job_is_interrupted_and_compiler_logs_are_visible(self):
        folder=self.root / 'job';folder.mkdir();build=self.root / 'build'
        log=build / 'aot/attempt/command';log.mkdir(parents=True);(log / 'stdout.log').write_text('real compiler progress')
        path=folder / 'job.json';w.write_json(path,dict(id='c'*32,state='running',stage='aot',pid=999999,build=str(build)))
        with patch.object(w,'alive',return_value=False): result=w.snapshot(path)
        self.assertEqual(result['state'],'interrupted')
        self.assertIn('real compiler progress',result['log'])

    def test_log_snapshot_filters_metadata_before_selecting_latest_files(self):
        folder = self.root / 'job'
        folder.mkdir()
        build = self.root / 'build'
        command = build / 'fabric/attempt/command'
        command.mkdir(parents=True)
        analysis = build / 'aot/attempt/product/analysis'
        analysis.mkdir(parents=True)
        (folder / 'build.stdout.log').write_text('fabric: real progress\n')
        (command / 'stderr.log').write_text('real sandbox error')
        for base in (folder, command, analysis):
            (base / '._build.stdout.log').write_bytes(b'\x00\x05\x16\x07Mac OS X ATTR')
            (base / '._stderr.log').write_bytes(b'\x00\x05\x16\x07Mac OS X ATTR')
        for name in ('__MACOSX', '._nested'):
            (folder / name).mkdir()
            (folder / name / 'stdout.log').write_text('metadata directory content')
        path = folder / 'job.json'
        w.write_json(path, dict(id='c'*32, state='failed', stage='fabric', build=str(build)))
        result = w.snapshot(path)
        self.assertIn('real progress', result['log'])
        self.assertIn('real sandbox error', result['log'])
        self.assertNotIn('ATTR', result['log'])
        self.assertNotIn('metadata directory content', result['log'])
        self.assertNotIn('._', result['log'])
        self.assertEqual(result['stage'], 'fabric')

    def test_job_launch_is_persisted_before_worker_release_and_concurrent_start_is_blocked(self):
        from types import SimpleNamespace
        request = {'loader': 'vanilla', 'output': str(self.root / 'output')}
        with patch.object(w, 'validate_request', return_value=self.root), patch.object(w.subprocess, 'Popen', return_value=SimpleNamespace(pid=12345)), patch.object(w, 'alive', return_value=True):
            job = w.start(request)
            folder = Path(job['folder'])
            self.assertEqual(w.read_json(folder / 'job.json')['pid'], 12345)
            self.assertTrue((folder / 'launch').exists())
            with self.assertRaisesRegex(ValueError, '已有构建'):
                w.start(request)

    def test_retry_preserves_staged_inputs_and_original_build_directory(self):
        from types import SimpleNamespace
        request = {'loader': 'vanilla', 'output': str(self.root / 'output')}
        old_id = 'e' * 32
        path = w.job_path(self.root, old_id)
        path.parent.mkdir(parents=True)
        w.write_json(path, dict(id=old_id, state='failed', stage='aot', request=request,
                               build=str(self.root / 'original-build'), sourceFolder=str(self.root / 'original-source'),
                               folder=str(path.parent)))
        with patch.object(w, 'validate_request', return_value=self.root), patch.object(w.subprocess, 'Popen', return_value=SimpleNamespace(pid=12345)):
            job = w.start(request, old_id)
        self.assertEqual(job['build'], str(self.root / 'original-build'))
        self.assertEqual(job['sourceFolder'], str(self.root / 'original-source'))
        self.assertNotEqual(job['id'], old_id)

    def test_cancellation_marker_is_visible_without_racing_worker_state_writes(self):
        path = self.root / 'job.json'
        w.write_json(path, dict(id='f' * 32, state='running', stage='aot', pid=12345))
        (self.root / 'cancel').touch()
        with patch.object(w, 'alive', return_value=True):
            self.assertEqual(w.snapshot(path, False)['state'], 'cancelling')
        self.assertEqual(w.read_json(path)['state'], 'running')

    def test_embed_script_copies_pack_resources_to_app_bundle(self):
        from mcfao import ROOT
        game = self.root / 'pack'
        (game / 'config').mkdir(parents=True)
        (game / 'config/a.json').write_text('fixture configuration')
        output = self.root / 'output'
        env = dict(os.environ, FAOT_INSTANCE_DATA_DIR=str(game), TARGET_BUILD_DIR=str(output),
                   UNLOCALIZED_RESOURCES_FOLDER_PATH='App.app', FAOT_GAME_ASSETS_DIR='', FAOT_GRAPHICS_NATIVE_DIR='')
        subprocess.run(['/bin/sh', str(ROOT / 'ios/C0Harness/embed_graphics_libraries.sh')], env=env, check=True)
        self.assertEqual((output / 'App.app/instance-seed/config/a.json').read_text(), 'fixture configuration')

    def test_storage_plan_and_clean_use_the_shared_data_root(self):
        data = self.root / 'data'
        (data / 'cache/upstream').mkdir(parents=True)
        (data / 'cache/upstream/jdk.tar.gz').write_bytes(b'x' * 2048)
        with patch.object(w.cleanup_storage, 'default_data_root', return_value=data):
            plan = w.storage('storage-plan', {})
            self.assertEqual(plan['status'], 'STORAGE_PLAN')
            self.assertIn('cache', [group['id'] for group in plan['groups']])
            result = w.storage('storage-clean', {'groups': ['cache']})
        self.assertEqual(result['status'], 'STORAGE_CLEANED')
        self.assertFalse((data / 'cache/upstream').exists())

    def test_storage_clean_requires_an_explicit_group(self):
        with patch.object(w.cleanup_storage, 'default_data_root', return_value=self.root):
            with self.assertRaises(ValueError):
                w.storage('storage-clean', {})
            with self.assertRaises(ValueError):
                w.storage('storage-clean', {'groups': ['cache', 3]})

    def test_configured_storage_reports_distribution_and_keeps_cleanup_read_only(self):
        configuration = self.root / 'storage.json'
        configuration.write_text('{}')
        cache = self.root / 'custom-cache'
        cache.mkdir()
        (cache / 'retain.bin').write_bytes(b'x' * 8192)
        paths = dict(cache=cache, builds=self.root / 'custom-builds',
                     jobs=self.root / 'custom-jobs', rust=self.root / 'custom-rust')
        with patch('storage_config.config_path', return_value=configuration), patch.object(w, 'storage_paths', return_value=paths):
            report = w.storage('storage-plan', {})
            self.assertEqual(len(report['usage']), 4)
            self.assertEqual(len(report['volumes']), 1)
            self.assertGreater(report['managedBytes'], 0)
            self.assertTrue(report['blocked'])
            with self.assertRaisesRegex(ValueError, '只读统计'):
                w.storage('storage-clean', {'groups': ['cache']})
        self.assertTrue((cache / 'retain.bin').exists())

    def test_configured_storage_keeps_disconnected_roots_visible(self):
        configuration = self.root / 'storage.json'
        configuration.write_text('{}')
        path = self.root / 'broken-cache'
        path.symlink_to(self.root / 'disconnected')
        with patch('storage_config.config_path', return_value=configuration), patch.object(w, 'storage_paths', return_value=dict(cache=path)):
            report = w.storage('storage-plan', {})
        self.assertFalse(report['usage'][0]['available'])
        self.assertTrue(report['warnings'])
        self.assertFalse((self.root / 'disconnected').exists())

if __name__=='__main__': unittest.main()
