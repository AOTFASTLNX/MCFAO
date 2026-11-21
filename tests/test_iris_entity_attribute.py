"""Regress the audited Iris USHORT4 input mismatch observed on the iPad."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_fabric_aot import load_reference
from capture import capture
from config_reflection import class_shape
from zipfile import ZipFile


class IrisEntityAttributeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = Path(os.environ.get("MCFAO_TEST_IRIS_BUILD", ROOT / "artifacts/compat-r3-20261121/fabric-signed-retry"))
        commands = list(build.glob("aot/*/product/analysis/command.json"))
        if not commands:
            raise unittest.SkipTest("Requires the audited Iris 1.10.9 local build")
        argv = json.loads(commands[-1].read_text())["argv"]
        cls.cp = argv[argv.index("-cp") + 1]
        cls.home, _, _, _ = load_reference(Path(json.loads((build / "inputs.json").read_text())["config"]["prepared"]))
        if os.environ.get("MCFAO_TEST_IRIS_ENTITY_LOGS"):
            cls.out = Path(os.environ["MCFAO_TEST_IRIS_ENTITY_LOGS"]).resolve()
            cls.out.mkdir(parents=True, exist_ok=False)
        else:
            temp = tempfile.TemporaryDirectory(prefix="ncl-iris-entity-")
            cls.addClassCleanup(temp.cleanup)
            cls.out = Path(temp.name)
        cls.classes = cls.out / "classes"
        cls.fixed = cls.out / "fixed"
        sources = ["compiler/gl41/tools/fabricaot/gl41/PatchDevice.java",
                   "compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java",
                   "interop/diagnostics/IrisEntityAttributeProbe.java"]
        cls.run_tool("compile", [str(cls.home / "bin/javac"), "-proc:none", "-cp", cls.cp,
                                "-d", str(cls.classes), *sources])
        cls.run_tool("lower", [str(cls.home / "bin/java"), "-Xverify:all", "-cp",
                     str(cls.classes) + os.pathsep + cls.cp, "fabricaot.gl41.IrisEntityAttributeProbe",
                     "lower", cls.cp.split(os.pathsep)[0], str(cls.fixed)])

    @classmethod
    def run_tool(cls, name, argv):
        result = capture(argv, cls.out / name, 120)
        out = (cls.out / name / "stdout.log").read_text()
        err = (cls.out / name / "stderr.log").read_text()
        if result["exitCode"] != 0:
            raise AssertionError(out[-4000:] + err[-4000:])
        return out + err

    def test_actual_iris_ast_preserves_signed_ids(self):
        for fixed in (False, True):
            cp = os.pathsep.join(([str(self.fixed)] if fixed else []) + [str(self.classes), self.cp])
            out = self.run_tool("ast-" + str(fixed), [str(self.home / "bin/java"), "-Xverify:all", "-cp", cp,
                     "fabricaot.gl41.IrisEntityAttributeProbe", "fixed" if fixed else "original"])
            self.assertIn("IRIS_ENTITY_AST_PASS fixed=" + str(fixed).lower() + " exactIDs=65536", out)

    def test_exported_gl41_aot_input_uses_unsigned_entity(self):
        build = Path(os.environ.get("MCFAO_TEST_IRIS_ENTITY_FIXED_BUILD",
                                   ROOT / "artifacts/iris-fma-20261121/ios-build-r5"))
        if not (build / "result.json").is_file():
            self.skipTest("Requires completed r5 iOS build")
        commands = list(build.glob("aot/*/product/analysis/command.json"))
        argv = json.loads(commands[-1].read_text())["argv"]
        jar = argv[argv.index("-cp") + 1].split(os.pathsep)[0]
        target = "net/irisshaders/iris/pipeline/transform/transformer/EntityPatcher.class"
        with ZipFile(jar) as archive:
            methods = dict(class_shape(archive.read(target), graph=True)["bytecode"])
            literals = [operand[1] for method, operations in methods.items()
                        if method.startswith("patchEntityId(")
                        for opcode, operand in operations
                        if opcode in (18, 19) and isinstance(operand, tuple) and operand[0] == 8]
            self.assertIn("in uvec3 iris_Entity;", literals)
            self.assertIn("iris_entityInfo = ivec3(iris_Entity);", literals)
            self.assertNotIn("in ivec3 iris_Entity;", literals)
        report = list(build.glob("gl41-patch/*/product/result.json"))[-1]
        patched = json.loads(report.read_text())
        self.assertIn(target, patched["changedEntries"])
        self.assertIn("unsigned USHORT4", patched["irisEntityAttribute"])

    @unittest.skipUnless(sys.platform == "darwin", "Requires Metal")
    def test_metal_original_rejection_and_fixed_pipeline(self):
        binary = self.out / "metal-integer-attribute"
        self.run_tool("metal-compile", ["xcrun", "clang", "-fobjc-arc", "-Wall", "-Wextra", "-Werror",
                      "interop/diagnostics/MetalIntegerAttributeProbe.m", "-framework", "Foundation",
                      "-framework", "Metal", "-o", str(binary)])
        out = self.run_tool("metal-run", [str(binary)])
        self.assertIn("METAL_INTEGER_ATTRIBUTE_PASS fixed=0", out)
        self.assertIn("METAL_INTEGER_ATTRIBUTE_PASS fixed=1", out)
        self.assertIn("METAL_ENTITY_VERTEX_IDS_PASS exactIDs=65536", out)


if __name__ == "__main__":
    unittest.main()
