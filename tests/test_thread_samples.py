"""Thread-dump supervisor: schedule parsing and builder-pid discovery only (no analysis run)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from probe_thread_samples import find_builder_pid, parse_schedule


class ThreadSampleTests(unittest.TestCase):
    PS = "\n".join([
        "  501 /bin/zsh -c python3 -B tools/probe_client_graph.py --output /tmp/run-19",
        "  502 /usr/bin/python3 -B tools/probe_client_graph.py --output /tmp/run-19",
        "  503 /usr/bin/sandbox-exec -f /tmp/run-19/policy.sb /h/lib/svm/bin/native-image --no-fallback",
        "  504 /h/bin/java @/tmp/run-19/work/tmp/driverRoot-1/vminvocation.args --image-args-file=/tmp/run-19/work/tmp/x",
        "  505 /h/bin/java -jar /other/run-190/tool.jar",
        "  506 /Applications/Other.app/Contents/MacOS/Other --path /tmp/run-19",
        "  507 /h/bin/java @/tmp/run-18/work/tmp/driverRoot-2/vminvocation.args",
    ])

    def test_finds_only_the_builder_child(self):
        self.assertEqual(find_builder_pid(self.PS, "/tmp/run-19"), 504)

    def test_unrelated_commands_and_other_runs_are_ignored(self):
        self.assertIsNone(find_builder_pid(self.PS, "/tmp/run-20"))
        self.assertEqual(find_builder_pid(self.PS, "/tmp/run-18"), 507)

    def test_chooses_highest_pid_when_several_builders_match(self):
        text = "\n".join([
            "  610 /h/bin/java @/tmp/run-19/work/tmp/a/vminvocation.args",
            "  612 /h/bin/java @/tmp/run-19/work/tmp/b/vminvocation.args",
        ])
        self.assertEqual(find_builder_pid(text, "/tmp/run-19"), 612)

    def test_schedule_is_sorted_and_validated(self):
        self.assertEqual(parse_schedule("70,20, 40"), [20.0, 40.0, 70.0])
        with self.assertRaises(ValueError):
            parse_schedule("20,0")
        with self.assertRaises(ValueError):
            parse_schedule(" , ")


if __name__ == "__main__":
    unittest.main()
