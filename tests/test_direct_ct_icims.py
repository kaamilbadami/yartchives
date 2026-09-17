import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("direct_ct_icims", SCRIPT_DIR / "direct_ct_icims.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DirectCtIcimsTests(unittest.TestCase):
    def test_discovers_one_evidenced_ct_cs_icims_site(self):
        feed = {
            "jobs": [
                {
                    "company": "General Dynamics Electric Boat",
                    "title": "Information Technology, Software Engineering, & Computer Science - 2027 Summer Internship",
                    "states": ["CT"],
                    "profiles": ["cs"],
                    "url": "https://careers-gdeb.icims.com/jobs/20341/job",
                },
                {
                    "company": "General Dynamics Electric Boat",
                    "title": "Another Software Internship",
                    "states": ["CT"],
                    "profiles": ["cs"],
                    "url": "https://careers-gdeb.icims.com/jobs/20500/another/job?in_iframe=1",
                },
                {
                    "company": "Other",
                    "states": ["NY"],
                    "profiles": ["cs"],
                    "url": "https://careers-other.icims.com/jobs/100/job",
                },
            ]
        }
        sources = mod.discover_sources(feed)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["host"], "careers-gdeb.icims.com")
        self.assertEqual(sources[0]["search_url"], "https://careers-gdeb.icims.com/jobs/search")

    def test_extract_job_links_dedupes_ids_and_ignores_non_jobs(self):
        html = """
        <a href="/jobs/20338/cybersecurity---2027-summer-internship/job?mobile=true">Cyber</a>
        <a href="https://careers-gdeb.icims.com/jobs/20338/job">Duplicate</a>
        <a href="/jobs/20341/software/job">Software</a>
        <a href="/jobs/intro">Intro</a>
        """
        links = mod.extract_job_links(html, "https://careers-gdeb.icims.com/jobs/search")
        self.assertEqual(
            links,
            [
                "https://careers-gdeb.icims.com/jobs/20338/job",
                "https://careers-gdeb.icims.com/jobs/20341/job",
            ],
        )

    def test_authoritative_cybersecurity_intern_becomes_direct_job(self):
        source = {
            "key": "ct-auto-icims-careers-gdeb-icims-com",
            "name": "General Dynamics Electric Boat (auto-discovered iCIMS)",
            "company": "General Dynamics Electric Boat",
            "state": "CT",
            "homepage": "https://careers-gdeb.icims.com/jobs/intro",
        }
        inspection = {
            "status": "inspected",
            "posting": {
                "title": "Cybersecurity - 2027 Summer Internship",
                "date_posted": "2026-09-03",
                "locations": {"status": "authoritative", "values": ["Groton, CT, US"]},
            },
        }
        job = mod.job_from_inspection(
            source,
            "https://careers-gdeb.icims.com/jobs/20338/job",
            inspection,
            datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(job)
        self.assertEqual(job["company"], "General Dynamics Electric Boat")
        self.assertIn("cs", job["profiles"])
        self.assertIn("CT", job["states"])
        self.assertTrue(job["direct_employer"])
        self.assertEqual(job["posted_at"], "2026-09-03T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
