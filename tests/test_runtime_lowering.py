from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from capture import capture
from prepare_fabric_aot import compile_java as _compile_java, load_reference


def compile_java(home, classpath, sources, classes, log):
    sources = list(sources)
    lowering = ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java"
    rule_engine = ROOT / "interop/fabric/tool/mcfao/build/AdaptationRuleEngine.java"
    if lowering in sources and rule_engine not in sources:
        sources.append(rule_engine)
    return _compile_java(home, classpath, sources, classes, log)


def newest_merged_client():
    jars = sorted((ROOT / "artifacts/mcfao").glob(
        "fabric-pack-*/metal-injection/*/product/client-26.1.2-metal.jar"), key=lambda path: path.stat().st_mtime)
    if not jars:
        raise unittest.SkipTest("Requires a built Fabric pack")
    return jars[-1]


def newest_metal_backend():
    jars = sorted((ROOT / "artifacts/graphics").glob("metal-*/metal-backend.jar"),
                  key=lambda path: path.stat().st_mtime)
    if not jars:
        raise unittest.SkipTest("Requires a built Metal backend")
    return jars[-1]


class RuntimeLoweringTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_jade_tooltip_mod_names_answer_from_the_generated_table(self):
        home, _, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, engine, [
                ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java",
                ROOT / "interop/diagnostics/LoaderMetadataProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *engine])),
                              "mcfao.build.LoaderMetadataProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_LOADER_METADATA_PASS",
                          (output / "run/stdout.log").read_text())

    def test_mods_asking_for_their_own_jar_get_a_nominal_path(self):
        home, _, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, engine, [
                ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java",
                ROOT / "interop/fabric/tool/mcfao/aot/ModFiles.java",
                ROOT / "interop/diagnostics/ModFileProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *engine])),
                              "mcfao.build.ModFileProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_MOD_FILE_PASS",
                          (output / "run/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_json_reads_through_a_mod_wrapper_register_their_type(self):
        home, _, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, engine, [
                ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java",
                ROOT / "interop/diagnostics/SerializationRootProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *engine])),
                              "mcfao.build.SerializationRootProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_SERIALIZATION_ROOT_PASS",
                          (output / "run/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_custom_stage_singletons_and_lazy_identity(self):
        home, libraries, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        classpath = [*engine, *libraries]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, classpath, [
                *(ROOT / "interop/fabric/tool/mcfao/build").glob("*.java"),
                ROOT / "interop/diagnostics/ExportGenerationProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *classpath])),
                              "mcfao.build.ExportGenerationProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_STAGE_SINGLETON_CACHE_PASS", (output / "run/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_glitchcore_event_types_are_resolved_at_build_time(self):
        home, _, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, engine, [
                ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java",
                ROOT / "interop/diagnostics/GlitchCoreEventProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *engine])),
                              "mcfao.build.GlitchCoreEventProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_GLITCHCORE_EVENT_LOWERING_PASS",
                          (output / "run/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_fabric_api_interfaces_are_pinned_for_dual_initializers(self):
        home, libraries, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        classpath = [*engine, *libraries]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, classpath, [
                *(ROOT / "interop/fabric/tool/mcfao/build").glob("*.java"),
                ROOT / "interop/diagnostics/FabricApiClosureProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *classpath])),
                              "mcfao.build.FabricApiClosureProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_FABRIC_API_CLOSURE_PASS",
                          (output / "run/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_mixin_plugin_early_init_is_replayed_in_closed_world(self):
        home, libraries, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        classpath = [*engine, *libraries]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, classpath, [
                *(ROOT / "interop/fabric/tool/mcfao/build").glob("*.java"),
                ROOT / "interop/diagnostics/ExportGenerationProbe.java",
                ROOT / "interop/diagnostics/ImmediatelyFastInitProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *classpath])),
                              "mcfao.build.ImmediatelyFastInitProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_IMMEDIATELYFAST_EARLY_INIT_PASS",
                          (output / "run/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_indigo_renderer_decision_without_runtime_plugin(self):
        home, _, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, engine, [
                ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java",
                ROOT / "interop/diagnostics/IndigoGateProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *engine])),
                              "mcfao.build.IndigoGateProbe"], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_INDIGO_GATE_LOWERING_PASS",
                          (output / "run/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_render_pipelines_are_gated_by_the_shader_bundle(self):
        home, libraries, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        client = next(path for path in libraries if path.name == "26.1.2.jar")
        metal = newest_metal_backend()
        classpath = [metal, *engine, *libraries]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, classpath, [
                ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java",
                ROOT / "compiler/metal-backend/src/fabricaot/metal/BundledPipelines.java",
                ROOT / "interop/diagnostics/PipelineGateProbe.java",
            ], classes, output / "compile")
            run = ["-cp", ":".join(map(str, [classes, *classpath])), "mcfao.build.PipelineGateProbe"]
            rewritten = capture([str(home / "bin/java"), *run, "rewrite", str(client)], output / "rewrite", 30)
            self.assertEqual(rewritten["exitCode"], 0, (output / "rewrite/stderr.log").read_text())
            stdout = (output / "rewrite/stdout.log").read_text()
            self.assertIn("MCFAO_PIPELINE_GATE_PASS", stdout)
            self.assertIn("MCFAO_REAL_PIPELINE_GATE_PASS", stdout)
            known = output / "known"
            bundled = capture([str(home / "bin/java"), *run, "bundle", str(known), "known"], output / "bundle", 30)
            self.assertEqual(bundled["exitCode"], 0, (output / "bundle/stderr.log").read_text())
            self.assertIn("MCFAO_PIPELINE_BUNDLE_PASS known", (output / "bundle/stdout.log").read_text())
            unreadable = capture([str(home / "bin/java"), *run, "bundle", str(output / "open"), "open"],
                                 output / "open", 30)
            self.assertEqual(unreadable["exitCode"], 0, (output / "open/stderr.log").read_text())
            self.assertIn("MCFAO_PIPELINE_BUNDLE_PASS open", (output / "open/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_framework_configs_are_discovered_without_the_loader(self):
        home, _, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        client = newest_merged_client()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, engine, [
                ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java",
                ROOT / "interop/diagnostics/ConfigDiscoveryProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *engine])),
                              "mcfao.build.ConfigDiscoveryProbe", str(client)], output / "run", 30)
            self.assertEqual(result["exitCode"], 0, (output / "run/stderr.log").read_text())
            self.assertIn("MCFAO_CONFIG_DISCOVERY_PASS", (output / "run/stdout.log").read_text())

    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(),
                         "Requires the pinned local Java/ASM toolchain")
    def test_mod_resource_namespaces_reach_the_builtin_pack(self):
        home, libraries, engine, _ = load_reference(ROOT / "artifacts/b0/prepared-04")
        client = next(path for path in libraries if path.name == "26.1.2.jar")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            classes = output / "classes"
            classes.mkdir()
            compile_java(home, engine, [
                ROOT / "interop/fabric/tool/mcfao/build/RuntimeLowering.java",
                ROOT / "interop/diagnostics/ModNamespacesProbe.java",
            ], classes, output / "compile")
            result = capture([str(home / "bin/java"), "-cp",
                              ":".join(map(str, [classes, *engine])),
                              "mcfao.build.ModNamespacesProbe", str(client)], output / "run", 30)
            self.assertEqual(result["exitCode"], 0,
                             (output / "run/stderr.log").read_text())
            stdout = (output / "run/stdout.log").read_text()
            self.assertIn("MCFAO_MOD_NAMESPACES_PASS", stdout)
            self.assertIn("MCFAO_REAL_PACK_BUILDER_PASS", stdout)
