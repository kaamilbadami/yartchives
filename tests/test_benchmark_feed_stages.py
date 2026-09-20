import unittest
import subprocess
import json
import tempfile
from pathlib import Path
import os
import sys

class BenchmarkFeedStagesTests(unittest.TestCase):
    def test_benchmark_runs_within_generous_threshold(self):
        """Test the feed benchmark runs properly and acts as a stable CI performance guard."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_json = Path(temp_dir) / "output.json"

            # We run it with a very small limit to just check that the script executes
            # properly and the overall time stays within a generous CI threshold.
            result = subprocess.run([
                "python3", "scripts/benchmark_feed_stages.py",
                "--limit", "1",
                "--output-json", str(output_json)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            self.assertEqual(result.returncode, 0, "Benchmark script failed to execute")
            self.assertTrue(output_json.exists(), "Benchmark did not produce JSON output")

            with open(output_json, "r") as f:
                data = json.load(f)

            total_time = data.get("total", 0)
            stages = data.get("stages", {})


            self.assertIn("collection", stages)
            self.assertIn("enrichment", stages)
            self.assertIn("link repair", stages)
            self.assertIn("ATS reconciliation", stages)
            self.assertIn("authoritative inspection", stages)
            self.assertIn("validation", stages)
            self.assertIn("audit", stages)
            # Use a generous threshold (150s) to ensure stable CI while preventing extreme regressions
            self.assertLess(total_time, 150, f"Benchmark total time exceeded 150 seconds: {total_time:.2f}s")
            self.assertTrue(isinstance(data.get("dominant"), str))


    def test_metrics_generation_shape(self):
        """Test that --record and --finalize produce the correct metrics shape."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            metrics_file = temp_path / "metrics.json"

            # Record a successful stage
            res1 = subprocess.run([
                "python3", "scripts/benchmark_feed_stages.py",
                "--metrics-file", str(metrics_file),
                "--record", "test stage 1",
                "--",
                "python3", "-c", "import time; time.sleep(0.1)"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(res1.returncode, 0)

            # Record a failing stage
            res2 = subprocess.run([
                "python3", "scripts/benchmark_feed_stages.py",
                "--metrics-file", str(metrics_file),
                "--record", "test stage 2",
                "--",
                "python3", "-c", "import sys; sys.exit(1)"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(res2.returncode, 1)

            # Finalize
            res3 = subprocess.run([
                "python3", "scripts/benchmark_feed_stages.py",
                "--metrics-file", str(metrics_file),
                "--finalize"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(res3.returncode, 0)

            self.assertTrue(metrics_file.exists())
            with open(metrics_file, "r") as f:
                history = json.load(f)

            self.assertEqual(len(history), 1)
            record = history[0]

            self.assertIn("timestamp", record)
            self.assertIn("total_duration", record)
            self.assertIn("dominant_stage", record)
            self.assertIn("failed_stage", record)
            self.assertIn("stages", record)

            self.assertEqual(record["failed_stage"], "test stage 2")

            stages = record["stages"]
            self.assertIn("test stage 1", stages)
            self.assertIn("test stage 2", stages)

            self.assertTrue(stages["test stage 1"]["success"])
            self.assertFalse(stages["test stage 2"]["success"])

            self.assertGreater(stages["test stage 1"]["duration"], 0)


if __name__ == "__main__":
    unittest.main()
