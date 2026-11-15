import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_lwjgl_opengl_ios import descriptor_parts, mangle


class OpenGLShimGeneratorTests(unittest.TestCase):
    def test_jni_mangling_matches_native_symbols(self):
        self.assertEqual(mangle("org/lwjgl/opengl/GL11C"), "org_lwjgl_opengl_GL11C")
        self.assertEqual(mangle("nglGetString"), "nglGetString")

    def test_primitives_only(self):
        self.assertEqual(descriptor_parts("(IZJFD)V"), ("IZJFD", "V"))
        self.assertEqual(descriptor_parts("()J"), ("", "J"))
        for descriptor in ("(Ljava/lang/String;)V", "([I)V", "(J)Ljava/lang/String;"):
            with self.assertRaises(ValueError):
                descriptor_parts(descriptor)


if __name__ == "__main__":
    unittest.main()
