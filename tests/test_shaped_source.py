import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from probe_shaped_methods import generate_source


class ShapedSourceTests(unittest.TestCase):
    def test_single_part_uses_one_static_initialiser(self):
        source = generate_source(4, 1)
        self.assertEqual(source.count("    static {\n"), 1)
        self.assertNotIn("static void part", source)
        self.assertEqual(source.count("keep("), 5)  # four calls plus the helper definition

    def test_split_keeps_total_calls_and_chains_parts(self):
        source = generate_source(10, 3)
        self.assertEqual(source.count("    static void part"), 3)
        self.assertIn("part0();", source)
        self.assertIn("part2();", source)
        calls = [line for line in source.splitlines() if line.strip().startswith("keep(") and "index" not in line]
        self.assertEqual(len(calls), 10)
        self.assertIn("keep(9, make(9));", source)

    def test_uneven_split_still_covers_every_index(self):
        source = generate_source(7, 4)
        for index in range(7):
            self.assertIn("keep(%d, make(%d));" % (index, index), source)

    def test_positive_inputs_are_required(self):
        with self.assertRaises(ValueError):
            generate_source(0, 1)
        with self.assertRaises(ValueError):
            generate_source(4, 0)


if __name__ == "__main__":
    unittest.main()
