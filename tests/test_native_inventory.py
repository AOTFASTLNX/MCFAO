import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from inventory_client_native_calls import method_references


def utf(text):
    data = text.encode()
    return b'\x01'+struct.pack('>H',len(data))+data


class NativeInventoryTests(unittest.TestCase):
    def test_java25_method_reference_is_resolved(self):
        pool = [utf('org/lwjgl/opengl/GL11C'), b'\x07\x00\x01', utf('glDrawArrays'), utf('(III)V'),
                b'\x0c\x00\x03\x00\x04', b'\x0a\x00\x02\x00\x05']
        data=b'\xca\xfe\xba\xbe\x00\x00\x00\x45'+struct.pack('>H',len(pool)+1)+b''.join(pool)
        self.assertEqual(method_references(data), {('org/lwjgl/opengl/GL11C','glDrawArrays','(III)V')})

    def test_bad_header_is_rejected(self):
        with self.assertRaises(ValueError): method_references(b'not-a-class')

    def test_truncated_pool_is_rejected(self):
        with self.assertRaises(ValueError): method_references(b'\xca\xfe\xba\xbe\0\0\0\x45\0\x02\x01\0\x10x')

    def test_unknown_tag_is_rejected(self):
        with self.assertRaises(ValueError): method_references(b'\xca\xfe\xba\xbe\0\0\0\x45\0\x02\xff')

    def test_wide_constant_consumes_two_slots(self):
        data=b'\xca\xfe\xba\xbe\0\0\0\x45\0\x03\x05'+b'\0'*8
        self.assertEqual(method_references(data),set())
