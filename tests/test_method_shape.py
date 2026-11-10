import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from scan_method_shape import scan_code


class MethodShapeTests(unittest.TestCase):
    def test_counts_branches_invokes_and_switch_entries(self):
        code = bytes([0x12, 0x05,              # ldc
                      0x99, 0x00, 0x03,        # ifeq
                      0xB6, 0x00, 0x01,        # invokevirtual
                      0xAC])                   # ireturn
        shape = scan_code(code)
        self.assertEqual(shape["instructions"], 4)
        self.assertEqual(shape["invokes"], 1)
        self.assertEqual(shape["conditionalBranches"], 1)
        self.assertEqual(shape["returns"], 1)
        self.assertEqual(shape["snapshotSites"], 2)
        self.assertEqual(shape["shapeCostProxy"], 4)

    def test_tableswitch_padding_counts_every_case(self):
        # offset 0 -> pad 3, then default/low/high for 3 cases (low=0, high=2)
        code = bytes([0xAA, 0, 0, 0]) + (0).to_bytes(4, "big") + (0).to_bytes(4, "big") \
            + (2).to_bytes(4, "big") + bytes(12) + bytes([0xB1])
        shape = scan_code(code)
        self.assertEqual(shape["switches"], 1)
        self.assertEqual(shape["switchEntries"], 3)
        self.assertEqual(shape["returns"], 1)

    def test_lookupswitch_and_wide_are_decoded(self):
        code = bytes([0xAB, 0, 0, 0]) + (0).to_bytes(4, "big") + (1).to_bytes(4, "big") \
            + (7).to_bytes(4, "big") + (9).to_bytes(4, "big") + bytes([0xC4, 0x84, 0, 1, 0, 1, 0xB1])
        shape = scan_code(code)
        self.assertEqual(shape["switchEntries"], 1)
        self.assertEqual(shape["instructions"], 3)  # lookupswitch, wide iinc, return

    def test_truncated_instruction_is_reported_not_ignored(self):
        with self.assertRaises(ValueError):
            scan_code(bytes([0xB6, 0x00]))
        with self.assertRaises(ValueError):
            scan_code(bytes([0xAA]))

    def test_unsupported_opcode_is_reported(self):
        with self.assertRaises(ValueError):
            scan_code(bytes([0xFE]))

    def test_exception_handlers_only_add_snapshot_sites_through_their_splits(self):
        shape = scan_code(bytes([0x00, 0xB1]), exception_handlers=3)
        self.assertEqual(shape["exceptionHandlers"], 3)
        self.assertEqual(shape["snapshotSites"], 0)
        self.assertEqual(shape["snapshotSitesLower"], 0)

    def test_cost_proxy_scales_quadratically_in_snapshot_sites(self):
        small = scan_code(bytes([0x99, 0x00, 0x02] * 10 + [0xB1]))
        large = scan_code(bytes([0x99, 0x00, 0x02] * 20 + [0xB1]))
        self.assertEqual(large["snapshotSites"], 2 * small["snapshotSites"])
        # 10 sites x 11 instructions / 2 vs 20 sites x 21 instructions / 2: near-quadratic, not linear.
        self.assertEqual(small["shapeCostProxy"], 55)
        self.assertEqual(large["shapeCostProxy"], 210)
        self.assertGreater(large["shapeCostProxy"] / small["shapeCostProxy"], 3.5)


if __name__ == "__main__":
    unittest.main()
