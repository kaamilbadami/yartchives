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

            self.assertIn("source collection", stages)
            self.assertIn("normalization", stages)
            self.assertIn("authoritative inspection", stages)
            self.assertIn("validation", stages)
            self.assertIn("generated artifacts", stages)

            # Use a generous threshold (150s) to ensure stable CI while preventing extreme regressions
            self.assertLess(total_time, 150, f"Benchmark total time exceeded 150 seconds: {total_time:.2f}s")
            self.assertTrue(isinstance(data.get("dominant"), str))

if __name__ == "__main__":
    unittest.main()
