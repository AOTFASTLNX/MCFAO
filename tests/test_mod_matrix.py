"""The compatibility matrix must never invent a verdict from a successful build."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate_mod_matrix as matrix


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class ModMatrixTests(unittest.TestCase):
    def make_pack(self, root: Path, smoke_status: str = "", smoke_log: str = "") -> Path:
        build = root / "artifacts" / "mcfao" / "fabric-pack-99"
        write(build / "result.json", {"status": "SIGNED_DEVICE_APP"})
        write(build / "classpath-check.json", {"classes": 100, "unloadable": 0})
        write(build / "classpath-members-check.json", {"classes": 100, "unloadable": 2})
        write(build / "fabric" / "hash" / "product" / "result.json", {
            "status": "FABRIC_AOT_INPUT_PREPARED",
            "mods": [{"id": "alpha", "name": "Alpha", "version": "1.0"},
                     {"id": "beta", "name": "Beta", "version": "2.0"}],
            "excludedMods": {"gamma": ["Unsupported runtime class/native loading: X.defineClass"]},
            "jarIds": {"alpha.jar": ["alpha"], "beta.jar": ["beta"]},
            "transform": {
                "resolvedMods": [{"id": "alpha", "version": "1.0"},
                                 {"id": "beta", "version": "2.0"}],
                "resourceNamespaces": ["minecraft", "alpha"],
            },
        })
        curated = root / "artifacts" / "mcfao" / "curated-verification-mods-01"
        curated.mkdir(parents=True)
        (curated / "alpha.jar").write_bytes(b"jar")
        (curated / "beta.jar").write_bytes(b"jar")
        isolated = root / "artifacts" / "mcfao" / "incompatible-01"
        write(isolated / "result.json", {"mods": [
            {"modId": "delta", "version": "4.0", "level": "platform",
             "reason": "needs OpenGL", "evidence": {"simulatorLog": "pack-1/game.log"}}]})
        smoke = root / "artifacts" / "mcfao" / "fabric-pack-99-simulator"
        smoke.mkdir(parents=True)
        (smoke / "game.log").write_text(smoke_log or (
            "MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS\n"
            "java.lang.IllegalStateException: blocked\n"))
        if smoke_status:
            write(smoke / "result.json", {"status": smoke_status})
        return build

    def collect(self, root: Path, evidence: dict | None = None,
                smoke_status: str = "", smoke_log: str = ""):
        build = self.make_pack(root, smoke_status=smoke_status, smoke_log=smoke_log)
        evidence_file = root / "evidence.json"
        if evidence is not None:
            write(evidence_file, evidence)
        with mock.patch.object(matrix, "ROOT", root), \
             mock.patch.object(matrix, "BUILDS", root / "artifacts" / "mcfao"), \
             mock.patch.object(matrix, "CURATED", root / "artifacts" / "mcfao" / "curated-verification-mods-01"), \
             mock.patch.object(matrix, "ISOLATED", root / "artifacts" / "mcfao" / "incompatible-01"), \
             mock.patch.object(matrix, "EVIDENCE", evidence_file):
            data = matrix.collect(build)
            text = matrix.render(data)
        return data, text

    def test_a_successful_build_is_never_reported_as_function_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            data, text = self.collect(Path(directory))
            rows = {row["id"]: row for row in data["rows"]}
            self.assertEqual(rows["alpha"]["status"], "BUILD_PASS")
            self.assertEqual(rows["beta"]["status"], "BUILD_PASS")
            self.assertEqual(rows["gamma"]["status"], "BLOCKED")
            self.assertEqual(rows["delta"]["status"], "BLOCKED")
            self.assertEqual(data["count"]["FUNCTION_PASS"], 0)
            self.assertEqual(data["count"]["DEVICE_PASS"], 0)
            self.assertIn("BLOCKED / NOT RUN", text)
            self.assertIn("pack-99", text)
            self.assertIn("| `BUILD_PASS` | 2 |", text)
            self.assertIn("java.lang.IllegalStateException: blocked", text)

    def test_blocked_rows_point_at_their_own_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            data, text = self.collect(Path(directory))
            rows = {row["id"]: row for row in data["rows"]}
            self.assertIn("#/excludedMods/gamma", rows["gamma"]["evidence"])
            self.assertIn("incompatible-01/result.json", rows["delta"]["evidence"])
            self.assertIn("导出期排除", text)
            self.assertIn("预先隔离", text)
            self.assertIn("Iris 保持隔离", text)

    def test_only_a_manual_observation_can_upgrade_a_row(self):
        with tempfile.TemporaryDirectory() as directory:
            data, text = self.collect(Path(directory), {
                "alpha": {"status": "FUNCTION_PASS", "note": "在运行的游戏内看到 Alpha 的 HUD",
                          "evidence": "pack-99-simulator/game.log#L42", "tests": "tests/test_alpha.py"},
                "gamma": {"status": "BUILD_PASS", "note": "试图降级"},
            })
            rows = {row["id"]: row for row in data["rows"]}
            self.assertEqual(rows["alpha"]["status"], "FUNCTION_PASS")
            self.assertIn("pack-99-simulator/game.log#L42", rows["alpha"]["evidence"])
            # A downgrade is ignored: the derived verdict is stronger.
            self.assertEqual(rows["gamma"]["status"], "BLOCKED")
            self.assertIn("| `FUNCTION_PASS` | 1 |", text)

    def test_a_passing_smoke_never_reports_startup_noise_as_a_crash(self):
        # oshi cannot identify the simulator OS and throws on every single launch; treating that
        # as "the first crash" invents a blocker out of a healthy log.
        log = (
            "java.lang.UnsupportedOperationException: Operating system not supported: Unknown\n"
            "MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS\n"
            "Dev joined the game\n"
            "MCFAO_F3_CLIENT_WORLD_JOIN_PASS\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            data, text = self.collect(Path(directory), smoke_status="SIMULATOR_WORLD_SMOKE_PASS",
                                      smoke_log=log)
            self.assertEqual(data["smoke"]["crash"], "")
            self.assertNotIn("首个崩溃", text)
            self.assertIn("未出现致命崩溃", text)
            self.assertIn("判据已全中", text)
            self.assertNotIn("BLOCKED / NOT RUN", text)

    def test_missing_pack_is_reported_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(matrix, "BUILDS", Path(directory) / "empty"):
                with self.assertRaises(SystemExit):
                    matrix.latest_build()


if __name__ == "__main__":
    unittest.main()
