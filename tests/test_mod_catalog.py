from pathlib import Path
import json
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_fabric_aot import compile_java, load_reference
from capture import capture

class ModCatalogTests(unittest.TestCase):
    def test_snapshot_lookup_metadata_builtin_paths_and_lowering(self):
        home, libraries, engine, _ = load_reference(ROOT / 'artifacts/b0/prepared-04')
        with tempfile.TemporaryDirectory() as work:
            output = Path(work)
            classes = output / 'classes'
            cp = [*engine, *libraries]
            compile_java(home, cp, [ROOT / p for p in [
                'interop/fabric/tool/mcfao/aot/ModCatalog.java',
                'interop/diagnostics/ModCatalogProbe.java']] + list((ROOT / 'interop/fabric/tool/mcfao/build').glob('*.java')), classes, output / 'compile')
            resource = classes / 'mcfao/mod-files/fixture/resourcepacks/dark/pack.mcmeta'
            resource.parent.mkdir(parents=True)
            resource.write_text('fixture')
            (classes / 'mcfao/mod-catalog.json').write_text(json.dumps({'fixture': {
                'id': 'fixture', 'name': 'Fixture', 'version': '1.2.3', 'description': '',
                'files': ['resourcepacks/dark/pack.mcmeta'], 'type':'fabric', 'environment':'UNIVERSAL', 'provides':['fixture_alias'], 'license':['MIT'], 'contact':{'homepage':'https://example.org'}, 'authors':[{'name':'Author','contact':{}}], 'contributors':[], 'dependencies':[{'id':'minecraft','kind':'DEPENDS','requirements':['>=26.1']}], 'custom':{'flag':True,'object':{'array':[1,None,'text']}}, 'icons':{'0':'icon.png'}, 'parent':'', 'children':[], 'originKind':'PATH'}}))
            run = capture([str(home / 'bin/java'), '-cp', ':'.join(map(str,[classes,*cp])),
                           'mcfao.build.ModCatalogProbe'], output / 'run', 30)
            self.assertEqual(run['exitCode'], 0, (output / 'run/stderr.log').read_text())
            self.assertIn('MOD_CATALOG_PASS', (output / 'run/stdout.log').read_text())

    def test_snapshot_matches_pinned_loader_metadata(self):
        home, libraries, engine, _ = load_reference(ROOT / 'artifacts/b0/prepared-04')
        with tempfile.TemporaryDirectory() as work:
            output = Path(work)
            classes = output / 'classes'
            cp = [*engine, *libraries]
            compile_java(home, cp, [ROOT / p for p in [
                'interop/fabric/tool/mcfao/aot/ModCatalog.java',
                'interop/fabric/tool/mcfao/build/ModSnapshot.java',
                'interop/diagnostics/ModSnapshotProbe.java']], classes, output / 'compile')
            run = capture([str(home / 'bin/java'), '-cp', ':'.join(map(str,[classes,*cp])),
                           'mcfao.build.ModSnapshotProbe',str(classes)], output / 'run', 30)
            self.assertEqual(run['exitCode'], 0, (output / 'run/stderr.log').read_text())
            self.assertIn('MOD_SNAPSHOT_PARITY_PASS', (output / 'run/stdout.log').read_text())

    def test_residue_requires_review_instead_of_semantic_pass(self):
        from prepare_fabric_aot import semantic_compatibility
        result = semantic_compatibility({'stubbedMethods': ['mod/Gameplay#tick -> Loader.query']})
        self.assertEqual(result['status'], 'REQUIRES_REVIEW')
        self.assertFalse(result['runtimeVerified'])
        self.assertEqual(len(result['unsupportedMethods']), 1)
        self.assertEqual(semantic_compatibility({})['status'], 'NO_RESIDUE_REPORTED')
