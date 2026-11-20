from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import patch_gl41_client


class GL41ManifestTests(unittest.TestCase):
    def setUp(self):
        toolchain = Path(os.environ.get("MCFAO_TEST_GL41_TOOLCHAIN", ROOT / "artifacts/compiler/method-splitter-01"))
        report = toolchain / "result.json"
        if not report.is_file():
            self.skipTest("Requires pinned Java 25 / ASM")
        splitter = json.loads(report.read_text())
        self.home = Path(splitter["javaHome"])
        self.asm = [Path(row["path"]) for row in splitter["asmJars"]
                    if row["name"] in {"asm-9.9.jar", "asm-tree-9.9.jar"}]
        if (len(self.asm) != 2 or not all(p.is_file() for p in self.asm)
                or not all((self.home / "bin" / name).is_file() for name in ("java", "javac"))):
            self.skipTest("Pinned Java 25 / ASM paths are unavailable")

    def test_main_attributes_survive_and_stale_entry_signatures_are_removed(self):
        asm = os.pathsep.join(map(str, self.asm))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); harness = out / "ManifestCheck.java"
            harness.write_text(r'''package fabricaot.gl41;
import java.io.*; import java.util.jar.*;
public class ManifestCheck { public static void main(String[] args) throws Exception {
  String source="Manifest-Version: 1.0\r\nMulti-Release: true\r\nMain-Class: Game\r\n\r\nName: Game.class\r\nSHA-256-Digest: stale\r\n\r\n";
  byte[] clean=PatchDevice.cleanManifest(source.getBytes(java.nio.charset.StandardCharsets.UTF_8));
  Manifest result=new Manifest(new ByteArrayInputStream(clean));
  if(!result.getEntries().isEmpty()) throw new AssertionError("stale entry signatures retained");
  if(!"true".equals(result.getMainAttributes().getValue("Multi-Release"))) throw new AssertionError("MR attribute lost");
  if(!"Game".equals(result.getMainAttributes().getValue("Main-Class"))) throw new AssertionError("main class lost");
  if(!java.util.Arrays.equals(clean,PatchDevice.cleanManifest(clean))) throw new AssertionError("not idempotent");
}}''')
            sources = [ROOT / "compiler/gl41/tools/fabricaot/gl41/PatchDevice.java",
                       ROOT / "compiler/metal-backend/tools/fabricaot/metal/InjectBackend.java", harness]
            subprocess.run([self.home / "bin/javac", "-proc:none", "-cp", asm, "-d", out, *sources],
                           check=True, capture_output=True, timeout=60)
            subprocess.run([self.home / "bin/java", "-cp", str(out) + os.pathsep + asm,
                            "fabricaot.gl41.ManifestCheck"], check=True, capture_output=True, timeout=60)

    def run_patcher(self, client, output):
        with patch.object(patch_gl41_client, "register_tree"), redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()) as stderr:
            result = patch_gl41_client.main([
                "--client", str(client), "--output", str(output), "--graalvm-home", str(self.home),
                "--asm-jars", *map(str, self.asm),
            ])
        return result, stderr.getvalue()

    def test_missing_patch_targets_report_the_java_cause_and_log_path(self):
        with tempfile.TemporaryDirectory() as temp:
            client = Path(temp) / "incomplete.jar"
            with ZipFile(client, "w") as archive:
                archive.writestr("fixture.txt", "unmodified")
            output = Path(temp) / "output"
            code, error = self.run_patcher(client, output)
            self.assertNotEqual(code, 0)
            self.assertIn("Missing GL41 patch targets:", error)
            self.assertIn("net/minecraft/SystemReport.class", error)
            self.assertIn(str(output / "transform"), error)
            self.assertFalse((output / "result.json").exists())

    def test_full_client_accepts_both_hardware_diagnostic_changes(self):
        client = Path(os.environ.get("MCFAO_TEST_GL41_CLIENT", ROOT / "artifacts/ci/client-split.jar"))
        if not client.is_file():
            self.skipTest("Set MCFAO_TEST_GL41_CLIENT to a local split 26.1.2 client JAR")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            code, error = self.run_patcher(client, output)
            self.assertEqual(code, 0, error)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["status"], "GL41_CLIENT_PATCHED")
            self.assertIn("com/mojang/blaze3d/platform/GLX.class", result["changedEntries"])
            self.assertIn("net/minecraft/SystemReport.class", result["changedEntries"])
