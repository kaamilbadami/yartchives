import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "direct_ct_workday.py"
spec = importlib.util.spec_from_file_location("direct_ct_workday", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def post(self, url, json=None, timeout=None):
        return FakeResponse(
            {
                "total": 3,
                "jobPostings": [
                    {
                        "title": "Software Engineering Intern - Summer 2027",
                        "locationsText": "Stamford, CT",
                        "externalPath": "/job/Stamford-CT/Software-Engineering-Intern_R1",
                        "postedOn": "Posted 3 Days Ago",
                    },
                    {
                        "title": "Software Engineering Intern - Summer 2027",
                        "locationsText": "New York, NY",
                        "externalPath": "/job/New-York-NY/Software-Engineering-Intern_R2",
                        "postedOn": "Posted Today",
                    },
                    {
                        "title": "Senior Software Engineer",
                        "locationsText": "Hartford, CT",
                        "externalPath": "/job/Hartford-CT/Senior-Software-Engineer_R3",
                        "postedOn": "Posted Today",
                    },
                ],
            }
        )


class DirectWorkdayTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "key": "ct-test-workday",
            "name": "Test Employer (direct)",
            "company": "Test Employer",
            "kind": "workday",
            "api_url": "https://example.test/wday/jobs",
            "public_base": "https://example.test/en-US/Careers",
            "homepage": "https://example.test/en-US/Careers",
            "state": "CT",
            "profile_hint": ["cs"],
            "search_terms": ["intern software"],
        }

    def test_target_state_handles_hyphenated_workday_locations(self):
        self.assertTrue(mod.is_target_state("US-CT-East Hartford-OBG", "CT"))
        self.assertTrue(mod.is_target_state("Stamford, Connecticut", "CT"))
        self.assertFalse(mod.is_target_state("Acton, Massachusetts", "CT"))

    def test_fetch_workday_filters_to_ct_student_roles(self):
        ref = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
        jobs = mod.fetch_workday_source(FakeSession(), self.source, ref)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Software Engineering Intern - Summer 2027")
        self.assertIn("CT", jobs[0]["states"])
        self.assertIn("cs", jobs[0]["profiles"])
        self.assertTrue(jobs[0]["url"].startswith("https://example.test/en-US/Careers/job/"))
        self.assertEqual(jobs[0]["posted_raw"], "3 Days")

    def test_direct_url_replaces_intermediary_url(self):
        ref = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
        incoming = mod.bf.base_job(
            company="Test Employer",
            title="Software Engineering Intern - Summer 2027",
            location="Stamford, CT",
            url="https://example.test/en-US/Careers/job/software_R1",
            posted_raw="3 days",
            source=self.source,
            section="Direct employer match",
            posted_at=ref,
        )
        incoming["direct_employer"] = True
        job_id = mod.stable_job_id(incoming)
        jobs = [
            {
                "id": job_id,
                "company": "Test Employer",
                "title": "Software Engineering Intern - Summer 2027",
                "location": "Stamford, CT",
                "url": "https://www.indeed.com/viewjob?jk=abc",
                "profiles": ["cs"],
                "states": ["CT"],
                "source_keys": ["other"],
                "source_names": ["Other"],
                "source_urls": ["https://other.test"],
                "first_seen": "2026-09-14T12:00:00Z",
                "last_seen": "2026-09-14T12:00:00Z",
            }
        ]
        mod.upsert_direct_job(jobs, incoming, {}, ref)
        self.assertEqual(jobs[0]["url"], "https://example.test/en-US/Careers/job/software_R1")
        self.assertIn("ct-test-workday", jobs[0]["source_keys"])
        self.assertTrue(jobs[0]["direct_employer"])


if __name__ == "__main__":
    unittest.main()
