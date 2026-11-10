import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_shader_toolchain import extract
from verify_evidence import verify
from translate_shaders import interface_locations,validate_bindings

class ShaderInterfaceTests(unittest.TestCase):
    @staticmethod
    def varying(kind,name,location,columns=1):
        return {'kind':kind,'name':name,'location':location,'baseType':13,'width':32,'components':2,'columns':columns,'array':[]}
    def test_unused_vertex_output_cannot_shift_fragment_texcoord(self):
        vertex={'resources':[self.varying('output','animation',0),self.varying('output','texCoord',1)]}
        fragment={'resources':[self.varying('input','texCoord',0)]}
        mapping=interface_locations(vertex,fragment)
        self.assertEqual(mapping['texCoord'],1)
    def test_missing_or_differently_typed_varying_is_rejected(self):
        vertex={'resources':[self.varying('output','texCoord',1)]}
        bad=self.varying('input','texCoord',0);bad['components']=3
        with self.assertRaisesRegex(ValueError,'varying mismatch'):interface_locations(vertex,{'resources':[bad]})
    def test_only_the_four_real_builtin_uniforms_are_implicit(self):
        pipeline={'uniforms':[],'samplers':[],'attributes':[]};data={'resources':[{'kind':'uniform','name':'Globals','metalIndex':0}]}
        validate_bindings(pipeline,data,{'resources':[]})
        data['resources'][0]['name']='UnregisteredBlock'
        with self.assertRaisesRegex(ValueError,'Undeclared'):validate_bindings(pipeline,data,{'resources':[]})

class ShaderToolCacheTests(unittest.TestCase):
    def test_archive_cannot_escape_extraction_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'source.tar.gz'
            with tarfile.open(archive,'w:gz') as stream:
                info=tarfile.TarInfo('../escaped');info.size=4
                stream.addfile(info,io.BytesIO(b'data'))
            with self.assertRaises((tarfile.TarError,ValueError)):extract(archive,root/'cache')
            self.assertFalse((root/'escaped').exists())

    def test_modified_extracted_source_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'source.tar.gz'
            with tarfile.open(archive,'w:gz') as stream:
                info=tarfile.TarInfo('source/CMakeLists.txt');info.size=5
                stream.addfile(info,io.BytesIO(b'fixed'))
            extract(archive,root/'cache');source=root/'cache/source/CMakeLists.txt';source.write_text('modified')
            with self.assertRaisesRegex(ValueError,'Modified cached tool source'):extract(archive,root/'cache')
            self.assertEqual(source.read_text(),'modified')

    def test_explicit_tool_binary_hash_is_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);binary=root/'build/tool';binary.parent.mkdir();binary.write_bytes(b'compiled tool')
            (root/'result.json').write_text(json.dumps({'binaries':{'compiler':{'path':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}}}))
            self.assertEqual(verify(root)['status'],'PASS')
            binary.write_bytes(b'modified tool')
            self.assertEqual(verify(root)['status'],'FAIL')

if __name__=='__main__':unittest.main()
