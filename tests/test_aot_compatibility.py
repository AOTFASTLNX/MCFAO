"""Regression tests for final classpath validation and generated reachability metadata."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from aot_compatibility import RENDER_PIPELINES, add_bytecode_results, bytecode_report, transform_report
from probe_client_graph import collect_mdaf_configuration
from run_b0_reference import execute


JAVA_FIXTURES = {
    "fabricaot/metal/BundledPipelines": """
        package fabricaot.metal;
        public final class BundledPipelines {
            public static Object register(Object input) { return input; }
        }
    """,
    "net/minecraft/client/renderer/RenderPipelines": """
        package net.minecraft.client.renderer;
        import fabricaot.metal.BundledPipelines;
        public final class RenderPipelines {
            static final Object PIPELINE = register(new Object());
            static Object register(Object input) { return BundledPipelines.register(input); }
        }
    """,
    "com/google/gson/Gson": """
        package com.google.gson;
        public class Gson {
            public <T> T fromJson(String json, Class<T> type) { return null; }
        }
    """,
    "first/TypedLoader": """
        package first;
        import com.google.gson.Gson;
        public class TypedLoader<T> {
            private final Class<T> type;
            TypedLoader(Class<T> type, String name) { this.type = type; }
            T defaults() throws ReflectiveOperationException {
                return type.getConstructor().newInstance();
            }
            T decode(Gson parser, String json) { return parser.fromJson(json, type); }
        }
    """,
    "first/ModConfigDTO": """
        package first;
        public class ModConfigDTO {
            public ModConfigDTO() {}
            public Nested nested;
            public static class Nested { public int value; }
        }
    """,
    "first/NoDefault": """
        package first;
        public class NoDefault { private NoDefault() {} }
    """,
    "first/FirstMod": """
        package first;
        public class FirstMod {
            static final TypedLoader<ModConfigDTO> LOADER = new TypedLoader<>(ModConfigDTO.class, "one");
            static final TypedLoader<NoDefault> OTHER = new TypedLoader<>(NoDefault.class, "two");
            public static Object resource() { return FirstMod.class.getResource("defaults.json"); }
        }
    """,
    "second/OptionalLibrary": """
        package second;
        public class OptionalLibrary {}
    """,
    "second/SecondMod": """
        package second;
        public class SecondMod extends OptionalLibrary {
            static final Object optional = new OptionalLibrary();
            public native void desktopNative();
            public void runtimeDefine(ClassLoader parent) throws Exception {
                java.lang.invoke.MethodHandles.lookup().defineClass(new byte[0]);
            }
        }
    """,
}


@unittest.skipUnless(shutil.which("javac"), "JDK required for classfile regression fixtures")
class AotCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.classes = cls.root / "classes"
        sources = []
        for name, source in JAVA_FIXTURES.items():
            path = cls.root / (name + ".java")
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_text(source)
            sources.append(path)
        subprocess.run(["javac", "-proc:none", "-d", cls.classes, *sources],
                       check=True, capture_output=True, timeout=30)

    def jar(self, name, include, resources=None):
        jar = self.root / name
        with zipfile.ZipFile(jar, "w") as archive:
            for path in sorted(self.classes.rglob("*.class")):
                relative = path.relative_to(self.classes).as_posix()
                if include(relative):
                    archive.write(path, relative)
            for resource, contents in (resources or {}).items():
                archive.writestr(resource, contents)
        return jar

    def test_gl41_rejects_metal_registration_before_native_image(self):
        client = self.jar("render.jar", lambda name: name == RENDER_PIPELINES + ".class")
        backend = self.jar("metal.jar", lambda name: name.startswith("fabricaot/metal/"))
        missing = bytecode_report(client, [client], "gl41", required=[RENDER_PIPELINES])
        self.assertIn("METAL_REFERENCE_ON_GL41", {row["code"] for row in missing[2]})
        for renderer, expected in (("gl41", True), ("metal", False)):
            _, _, findings, graph = bytecode_report(client, [client, backend], renderer)
            self.assertEqual(any(row["severity"] == "blocker" for row in findings), expected)
            self.assertGreater(graph["classInitializerEdges"], 0)

    def test_freecam_shape_registers_only_real_public_no_arg_constructible_dto(self):
        jar = self.jar("typed.jar", lambda name: name.startswith(("first/", "com/google/gson/")),
                       {"first/defaults.json": "{}"})
        inferred, resources, findings, graph = bytecode_report(jar, [jar], "gl41")
        by_name = {entry["name"]: entry for entry in inferred}
        self.assertTrue(by_name["first.ModConfigDTO"]["allDeclaredConstructors"])
        self.assertTrue(by_name["first.ModConfigDTO$Nested"]["allDeclaredFields"])
        self.assertNotIn("first.NoDefault", by_name)
        fix = next(row for row in findings if row["code"] == "TYPED_GSON_CONFIG")
        self.assertEqual(fix["target"], "first/ModConfigDTO")
        absence = next(row for row in findings if row["code"] == "CONFIG_NO_PUBLIC_NOARG")
        self.assertEqual(absence["target"], "first/NoDefault")
        self.assertGreater(graph["constructorEdges"], 0)

        with tempfile.TemporaryDirectory() as output:
            config, report = collect_mdaf_configuration(
                [], inferred, [], [jar], Path(output), {"resource-config.json": resources})
            self.assertIn("first.ModConfigDTO",
                          {row["name"] for row in json.loads((config / "reflect-config.json").read_text())})
            self.assertEqual(json.loads((config / "resource-config.json").read_text()),
                             {"resources": {"includes": [{"pattern": r"first/defaults\.json"}]}})
            self.assertEqual(report["reflectionResolution"]["status"], "RESOLVED_IN_SHIPPED_ARCHIVES")

    def test_missing_mandatory_superclass_blocks_known_entrypoint_only(self):
        mod = self.jar("second.jar", lambda name: name == "second/SecondMod.class")
        library = self.jar("optional.jar", lambda name: name == "second/OptionalLibrary.class")
        _, _, findings, _ = bytecode_report(mod, [mod], "gl41")
        self.assertEqual({row["severity"] for row in findings}, {"warning"})
        self.assertIn("RUNTIME_CLASS_DEFINITION", {row["code"] for row in findings})
        self.assertIn("MOD_NATIVE_METHOD", {row["code"] for row in findings})
        _, _, findings, graph = bytecode_report(mod, [mod], "gl41", required=["second/SecondMod"])
        self.assertIn("MISSING_REQUIRED_TYPE", {row["code"] for row in findings})
        _, _, findings, _ = bytecode_report(mod, [mod, library], "gl41", required=["second/SecondMod"])
        self.assertNotIn("MISSING_REQUIRED_TYPE", {row["code"] for row in findings})
        self.assertIn("classInitializers", graph)

    def test_stage_pass_leaves_startup_and_device_unverified(self):
        report = transform_report({"status": "FABRIC_AOT_INPUT_PREPARED", "renderer": "gl41",
                                   "transform": {"resolvedMods": [{"id": "fixture"}]}})
        report = add_bytecode_results(report, [], {}, [])
        self.assertEqual(report["stages"], {
            "static": "PASS", "transform": "PASS", "aot": "SKIPPED",
            "startup": "UNVERIFIED", "device": "UNVERIFIED",
        })


class BuildLogTests(unittest.TestCase):
    def test_sandbox_runner_redacts_before_persisting_complete_or_split_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / "tmp").mkdir()
            log = work / "capture"
            command = [
                sys.executable, "-c",
                "import os, time; os.write(1,b'Authorization: Bear'); time.sleep(.05);"
                "os.write(1,b'er opaque-token\\n'); os.write(2,b'access_token=another-token')",
            ]
            result = execute(command, log, work)
            self.assertEqual(result["exitCode"], 0)
            self.assertEqual((log / "stdout.log").read_text(), "Authorization: [REDACTED]\n")
            self.assertEqual((log / "stderr.log").read_text(), "access_token=[REDACTED]")
