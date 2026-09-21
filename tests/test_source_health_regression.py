import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import parallel_ats_collect as pac

class SourceHealthRegressionTests(unittest.TestCase):
    def test_run_parallel_handles_exceptions(self):
        def good_task():
            return {"jobs": [], "sources": {"a": {"status": "healthy"}}}

        def bad_task():
            raise RuntimeError("Something went wrong")

        results = pac.run_parallel({"good": good_task, "bad": bad_task})
        self.assertEqual(results["good"]["sources"]["a"]["status"], "healthy")
        self.assertEqual(results["bad"], {})

if __name__ == "__main__":
    unittest.main()
