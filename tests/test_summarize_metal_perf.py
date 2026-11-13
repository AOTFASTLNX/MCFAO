import importlib.util
import tempfile
import unittest
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("summarize_metal_perf", ROOT / "tools/summarize_metal_perf.py")
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)


class MetalPerfSummaryTests(unittest.TestCase):
    def test_legacy_gpu_zero_is_not_a_measurement(self):
        report = perf.summarize("prefix [MetalPerf] frames=300 interval_ms=33.3 submit_wait_ms=10 final_command_gpu_ms=0.000")
        self.assertEqual(report["total_windows"]["submitted"], 1)
        self.assertIn("cannot establish", report["interpretation"]["legacy_gpu"])
        self.assertIn("combines", report["interpretation"]["legacy_wait"])

    def test_presented_and_submitted_are_separate_and_discarded_independently(self):
        text = "\n".join([
            "[MetalPerf] submitted=300 submit_interval_ms=20 cpu_sync_wait_ms=3 gpu_completed=400",
            "[MetalPerf] submitted=300 submit_interval_ms=10 cpu_sync_wait_ms=1 gpu_completed=400",
            "[MetalPresented] intervals=300 fps=50 mean_ms=20 p95_ms=25 p99_ms=30",
            "[MetalPresented] intervals=300 fps=60 mean_ms=16.667 p95_ms=17 p99_ms=20",
        ])
        report = perf.summarize(text, discard=1, last=1)
        self.assertEqual(report["selected_windows"]["submitted"][0]["cpu_sync_wait_ms"], 1)
        self.assertEqual(report["selected_windows"]["presented"][0]["fps"], 60)
        self.assertIn("not GPU utilization", report["interpretation"]["modern_gpu"])

    def test_zip_selects_newest_run_without_extracting_world(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("c0-logs/run-9.log", "old")
                archive.writestr("c0-logs/run-10.log", "new")
                archive.writestr("game/saves/world.dat", "private")
            self.assertEqual(perf.read_log(path), "new")

    def test_rejects_invalid_selection(self):
        with self.assertRaises(ValueError):
            perf.summarize("", last=0)
        with self.assertRaises(ValueError):
            perf.summarize("", discard=-1)


if __name__ == "__main__":
    unittest.main()
