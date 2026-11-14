import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from import_instance import import_instance, public_endpoint
from mcfao import instance_files, loader_client
from prepare_fabric_aot import mod_files
from types import SimpleNamespace

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pack(self, files=None, overrides=None):
        path = self.root / 'input.mrpack'
        with ZipFile(path, 'w') as archive:
            archive.writestr('modrinth.index.json', json.dumps({
                'formatVersion':1,'game':'minecraft','name':'fixture','versionId':'1',
                'dependencies':{'minecraft':'26.1.2','fabric-loader':'0.19.3'},'files':files or []}))
            for name, data in (overrides or {}).items():
                archive.writestr('overrides/'+name, data)
        return path

    def row(self, data):
        return {'path':'config/sample.json','hashes':{'sha1':hashlib.sha1(data).hexdigest(),'sha512':hashlib.sha512(data).hexdigest()},
                'fileSize':len(data),'downloads':['https://cdn.modrinth.com/fixture']}

    def test_hash_verified_files_and_options_have_exact_manifest(self):
        data=b'{"safe":true}'
        source=self.pack([self.row(data)], {'options.txt':'renderDistance:4'})
        output=self.root/'output'
        result=import_instance(source,output,lambda url,limit:data)
        self.assertEqual(set(result['files']),{'config/sample.json','options.txt'})
        self.assertEqual(set(instance_files(output)),{'config/sample.json','options.txt','import.json'})
        (output/'config/sample.json').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'changed'): instance_files(output)

    def test_bad_download_hash_retains_failure_and_never_claims_success(self):
        source=self.pack([self.row(b'expected')])
        output=self.root/'output'
        with self.assertRaises(ValueError): import_instance(source,output,lambda url,limit:b'wrong')
        self.assertTrue((output/'import-failure.json').is_file())
        self.assertFalse((output/'import.json').exists())

    def test_sensitive_override_is_rejected(self):
        source=self.pack(overrides={'accounts.json':'secret'})
        with self.assertRaisesRegex(ValueError,'Only mods'): import_instance(source,self.root/'output')

    def test_prism_import_excludes_saves_accounts_and_rejects_links(self):
        source=self.root/'prism'; source.mkdir()
        (source/'mmc-pack.json').write_text(json.dumps({'components':[
            {'uid':'net.minecraft','version':'26.1.2'}, {'uid':'net.fabricmc.fabric-loader','version':'0.19.3'}]}))
        base=source/'.minecraft';(base/'mods').mkdir(parents=True);(base/'config').mkdir()
        (base/'config/test.json').write_text('{}'); (base/'options.txt').write_text('renderDistance:4')
        (base/'saves').mkdir();(base/'saves/world').write_text('preserve');(base/'accounts.json').write_text('private')
        result=import_instance(source,self.root/'output')
        self.assertEqual(set(result['files']),{'config/test.json','options.txt'})
        (base/'config/link').symlink_to(base/'accounts.json')
        with self.assertRaisesRegex(ValueError,'Symlink'):import_instance(source,self.root/'blocked')

    def test_download_rejects_local_network_and_non_cdn_endpoints(self):
        for url in ['http://cdn.modrinth.com/a','https://localhost/a','https://cdn.modrinth.com@localhost/a']:
            with self.assertRaises(ValueError): public_endpoint(url)
        with patch('import_instance.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaisesRegex(ValueError,'non-public'):public_endpoint('https://cdn.modrinth.com/a')

    def test_uppercase_mod_jars_are_never_silently_omitted(self):
        path=self.root/'SAMPLE.JAR';path.write_bytes(b'fixture')
        self.assertEqual(mod_files(self.root),[path])

    def test_full_fabric_build_rejects_implicitly_reduced_pack(self):
        output=self.root/'prepared';output.mkdir()
        args=SimpleNamespace(loader='fabric',mods=self.root,audited_mods=True,trace_agent=False,prepare_only=False)
        pipeline=SimpleNamespace(step=lambda *a,**k:output)
        for field,value in [('excludedMods',{'sample':['dynamic class generation']}),('retiredJars',['sample.jar'])]:
            (output/'result.json').write_text(json.dumps({'modSHA256':{},field:value}))
            with self.assertRaisesRegex(ValueError,'excluded Mods'):
                loader_client(pipeline,args,{'prepared':self.root},self.root/'client.jar',{'modsSHA256':{}})
