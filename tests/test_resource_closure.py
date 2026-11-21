import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from capture import capture
from prepare_fabric_aot import compile_java, load_reference, verify_pack_classpath, verify_resource_closure

PREPARED = Path(os.environ.get("MCFAO_TEST_FABRIC_PREPARED", ROOT / "artifacts/b0/prepared-04"))


class ResourceClosureTests(unittest.TestCase):
    def test_bounded_constant_paths_and_unknown_branch(self):
        home, _, engine, _ = load_reference(PREPARED)
        with tempfile.TemporaryDirectory() as work:
            output = Path(work)
            classes = output / "classes"
            compile_java(home, engine, [ROOT / "interop/fabric/tool/mcfao/build/ResourceLookup.java",
                                        ROOT / "interop/diagnostics/ResourceLookupProbe.java"],
                         classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp", os.pathsep.join(map(str, [classes, *engine])),
                              "mcfao.build.ResourceLookupProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0, (output / "run/stderr.log").read_text())
            self.assertIn("RESOURCE_LOOKUP_PASS", (output / "run/stdout.log").read_text())

    def test_dynamic_pack_stream_matches_reference_with_only_one_resource_copy(self):
        home, _, engine, _ = load_reference(PREPARED)
        with tempfile.TemporaryDirectory() as work:
            output = Path(work)
            classes = output / "classes"
            compile_java(home, engine, [ROOT / "interop/fabric/tool/mcfao/build/ResourceLookup.java",
                                        ROOT / "interop/fabric/tool/mcfao/aot/ClasspathPackResources.java",
                                        ROOT / "interop/diagnostics/ResourceLookupProbe.java"],
                         classes, output / "compile")
            lowered = output / "PackStreamFixture.class"
            java = str(home / "bin/java")
            result = capture([java, "-cp", os.pathsep.join(map(str, [classes, *engine])),
                              "mcfao.build.ResourceLookupProbe", str(lowered)], output / "lower", 30)
            self.assertEqual(result["exitCode"], 0, (output / "lower/stderr.log").read_text())

            main = "mcfao.build.PackStreamFixture"
            path = "assets/fixture/shaders/opaque.vsh"
            target = "mcfao/mod-files/fixture/" + path
            data_path = "data/second_fixture/tags/stone.json"
            data_target = "mcfao/mod-files/second_fixture/" + data_path
            index = "mcfao/classpath-pack-resources.tsv"
            original = "mcfao/build/PackStreamFixture.class"
            reference, shipping = output / "reference.jar", output / "shipping.jar"
            for jar, transformed in ((reference, False), (shipping, True)):
                with zipfile.ZipFile(jar, "w") as archive:
                    archive.writestr(original, (lowered if transformed else classes / original).read_bytes())
                    archive.writestr(target if transformed else path, b"original shader")
                    archive.writestr(data_target if transformed else data_path, b"original data")
                    archive.writestr("assets/minecraft/shader.vsh", b"vanilla shader")
                    archive.writestr("mcfao/build/relative.csh", b"package relative")
                    if transformed:
                        archive.writestr(index, f"{path}\t{target}\n{data_path}\t{data_target}\n")
                        for helper in (classes / "mcfao/aot").glob("ClasspathPackResources*.class"):
                            archive.write(helper, helper.relative_to(classes).as_posix())

            verify_pack_classpath(shipping, 2)
            args = ["/" + path, "original shader", "/" + data_path, "original data",
                    "/assets/minecraft/shader.vsh", "vanilla shader", "relative.csh", "package relative",
                    "/assets/fixture/no-file", "MISSING"]
            for jar in (reference, shipping):
                result = capture([java, "-cp", str(jar), main, *args], output / jar.stem, 30)
                self.assertEqual(result["exitCode"], 0, (output / jar.stem / "stderr.log").read_text())

    def test_pack_index_rejects_bad_targets_and_canonical_duplicates(self):
        path = "assets/fixture/shader.vsh"
        target = "mcfao/mod-files/fixture/" + path
        with tempfile.TemporaryDirectory() as work:
            jar = Path(work) / "invalid.jar"
            for entries, index_target in (([], target), ([target, path], target), ([target], path)):
                with self.subTest(entries=entries, target=index_target):
                    with zipfile.ZipFile(jar, "w") as archive:
                        archive.writestr("mcfao/classpath-pack-resources.tsv", f"{path}\t{index_target}\n")
                        for name in entries:
                            archive.writestr(name, b"data")
                    with self.assertRaisesRegex(ValueError, "Invalid classpath pack stream target"):
                        verify_pack_classpath(jar, 1)

    def test_pack_index_rejects_omissions_and_conflicting_layers(self):
        path = "data/fixture/tags/sample.json"
        first = "mcfao/mod-files/first/" + path
        second = "mcfao/mod-files/second/" + path
        with tempfile.TemporaryDirectory() as work:
            jar = Path(work) / "incomplete.jar"
            index = "mcfao/classpath-pack-resources.tsv"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr(index, "")
                archive.writestr(first, b"first")
            with self.assertRaisesRegex(ValueError, "omits 1 unique paths"):
                verify_pack_classpath(jar, 0)
            verify_pack_classpath(jar, 0, layered=False)

            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr(index, f"{path}\t{first}\n")
                archive.writestr(first, b"first")
                archive.writestr(second, b"second")
            with self.assertRaisesRegex(ValueError, "ambiguous or inactive path"):
                verify_pack_classpath(jar, 1)

    def test_final_jar_bytes_and_missing_resource(self):
        with tempfile.TemporaryDirectory() as work:
            jar = Path(work) / "client.jar"
            source = b"first-party shader"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("fixture.fsh", source)
            row = dict(status="RETAINED", finalPath="fixture.fsh", bytes=len(source),
                       sha256=hashlib.sha256(source).hexdigest(), aotReadable="UNVERIFIED")
            verify_resource_closure(jar, [row])
            self.assertTrue(row["jarVerified"])
            self.assertEqual(row["aotReadable"], "UNVERIFIED")
            with self.assertRaisesRegex(ValueError, "fingerprint differs"):
                verify_resource_closure(jar, [dict(row, sha256="changed")])
            with self.assertRaisesRegex(ValueError, "missing from merged client"):
                verify_resource_closure(jar, [dict(row, finalPath="missing.fsh")])
