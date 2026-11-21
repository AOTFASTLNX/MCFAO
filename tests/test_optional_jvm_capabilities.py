"""Execute the capability API and audited Iris bytecode; opt in to native compilation."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from capture import capture
from native_image_home import native_image_home
from prepare_fabric_aot import load_reference
from config_reflection import class_shape


class OptionalJvmCapabilitiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = Path(os.environ.get("MCFAO_TEST_IRIS_BUILD", ROOT / "artifacts/compat-r3-20261121/fabric-signed-retry"))
        commands = list(cls.build.glob("aot/*/product/analysis/command.json"))
        if not commands:
            raise unittest.SkipTest("Set MCFAO_TEST_IRIS_BUILD to an existing audited Iris build")
        cls.original_argv = json.loads(commands[-1].read_text())["argv"]
        cls.classpath = cls.original_argv[cls.original_argv.index("-cp") + 1].split(os.pathsep)
        inputs = json.loads((cls.build / "inputs.json").read_text())
        cls.home, _, _, _ = load_reference(Path(inputs["config"]["prepared"]))
        if os.environ.get("MCFAO_TEST_IRIS_LOGS"):
            cls.output = Path(os.environ["MCFAO_TEST_IRIS_LOGS"]).resolve()
            cls.output.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory(prefix="ncl-iris-tests-")
            cls.addClassCleanup(temporary.cleanup)
            cls.output = Path(temporary.name)
        cls.classes = cls.output / "classes"
        cls.fixed = cls.output / "fixed"
        cls.classes.mkdir()
        sources = ["interop/fabric/tool/mcfao/build/AdaptationRuleEngine.java",
                   "interop/fabric/tool/mcfao/build/OptionalJvmCapabilityLowering.java",
                   "interop/fabric/tool/mcfao/aot/OptionalJvmCapabilities.java",
                   "interop/diagnostics/OptionalJvmCapabilitiesProbe.java",
                   "interop/diagnostics/OptionalJvmCapabilityLoweringProbe.java",
                   "interop/diagnostics/IrisShadowProbe.java",
                   "interop/diagnostics/IrisShadowOriginalProbe.java"]
        cls.run_command("compile", [str(cls.home / "bin/javac"), "-proc:none", "-cp",
                        os.pathsep.join(cls.classpath), "-d", str(cls.classes), *sources])
        cls.run_command("lowering", [str(cls.home / "bin/java"), "-Xverify:all", "-cp",
                        os.pathsep.join([str(cls.classes), *cls.classpath]),
                        "mcfao.build.OptionalJvmCapabilityLoweringProbe", cls.classpath[0], str(cls.fixed)])

    @classmethod
    def run_command(cls, name, argv, timeout=120):
        report = capture(argv, cls.output / name, timeout)
        stdout = (cls.output / name / "stdout.log").read_text()
        stderr = (cls.output / name / "stderr.log").read_text()
        if report["exitCode"] != 0 or report["timedOut"]:
            raise AssertionError(f"{name}: {report['exitCode']}\n{stdout[-4000:]}\n{stderr[-4000:]}")
        return stdout

    def cp(self, fixed=True):
        return os.pathsep.join(([str(self.fixed)] if fixed else []) + [str(self.classes), *self.classpath])

    def test_jvm_optional_capability_and_exception_contract(self):
        out = self.run_command("jvm-capabilities", [str(self.home / "bin/java"), "-Xverify:all", "-cp",
                               self.cp(), "mcfao.aot.OptionalJvmCapabilitiesProbe"])
        self.assertIn("OPTIONAL_JVM_CAPABILITIES_PASS", out)

    def test_real_iris_fma_and_non_fma_culling(self):
        for enabled in (False, True):
            out = self.run_command(f"jvm-fma-{enabled}", [str(self.home / "bin/java"), "-Xverify:all",
                                   "-XX:" + ("+" if enabled else "-") + "UseFMA", "-cp", self.cp(),
                                   "mcfao.diagnostics.IrisShadowProbe"])
            self.assertIn(f"IRIS_SHADOW_PASS FMA={str(enabled).lower()}", out)

    def test_rule_preserves_all_algorithm_methods_and_rejects_shape_changes(self):
        self.assertIn("unchanged algorithm methods=22",
                      (self.output / "lowering/stdout.log").read_text())

    def test_exported_aot_input_contains_fix(self):
        fixed_build = Path(os.environ.get("MCFAO_TEST_IRIS_FIXED_BUILD",
                               ROOT / "artifacts/iris-fma-20261121/ios-build"))
        commands = list(fixed_build.glob("aot/*/product/analysis/command.json"))
        if not commands:
            self.skipTest("Requires the completed fixed iOS AOT build")
        argv = json.loads(commands[-1].read_text())["argv"]
        jar = argv[argv.index("-cp") + 1].split(os.pathsep)[0]
        target = "net/irisshaders/iris/shadows/frustum/advanced/AdvancedShadowCullingFrustum.class"
        with zipfile.ZipFile(jar) as archive, zipfile.ZipFile(self.classpath[0]) as original:
            fixed = {method: list(body) for method, body in
                     class_shape(archive.read(target), graph=True)["bytecode"]}
            raw = {method: list(body) for method, body in
                   class_shape(original.read(target), graph=True)["bytecode"]}
            for method, body in raw.items():
                if not method.startswith("<clinit>"):
                    self.assertEqual(fixed[method], body, method)
            init = fixed["<clinit>()V"]
            self.assertEqual(len(init), 3)
            self.assertEqual(init[0][1], (10, "mcfao/aot/OptionalJvmCapabilities", "isFmaEnabled", "()Z"))
            for name in ("mcfao/aot/OptionalJvmCapabilities.class",
                         "mcfao/aot/OptionalJvmCapabilities$BooleanCapability.class"):
                self.assertIn(name, archive.namelist())
        reports = list(fixed_build.glob("fabric/*/product/work/transform.json"))
        self.assertTrue(reports)
        rules = json.loads(reports[-1].read_text())["adaptationRules"]
        self.assertTrue(any(r["id"] == "jvm.optional.hotspot-fma.v1" and r["status"] == "APPLIED"
                            for r in rules))

    def test_scan_exact_classpath_for_related_management_calls(self):
        sites = []
        effective = set()
        for path in self.classpath:
            with zipfile.ZipFile(path) as jar:
                for name in jar.namelist():
                    if not name.endswith(".class") or name.startswith(("META-INF/", "__MACOSX/")) or name in effective:
                        continue
                    effective.add(name)
                    data = jar.read(name)
                    if not any(term in data for term in (b"HotSpotDiagnosticMXBean", b"getPlatformMXBean", b"getVMOption", b"UseFMA")):
                        continue
                    shape = class_shape(data, graph=True)
                    for method, operations in shape["bytecode"]:
                        for opcode, operand in operations:
                            if isinstance(operand, tuple) and operand[0] in (10, 11):
                                _, owner, member, descriptor = operand
                                if (owner == "java/lang/management/ManagementFactory" and member.startswith("getPlatformMXBean")
                                        or owner.startswith("com/sun/management/") and member == "getVMOption"):
                                    sites.append(dict(archive=path, caller=shape["name"] + "#" + method,
                                                      owner=owner, member=member, descriptor=descriptor))
        (self.output / "management-call-sites.json").write_text(json.dumps(sites, indent=2) + "\n")
        self.assertTrue(any("AdvancedShadowCullingFrustum#<clinit>" in site["caller"] for site in sites))

    @unittest.skipUnless(os.environ.get("MCFAO_TEST_NATIVE_IMAGE") == "1", "Native Image probe is opt-in")
    def test_native_image_original_failure_and_fixed_real_iris(self):
        # Strip embedded application/dependency build directives for this focused executable.
        # Preserve the effective classpath order and every selected class byte. In particular,
        # Netty's build-time initialization directives belong to the full-game build, not this probe.
        probe_jar = self.output / "game-classes.jar"
        effective = set()
        with zipfile.ZipFile(probe_jar, "w", zipfile.ZIP_DEFLATED) as dest:
            for path in self.classpath:
                with zipfile.ZipFile(path) as source:
                    for name in source.namelist():
                        if (name.endswith(".class") and not name.startswith(("META-INF/", "__MACOSX/"))
                                and name not in effective):
                            effective.add(name)
                            dest.writestr(name, source.read(name))
        # JOML's Java-version probes use cached Class fields, so these precise queries
        # need metadata when the full-game metadata has been stripped above.
        reflection = self.output / "probe-reflection.json"
        reflection.write_text(json.dumps([
            {"name": "java.lang.Float", "queriedMethods": [
                {"name": "floatToRawIntBits", "parameterTypes": ["float"]}]},
            {"name": "java.lang.Double", "queriedMethods": [
                {"name": "doubleToRawLongBits", "parameterTypes": ["double"]}]},
            {"name": "java.lang.Long", "queriedMethods": [
                {"name": "rotateLeft", "parameterTypes": ["long", "int"]}]},
            {"name": "java.lang.Math", "queriedMethods": [
                {"name": "fma", "parameterTypes": ["float", "float", "float"]}]},
        ]))
        with native_image_home(self.home) as clean:
            for fixed in (False, True):
                label = "native-fixed" if fixed else "native-original"
                cp = os.pathsep.join(([str(self.fixed)] if fixed else [])
                                     + [str(self.classes), str(probe_jar)])
                main = "mcfao.diagnostics.IrisShadowProbe" if fixed else "mcfao.diagnostics.IrisShadowOriginalProbe"
                binary = self.output / label
                self.run_command(label + "-build", [str(clean / "bin/native-image"), "--no-fallback", "-O1",
                    "--parallelism=2", "-J-Xmx3g", "--initialize-at-run-time", "--exact-reachability-metadata",
                    "-H:ReflectionConfigurationFiles=" + str(reflection),
                    "-cp", cp, "-o", str(binary), main], 1200)
                out = self.run_command(label + "-run", [str(binary), "unavailable"])
                self.assertIn("IRIS_SHADOW_PASS FMA=false capability=UNAVAILABLE" if fixed
                              else "IRIS_ORIGINAL_FAILURE_REPRODUCED", out)


if __name__ == "__main__":
    unittest.main()
