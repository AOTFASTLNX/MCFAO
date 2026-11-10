import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_method_splitter import java_home
from capture import ROOT

DIAGNOSTICS = ROOT / "compiler/metal-backend/tools/fabricaot/diag/PlayDiagnostics.java"
FIXTURE = """
package fixture;

import fabricaot.diag.PlayDiagnostics;

public final class DiagFixture {
    public static void main(String[] args) throws Exception {
        PlayDiagnostics.tick();
        PlayDiagnostics.login("ClientboundLoginPacket[playerId=7]");
        PlayDiagnostics.batchStart();
        PlayDiagnostics.chunk(0, 0);
        PlayDiagnostics.batch(9);
        PlayDiagnostics.chunkDecode(0, 0);
        PlayDiagnostics.radius(8);
        PlayDiagnostics.cacheCenter(0, 0);
        PlayDiagnostics.tracker("WaitingForServer");
        PlayDiagnostics.chunkReady(true);
        PlayDiagnostics.ready(true);
        PlayDiagnostics.sectionCheck("BlockPos{x=5, y=131, z=7}");
        for (int index = 0; index < 500; index++) {
            PlayDiagnostics.sectionVisible(index % 2 == 0);
        }
        PlayDiagnostics.clientPosition(5.5, 131.0, 7.5);
        PlayDiagnostics.serverPosition("ClientboundPlayerPositionPacket");
        PlayDiagnostics.connectionFailure(new RuntimeException("fixture failure"));
        PlayDiagnostics.channelInactive();
        Thread.sleep(2200L);
    }
}
"""


class PlayDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.home = java_home()
        except (SystemExit, OSError, ValueError):
            raise unittest.SkipTest("verified Java 25 home is not available")
        if not DIAGNOSTICS.is_file():
            raise unittest.SkipTest("PlayDiagnostics source is not present")

    def compile_and_run(self, directory: Path, enabled: bool) -> str:
        source = directory / "DiagFixture.java"
        source.write_text(FIXTURE)
        subprocess.run([str(self.home / "bin/javac"), "--release", "25", "-proc:none",
                        "-d", str(directory / "classes"), str(DIAGNOSTICS), str(source)],
                       check=True, capture_output=True, text=True, timeout=120)
        result = subprocess.run([
            str(self.home / "bin/java"), f"-Dmcfao.diag.play={'true' if enabled else 'false'}",
            "-cp", str(directory / "classes"), "fixture.DiagFixture"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_play_hooks_are_structured_and_switchable(self):
        with tempfile.TemporaryDirectory() as temp:
            enabled = self.compile_and_run(Path(temp), True)
            for event in ("configuration_to_play", "chunk_received", "chunk_decoded",
                          "chunk_batch_finished", "level_load_tracker", "level_load_ready",
                          "section_visibility", "client_position_send", "server_position",
                          "connection_exception", "channel_inactive", "heartbeat"):
                self.assertIn("event=" + event, enabled)
            self.assertIn("thread=main", enabled)
            # 500 section queries in one short run must not become 500 log lines.
            self.assertLessEqual(enabled.count("event=section_visibility"), 10)
        with tempfile.TemporaryDirectory() as temp:
            disabled = self.compile_and_run(Path(temp), False)
            self.assertNotIn("[MCFAO_DIAG]", disabled)

    def test_aot_enables_shared_arenas_and_runtime_diagnostics(self):
        builder = (ROOT / "tools/probe_client_graph.py").read_text()
        self.assertIn('"-H:+SharedArenaSupport"', builder)
        self.assertIn("io.netty,joptsimple,fabricaot", builder)
        injector = (ROOT / "tools/inject_metal_backend.py").read_text()
        self.assertIn("fabricaot/diag/PlayDiagnostics.class", injector)
        self.assertIn("LevelLoadTracker", injector)

    def test_connection_failure_keeps_the_original_error_name(self):
        with tempfile.TemporaryDirectory() as temp:
            output = self.compile_and_run(Path(temp), True)
            self.assertIn("error=java.lang.RuntimeException: fixture failure", output)
            self.assertIn("event=connection_exception_frame", output)


if __name__ == "__main__":
    unittest.main()
