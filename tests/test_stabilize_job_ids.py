import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "stabilize_job_ids.py"
spec = importlib.util.spec_from_file_location("stabilize_job_ids", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class StableJobIdentityTests(unittest.TestCase):
    def test_same_workday_requisition_keeps_id_across_location_and_slug_change(self):
        old = [{
            "id": "existing-applied-id",
            "company": "CACI",
            "title": "Cleared Software Engineer Intern - Summer 2027",
            "location": "Sterling, VA",
            "url": "https://caci.wd1.myworkdayjobs.com/external/job/437-DENVER-CO/Role_331999",
            "first_seen": "2026-09-01T00:00:00Z",
        }]
        refreshed = [{
            "id": "metadata-drifted-id",
            "company": "CACI, Inc.",
            "title": "Cleared Software Engineer Intern – Summer 2027",
            "location": "Denver, CO, US",
            "url": "https://caci.wd1.myworkdayjobs.com/External/job/Denver-CO-US/Updated-Role_331999",
        }]

        jobs, stats = mod.stabilize_jobs(refreshed, old)
        self.assertEqual(jobs[0]["id"], "existing-applied-id")
        self.assertEqual(jobs[0]["first_seen"], "2026-09-01T00:00:00Z")
        self.assertEqual(stats["preserved"], 1)

    def test_same_canonical_url_keeps_id_when_display_metadata_changes(self):
        old = [{
            "id": "old-id",
            "company": "Gecko Robotics",
            "title": "Software Engineer Intern",
            "location": "Pittsburgh",
            "url": "https://jobs.ashbyhq.com/gecko/abc123?utm_source=feed",
        }]
        refreshed = [{
            "id": "new-id",
            "company": "Gecko Robotics",
            "title": "Software Engineer Intern",
            "location": "Pittsburgh, PA",
            "url": "https://jobs.ashbyhq.com/gecko/abc123",
        }]

        jobs, _ = mod.stabilize_jobs(refreshed, old)
        self.assertEqual(jobs[0]["id"], "old-id")

    def test_new_provider_posting_id_is_independent_of_display_metadata(self):
        first = {
            "company": "WEX",
            "title": "Backend Software Engineer Intern",
            "location": "US - Remote",
            "url": "https://wexinc.wd5.myworkdayjobs.com/WEXInc/job/US---Remote/Backend-Software-Engineer-Intern_R22593",
        }
        second = {
            "company": "WEX Inc.",
            "title": "Fullstack Software Engineer Intern",
            "location": "Remote, United States",
            "url": "https://wexinc.wd5.myworkdayjobs.com/WEXInc/job/USA/Fullstack-Software-Engineer-Intern_R22593",
        }

        self.assertEqual(mod.deterministic_job_id(first), mod.deterministic_job_id(second))

    def test_metadata_fallback_remains_available_without_a_url(self):
        job = {"company": "Example", "title": "Software Intern", "location": "Remote", "url": None}
        self.assertEqual(len(mod.deterministic_job_id(job)), 16)


if __name__ == "__main__":
    unittest.main()
