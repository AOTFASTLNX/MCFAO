import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class GL41ManifestTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "artifacts/b0/prepared-04/result.json").is_file(), "Requires pinned Java 25 / ASM")
    def test_main_attributes_survive_and_stale_entry_signatures_are_removed(self):
        prepared = json.loads((ROOT / "artifacts/b0/prepared-04/result.json").read_text())
        home = Path(prepared["javaHome"])
        asm = [row["path"] for row in prepared["engineLibraries"] if Path(row["path"]).name.startswith(("asm-", "asm-tree-"))]
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
            subprocess.run([str(home/"bin/javac"), "-proc:none", "-cp", ":".join(asm), "-d", str(out), *map(str,sources)], check=True, capture_output=True)
            subprocess.run([str(home/"bin/java"), "-cp", str(out)+":"+":".join(asm), "fabricaot.gl41.ManifestCheck"], check=True, capture_output=True)
