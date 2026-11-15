import hashlib
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inventory_mod_opengl_calls import inventory


def utf8(value):
    b = value.encode('utf-8')
    return b'\x01' + struct.pack('>H', len(b)) + b


def class_with_reference(owner):
    # Minimal constant pool: Class, NameAndType and Methodref.
    pool = (utf8(owner) + b'\x07\x00\x01' + utf8('glGetString') + utf8('(I)J')
            + b'\x0c\x00\x03\x00\x04' + b'\x0a\x00\x02\x00\x05')
    return b'\xca\xfe\xba\xbe\x00\x00\x00\x3d\x00\x07' + pool


class InventoryTest(unittest.TestCase):
    def test_collects_gl_only_and_reports_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'input.jar'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('A.class', class_with_reference('org/lwjgl/opengl/GL11C'))
                z.writestr('B.class', class_with_reference('org/lwjgl/glfw/GLFW'))
            result = inventory([path])
            self.assertEqual(result['uniqueMethods'], 1)
            self.assertEqual(result['methods'][0]['name'], 'glGetString')
            self.assertEqual(result['methods'][0]['referencedBy'], ['input.jar:A'])
            self.assertEqual(result['inputs'][0]['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
    def test_invalid_class_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bad.jar'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('Bad.class', b'bad')
            with self.assertRaises(ValueError):
                inventory([path])


if __name__ == '__main__':
    unittest.main()
