import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("direct_greenhouse", SCRIPT_DIR / "direct_greenhouse.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DirectGreenhouseTests(unittest.TestCase):
    def test_discovers_one_evidenced_cs_board(self):
        feed = {
            "jobs": [
                {
                    "company": "Schonfeld",
                    "profiles": ["cs"],
                    "link_kind": "direct",
                    "url": "https://job-boards.greenhouse.io/schonfeld/jobs/8171692",
                },
                {
                    "company": "Schonfeld",
                    "profiles": ["cs"],
                    "link_kind": "direct",
                    "url": "https://boards.greenhouse.io/schonfeld/jobs/8171699?gh_jid=8171699",
                },
                {
                    "company": "Other",
                    "profiles": ["finance-econ"],
                    "link_kind": "direct",
                    "url": "https://job-boards.greenhouse.io/other/jobs/123456",
                },
            ]
        }
        sources = mod.discover_sources(feed)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["board_token"], "schonfeld")
        self.assertEqual(
            sources[0]["api_url"],
            "https://boards-api.greenhouse.io/v1/boards/schonfeld/jobs",
        )

    def test_authoritative_us_cs_intern_becomes_direct_job(self):
        source = {
            "key": "auto-greenhouse-schonfeld",
            "name": "Schonfeld (auto-discovered Greenhouse)",
            "company": "Schonfeld",
            "board_token": "schonfeld",
            "homepage": "https://job-boards.greenhouse.io/schonfeld",
        }
        item = {
            "id": 8171696,
            "title": "2027 Cybersecurity Operations Intern",
            "location": {"name": "New York, NY"},
            "absolute_url": "https://job-boards.greenhouse.io/schonfeld/jobs/8171696",
        }
        job = mod.job_from_item(
            source,
            item,
            datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(job)
        self.assertEqual(job["company"], "Schonfeld")
        self.assertIn("cs", job["profiles"])
        self.assertIn("NY", job["states"])
        self.assertTrue(job["direct_employer"])
        self.assertEqual(job["greenhouse_job_id"], "8171696")
        self.assertEqual(
            job["url"],
            "https://job-boards.greenhouse.io/schonfeld/jobs/8171696",
        )

    def test_rejects_nonstudent_noncs_and_nonus_roles(self):
        source = {
            "key": "auto-greenhouse-example",
            "name": "Example (auto-discovered Greenhouse)",
            "company": "Example",
            "board_token": "example",
            "homepage": "https://job-boards.greenhouse.io/example",
        }
        reference = datetime(2026, 9, 17, tzinfo=timezone.utc)
        cases = [
            {"id": 1, "title": "Software Engineer", "location": {"name": "New York, NY"}},
            {"id": 2, "title": "Marketing Intern", "location": {"name": "New York, NY"}},
            {"id": 3, "title": "Software Engineering Intern", "location": {"name": "London, UK"}},
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertIsNone(mod.job_from_item(source, item, reference))

    def test_board_token_like_company_is_replaced_by_authoritative_board_brand(self):
        source = {
            "key": "auto-greenhouse-sage49",
            "name": "Sage49 (auto-discovered Greenhouse)",
            "company": "Sage49",
            "board_token": "sage49",
            "homepage": "https://job-boards.greenhouse.io/sage49",
            "api_url": "https://boards-api.greenhouse.io/v1/boards/sage49/jobs",
        }

        class Response:
            def __init__(self, *, text="", payload=None):
                self.text = text
                self._payload = payload
                self.status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(url)
                if url == source["homepage"]:
                    return Response(text="<html><head><title>Jobs at Sage</title></head></html>")
                return Response(payload={
                    "jobs": [{
                        "id": 6131191004,
                        "title": "Software Engineering Intern (Edge) – Summer 2027",
                        "location": {"name": "New York, NY"},
                        "absolute_url": "https://job-boards.greenhouse.io/sage49/jobs/6131191004",
                    }]
                })

        jobs = mod.fetch_source(Session(), source, datetime(2026, 9, 17, tzinfo=timezone.utc))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Sage")

    def test_board_list_is_bounded_to_matching_sibling_roles(self):
        source = {
            "key": "auto-greenhouse-example",
            "name": "Example (auto-discovered Greenhouse)",
            "company": "Example",
            "board_token": "example",
            "homepage": "https://job-boards.greenhouse.io/example",
            "api_url": "https://boards-api.greenhouse.io/v1/boards/example/jobs",
        }

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "jobs": [
                        {"id": 10, "title": "Software Engineering Intern", "location": {"name": "Boston, MA"}},
                        {"id": 11, "title": "Software Engineering Intern", "location": {"name": "Toronto, Canada"}},
                        {"id": 12, "title": "Sales Intern", "location": {"name": "New York, NY"}},
                    ]
                }

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return Response()

        session = Session()
        jobs = mod.fetch_source(session, source, datetime(2026, 9, 17, tzinfo=timezone.utc))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["greenhouse_job_id"], "10")
        self.assertEqual(session.calls[0][0], source["api_url"])


if __name__ == "__main__":
    unittest.main()
