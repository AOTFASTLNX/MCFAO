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
from aot_compatibility import (RENDER_PIPELINES, add_bytecode_results, attribute_failure,
                               bytecode_report, cached_bytecode_report, dynamic_risk,
                               issue, record_build_pass, transform_report)
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
    "third/Dependency": """
        package third;
        public class Dependency {
            public static int VALUE;
            public static void touch() {}
        }
    """,
    "third/LibraryCaller": """
        package third;
        public class LibraryCaller {
            static int value = Dependency.VALUE;
            public static void main(String[] args) { Dependency.touch(); }
            public Runnable optional() { return Dependency::touch; }
        }
    """,
    "first/DesktopImageCaller": """
        package first;
        public class DesktopImageCaller {
            public static boolean export(java.awt.image.BufferedImage image, java.io.File file)
                    throws java.io.IOException {
                return javax.imageio.ImageIO.write(image, "png", file);
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

    def test_attribution_requires_mechanism_evidence_and_keeps_owner(self):
        unknown = attribute_failure(["java.lang.NullPointerException: failed"])
        self.assertEqual(unknown["category"], "UNKNOWN")
        known = attribute_failure([
            "Caused by: org.graalvm.nativeimage.MissingResourceRegistrationError: sample.png",
            "    at fixture.Example.load(Example.java:12)",
        ], {"fixture/Example": "demo"})
        self.assertEqual(known["category"], "AOT_RESOURCE")
        self.assertEqual(known["modId"], "demo")
        self.assertEqual(known["status"], "REQUIRES_VALIDATION")

    def test_platform_and_dynamic_categories_do_not_conflate_apis(self):
        for owner, method, expected in (
            ("java/nio/file/Path", "toRealPath", "PLATFORM_REAL_PATH"),
            ("java/awt/Font", "<init>", "DESKTOP_AWT_DRAWING"),
            ("org/lwjgl/openal/EXTEfx", "alGenEffects", "OPENAL_EFX_UNVERIFIED"),
            ("example/Loader", "defineClass", None),
            ("java/lang/invoke/MethodHandles$Lookup", "defineHiddenClassWithClassData", "RUNTIME_CLASS_DEFINITION"),
            ("org/objectweb/asm/ClassWriter", "toByteArray", "RUNTIME_BYTECODE_GENERATOR_UNVERIFIED"),
            ("org/lwjgl/opengl/GL45C", "glBindTextureUnit", "OPENGL_AFTER_41"),
        ):
            with self.subTest(owner=owner, method=method):
                self.assertEqual(dynamic_risk(owner, method, "gl41"), expected)

    def test_mod_reports_keep_blocked_and_function_evidence_separate(self):
        report = transform_report({
            "status": "FABRIC_AOT_INPUT_PREPARED",
            "mods": [{"id": "one", "name": "One", "version": "1.0"}],
            "excludedMods": {"two": ["dependency"]},
            "transform": {"resolvedMods": [{"id": "one", "version": "1.0"}]},
        })
        report = add_bytecode_results(report, [
            issue("DYNAMIC_RESOURCE_UNRESOLVED", "warning", "sample", mod="one"),
        ], {}, ())
        record_build_pass(report)
        first, second = report["mods"]
        self.assertEqual(first["buildStatus"], "BUILD_PASS")
        self.assertEqual(first["functionStatus"], "UNVERIFIED")
        self.assertEqual(first["relevantChecks"], ["runtime-resource-read"])
        self.assertEqual(first["riskCount"], 1)
        self.assertEqual(second["buildStatus"], "BLOCKED")

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

    def test_desktop_image_export_reports_the_call_site_without_blocking(self):
        mod = self.jar("desktop-image.jar", lambda name: name == "first/DesktopImageCaller.class")
        _, _, findings, _ = bytecode_report(mod, [mod], "gl41")
        warnings = [row for row in findings if row["code"] == "DESKTOP_IMAGE_IOS_UNSUPPORTED"]
        self.assertEqual([(row["severity"], row["target"], row["location"]) for row in warnings], [
            ("warning", "javax/imageio/ImageIO.write",
             "first/DesktopImageCaller#export(Ljava/awt/image/BufferedImage;Ljava/io/File;)Z"),
        ])

    def test_missing_library_members_have_method_location_and_reachability(self):
        client = self.jar("main-fixture.jar", lambda name: name == "first/NoDefault.class")
        caller = self.jar("library-caller.jar", lambda name: name == "third/LibraryCaller.class",
                          {"META-INF/services/third.Service": "third.Missing # optional provider\n"})
        unavailable = self.root / "dependency.jar"
        data = (self.classes / "third/Dependency.class").read_bytes()
        with zipfile.ZipFile(unavailable, "w") as archive:
            archive.writestr("third/Dependency.class", data.replace(b"VALUE", b"OTHER").replace(b"touch", b"other"))
        settings = subprocess.run(["java", "-XshowSettings:properties", "-version"], check=True,
                                  capture_output=True, text=True, timeout=30).stderr
        home = next(Path(line.split("=", 1)[1].strip()) for line in settings.splitlines()
                    if line.strip().startswith("java.home ="))
        _, _, findings, graph = bytecode_report(
            client, [client, caller, unavailable], "gl41", java_home=home, entrypoint="third/LibraryCaller")
        expected = {
            ("MISSING_FIELD", "blocker", "third/LibraryCaller#<clinit>()V"),
            ("MISSING_METHOD", "blocker", "third/LibraryCaller#main([Ljava/lang/String;)V"),
            ("MISSING_METHOD", "warning", "third/LibraryCaller#optional()Ljava/lang/Runnable;"),
            ("SERVICE_PROVIDER_MISSING", "warning", "META-INF/services/third.Service"),
        }
        self.assertTrue(expected <= {(row["code"], row["severity"], row["location"]) for row in findings})
        self.assertTrue(all(row["archive"] == caller.name for row in findings))
        self.assertEqual(graph["classes"], 3)
        _, _, findings, _ = bytecode_report(
            client, [client, caller], "gl41", entrypoint="third/LibraryCaller")
        self.assertTrue(any(row["severity"] == "blocker" and row["target"] == "third/Dependency"
                            for row in findings))

    def test_preflight_cache_tracks_content_order_and_renderer(self):
        client = self.jar("cache-client.jar", lambda name: name == "first/NoDefault.class")
        caller = self.jar("cache-library.jar", lambda name: name == "third/LibraryCaller.class")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def scan(classpath, renderer):
                return cached_bytecode_report(root, client, classpath, renderer, java_home=root,
                                              required=(), entrypoint=None)

            cold = scan([client, caller], "gl41")
            warm = scan([client, caller], "gl41")
            self.assertFalse(cold[-1]["cacheHit"])
            self.assertTrue(warm[-1]["cacheHit"])
            self.assertEqual(cold[:-1], warm[:-1])
            self.assertFalse(scan([caller, client], "gl41")[-1]["cacheHit"])
            self.assertFalse(scan([client, caller], "metal")[-1]["cacheHit"])
            (root / (cold[-1]["key"] + ".json")).write_text("{}")
            self.assertFalse(scan([client, caller], "gl41")[-1]["cacheHit"])
            with zipfile.ZipFile(caller, "a") as archive:
                archive.writestr("changed.txt", "different content")
            self.assertFalse(scan([client, caller], "gl41")[-1]["cacheHit"])

    def test_higher_multi_release_definition_and_classpath_precedence(self):
        client = self.jar("mr.jar", lambda name: name == RENDER_PIPELINES + ".class",
                          {"META-INF/MANIFEST.MF": "Manifest-Version: 1.0\r\nMulti-Release: true\r\n\r\n"})
        entry = RENDER_PIPELINES + ".class"
        code = (self.classes / entry).read_bytes()
        with zipfile.ZipFile(client, "a") as archive:
            archive.writestr("META-INF/versions/25/" + entry,
                             code.replace(b"fabricaot/metal/", b"fixture/backend/"))
            archive.writestr("META-INF/versions/26/" + entry, code)
        bad = self.jar("shadowed.jar", lambda name: name == entry)
        _, _, findings, graph = bytecode_report(client, [client, bad], "gl41")
        self.assertFalse(any(row["severity"] == "blocker" for row in findings))
        self.assertEqual(graph["classes"], 1)
        _, _, findings, _ = bytecode_report(client, [bad, client], "gl41")
        self.assertTrue(any(row["code"] == "METAL_REFERENCE_ON_GL41" for row in findings))

    def test_bad_tracing_constructor_descriptor_is_reported(self):
        client = self.jar("reflection-negative.jar", lambda name: name == "first/ModConfigDTO.class")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trace = root / "trace"
            trace.mkdir()
            (trace / "reflect-config.json").write_text(json.dumps([{
                "name": "first.ModConfigDTO", "methods": [{"name": "<init>", "parameterTypes": ["int"]}]
            }]))
            _, report = collect_mdaf_configuration([], [], [trace], [client], root)
            self.assertTrue(any(row["status"] == "UNRESOLVED_MEMBERS" and row["type"] == "first.ModConfigDTO"
                                for row in report["reflectionResolution"]["findings"]))


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
