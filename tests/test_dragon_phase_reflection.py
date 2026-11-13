"""Keep all vanilla dragon-phase constructors reachable to Native Image."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "net.minecraft.world.entity.boss.enderdragon.phases."
DRAGON = "net.minecraft.world.entity.boss.enderdragon.EnderDragon"


class DragonPhaseReflectionTests(unittest.TestCase):
    def test_all_vanilla_phase_constructors_are_registered(self):
        phases = {
            "DragonHoldingPatternPhase", "DragonStrafePlayerPhase",
            "DragonLandingApproachPhase", "DragonLandingPhase", "DragonTakeoffPhase",
            "DragonSittingFlamingPhase", "DragonSittingScanningPhase",
            "DragonSittingAttackingPhase", "DragonChargePlayerPhase",
            "DragonDeathPhase", "DragonHoverPhase",
        }
        config = json.loads((ROOT / "compiler/reflection-config.json").read_text(encoding="utf-8"))
        matches = [entry for entry in config if entry["name"].startswith(PREFIX)]
        self.assertEqual({entry["name"] for entry in matches}, {PREFIX + phase for phase in phases})
        self.assertEqual(len(matches), len(phases))
        for entry in matches:
            self.assertIn({"name": "<init>", "parameterTypes": [DRAGON]}, entry["methods"])


if __name__ == "__main__":
    unittest.main()
