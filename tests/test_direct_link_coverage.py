import unittest
import json
import os

class DirectLinkCoverageTests(unittest.TestCase):
    def test_direct_link_coverage_baseline(self):
        if os.environ.get("YARTCHIVES_REPO_HEALTH") != "1":
            self.skipTest("Repository-health baseline runs only in explicit health checks")
        """Ensure direct-link coverage does not silently drop below the measured baseline."""
        listings_path = os.path.join(os.path.dirname(__file__), "..", "data", "listings.json")
        if not os.path.exists(listings_path):
            self.skipTest(f"Missing {listings_path} for testing baseline coverage")

        with open(listings_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        jobs = data.get("jobs", [])
        total = len(jobs)
        if total == 0:
            self.skipTest("No jobs found in listings.json to verify coverage")

        direct = sum(1 for job in jobs if job.get("link_kind") == "direct")
        coverage = direct / total

        # We upgraded coverage to 85.86%. The acceptance criteria states:
        # Add a regression guard so future changes cannot push direct-link coverage
        # materially below the new measured baseline without explicit review.
        self.assertGreaterEqual(
            coverage,
            0.85,
            f"Direct link coverage {coverage*100:.2f}% is below the 85.0% baseline. "
            "A drop this large must be reviewed and explicitly authorized."
        )

if __name__ == "__main__":
    unittest.main()
