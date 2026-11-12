"""Only a line that proves the Mod's own code ran may upgrade it to LOAD_PASS."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import scan_mod_evidence as scan


LOG = "\n".join([
    "[12:32:48] [Render thread/INFO]: [MCFAO_ENTRYPOINT] mod=alpha stage=main class=com.example.Alpha",
    "[12:32:48] [Render thread/INFO]: java.lang.RuntimeException: Asset load failed in beta",
    "[12:32:48] [Render thread/ERROR]: [beta] Unable to initialize renderer",
    "[12:32:48] [Render thread/INFO]: Registered synced data key gamma:slot for minecraft:player",
    "[12:32:48] [Render thread/INFO]: Loading assets/delta/lang/en_us.json",
    "[12:32:49] [Render thread/INFO]: Start loading plugin from : com.example.EpsilonPlugin",
    "\tat com.example.Zeta.<clinit>(Zeta.java:12)",
    "[12:32:49] [Render thread/INFO]: Builtin shader registered",
])


def mods(*ids: str) -> list[dict]:
    return [{"id": item, "name": item.capitalize()} for item in ids]


class ScanModEvidenceTests(unittest.TestCase):
    def run_scan(self, log_text: str = LOG, entries: dict | None = None):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "game.log"
            log.write_text(log_text)
            grouped = {key: [{"definition": value}] for key, value in (entries or {}).items()}
            return scan.scan(log, mods("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "shader"),
                             grouped)

    def test_a_dispatch_trace_is_direct_proof(self):
        results = self.run_scan()
        self.assertEqual(results["alpha"]["dispatched"]["line"], 1)
        self.assertEqual(results["alpha"]["dispatched"]["stage"], "main")

    def test_a_token_in_prose_is_not_proof(self):
        # `delta` only appears inside an asset path, and `shader` inside a generic vanilla line.
        results = self.run_scan()
        self.assertEqual(results["delta"]["clean"], [])
        self.assertEqual(results["shader"]["clean"], [])

    def test_errors_and_stack_frames_are_never_proof(self):
        results = self.run_scan()
        self.assertEqual([hit["severity"] for hit in results["beta"]["hits"]], ["ERROR"])
        self.assertEqual(results["beta"]["clean"], [])
        # `zeta` only appears as a stack frame, which says nothing about its health.
        self.assertEqual(results["zeta"]["hits"], [])

    def test_a_registration_line_names_the_mod_that_logged_it(self):
        results = self.run_scan()
        self.assertEqual(results["gamma"]["clean"][0]["line"], 4)
        self.assertEqual(results["gamma"]["clean"][0]["token"], "gamma")

    def test_entrypoint_packages_are_searchable_too(self):
        results = self.run_scan(entries={"epsilon": "com.example.Epsilon"})
        self.assertEqual(results["epsilon"]["clean"][0]["line"], 6)

    def test_emit_evidence_never_overwrites_a_manual_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "evidence.json"
            table.write_text(json.dumps({
                "_readme": "x",
                "beta": {"status": "FUNCTION_PASS", "note": "人工观察", "evidence": "shot.png"},
            }))
            results = {
                "alpha": {"mod": "alpha", "name": "Alpha", "dispatched": {"line": 1, "stage": "main", "cls": "A"},
                          "clean": [], "hits": []},
                "beta": {"mod": "beta", "name": "Beta", "dispatched": {"line": 2, "stage": "main", "cls": "B"},
                         "clean": [], "hits": []},
                "delta": {"mod": "delta", "name": "Delta", "dispatched": None, "clean": [], "hits": []},
            }
            added = scan.emit_evidence(results, Path("artifacts/mcfao/fabric-pack-99"), table)
            self.assertEqual(added, ["alpha"])
            written = json.loads(table.read_text())
            self.assertEqual(written["beta"]["status"], "FUNCTION_PASS")
            self.assertEqual(written["alpha"]["status"], "LOAD_PASS")
            self.assertIn("fabric-pack-99-simulator/game.log#L1", written["alpha"]["evidence"])
            self.assertNotIn("delta", written)




class ProducerContractTests(unittest.TestCase):
    """The scanner parses a line the exporter builds in Java; both sides must agree."""

    EXPORTER = ROOT / "interop/fabric/tool/mcfao/build/AotExport.java"

    def test_the_marker_the_exporter_prints_is_parseable(self):
        line = ("[12:32:48] [Render thread/INFO]: [STDOUT]: [MCFAO_ENTRYPOINT] "
                "mod=advancednetherite stage=main class=com.autovw.advancednetherite.AdvancedNetheriteFabric")
        parsed = scan.dispatch_lines([(7, line)])
        self.assertEqual(parsed["advancednetherite"],
                         {"line": 7, "stage": "main",
                          "cls": "com.autovw.advancednetherite.AdvancedNetheriteFabric"})

    def test_the_trace_is_emitted_once_per_dispatch_path(self):
        source = self.EXPORTER.read_text()
        # Two paths (ref-form provider and interface-form entrypoint) both need the trace, and it
        # has to come after the callback: printing before it would only prove "started".
        self.assertEqual(source.count("emitEntrypointDispatched(start, entry);"), 2)
        self.assertIn('start.visitMethodInsn(INVOKEINTERFACE, entry.type(), entry.method(), "()V", true);\n'
                      "            emitEntrypointDispatched(start, entry);", source)
        self.assertIn('"[MCFAO_ENTRYPOINT] mod="', source)


if __name__ == "__main__":
    unittest.main()
