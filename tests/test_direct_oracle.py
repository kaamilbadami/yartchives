import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("direct_oracle", SCRIPT_DIR / "direct_oracle.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DirectOracleTests(unittest.TestCase):
    def test_discovers_only_fully_resolved_candidate_experience_sites(self):
        universe = {
            "employers": [
                {
                    "id": "amex",
                    "name": "American Express",
                    "careers_url": "https://careers.example.com/en/sites/CX_1",
                    "provider": {"family": "oracle", "status": "resolved"},
                    "careers_resolution": {"status": "resolved"},
                },
                {
                    "id": "bare",
                    "name": "Bare Tenant",
                    "provider": {"family": "oracle", "status": "resolved"},
                    "careers_resolution": {"status": "provider_resolved"},
                },
                {
                    "id": "taleo",
                    "name": "Legacy Taleo",
                    "careers_url": "https://legacy.taleo.net/careersection/ext/jobsearch.ftl",
                    "provider": {"family": "oracle", "status": "resolved"},
                    "careers_resolution": {"status": "resolved"},
                },
            ]
        }
        sources = mod.discover_sources(universe)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["site_number"], "CX_1")
        self.assertEqual(
            sources[0]["api_url"],
            "https://careers.example.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        )

    def test_us_cs_student_requisition_becomes_direct_job(self):
        source = {
            "key": "auto-oracle-amex-cx-1",
            "name": "American Express (resolved Oracle)",
            "company": "American Express",
            "site_number": "CX_1",
            "homepage": "https://careers.example.com/en/sites/CX_1",
        }
        item = {
            "Id": "26011916",
            "Title": "Campus Undergraduate Summer Internship Program - 2027 Software Engineer",
            "PrimaryLocation": "New York, NY, United States",
            "PrimaryLocationCountry": "US",
            "PostedDate": "2026-08-03",
        }
        job = mod.job_from_item(source, item, datetime(2026, 9, 17, tzinfo=timezone.utc))
        self.assertIsNotNone(job)
        self.assertEqual(job["company"], "American Express")
        self.assertIn("cs", job["profiles"])
        self.assertIn("NY", job["states"])
        self.assertTrue(job["direct_employer"])
        self.assertEqual(job["oracle_site_number"], "CX_1")
        self.assertEqual(job["oracle_job_id"], "26011916")
        self.assertEqual(job["url"], "https://careers.example.com/en/sites/CX_1/job/26011916")

    def test_rejects_nonstudent_noncs_and_nonus_roles(self):
        source = {
            "key": "auto-oracle-example",
            "name": "Example (resolved Oracle)",
            "company": "Example",
            "site_number": "CX_1",
            "homepage": "https://careers.example.com/en/sites/CX_1",
        }
        reference = datetime(2026, 9, 17, tzinfo=timezone.utc)
        cases = [
            {"Id": "1", "Title": "Software Engineer", "PrimaryLocation": "New York, NY", "PrimaryLocationCountry": "US"},
            {"Id": "2", "Title": "Marketing Intern", "PrimaryLocation": "New York, NY", "PrimaryLocationCountry": "US"},
            {"Id": "3", "Title": "Software Engineering Intern", "PrimaryLocation": "London, UK", "PrimaryLocationCountry": "GB"},
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertIsNone(mod.job_from_item(source, item, reference))

    def test_fetch_uses_bounded_oracle_finder_and_requisition_list(self):
        source = {
            "key": "auto-oracle-example",
            "name": "Example (resolved Oracle)",
            "company": "Example",
            "site_number": "CX_1",
            "homepage": "https://careers.example.com/en/sites/CX_1",
            "api_url": "https://careers.example.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        }

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "items": [{
                        "TotalJobsCount": 2,
                        "requisitionList": [
                            {
                                "Id": "10",
                                "Title": "Software Engineering Intern",
                                "PrimaryLocation": "Boston, MA, United States",
                                "PrimaryLocationCountry": "US",
                                "PostedDate": "2026-09-01",
                            },
                            {
                                "Id": "11",
                                "Title": "Sales Intern",
                                "PrimaryLocation": "New York, NY, United States",
                                "PrimaryLocationCountry": "US",
                            },
                        ],
                    }]
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
        self.assertEqual(jobs[0]["oracle_job_id"], "10")
        self.assertEqual(len(session.calls), 1)
        params = session.calls[0][1]["params"]
        self.assertEqual(params["onlyData"], "true")
        self.assertEqual(params["expand"], "requisitionList")
        self.assertIn("siteNumber=CX_1", params["finder"])
        self.assertIn("keyword=intern", params["finder"])
        self.assertIn("workLocationCountryCode=US", params["finder"])


    def test_fetch_falls_back_across_oracle_rest_versions(self):
        source = {
            "key": "auto-oracle-example",
            "name": "Example (resolved Oracle)",
            "company": "Example",
            "site_number": "CX_1",
            "homepage": "https://careers.example.com/en/sites/CX_1",
            "api_url": "https://careers.example.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
            "api_urls": [
                "https://careers.example.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                "https://careers.example.com/hcmRestApi/resources/11.13.18.05/recruitingCEJobRequisitions",
            ],
        }

        class Response:
            def __init__(self, ok):
                self.ok = ok

            def raise_for_status(self):
                if not self.ok:
                    raise mod.requests.HTTPError("404")

            def json(self):
                return {
                    "items": [{
                        "TotalJobsCount": 1,
                        "requisitionList": [{
                            "Id": "10",
                            "Title": "Software Engineering Intern",
                            "PrimaryLocation": "Boston, MA, United States",
                            "PrimaryLocationCountry": "US",
                            "PostedDate": "2026-09-01",
                        }],
                    }]
                }

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return Response("/11.13.18.05/" in url)

        session = Session()
        jobs = mod.fetch_source(session, source, datetime(2026, 9, 17, tzinfo=timezone.utc))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["oracle_job_id"], "10")
        self.assertEqual(len(session.calls), 3)
        self.assertIn("/11.13.18.05/", session.calls[-1][0])



    def test_fetch_falls_back_from_non_json_ce_to_ice_resource(self):
        source = {
            "key": "auto-oracle-example",
            "name": "Example (resolved Oracle)",
            "company": "Example",
            "site_number": "CX_1",
            "homepage": "https://careers.example.com/en/sites/CX_1",
            "api_url": "https://careers.example.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
            "api_urls": [
                "https://careers.example.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                "https://careers.example.com/hcmRestApi/resources/latest/recruitingICEJobRequisitions",
            ],
        }

        class Response:
            def __init__(self, json_ok):
                self.json_ok = json_ok
                self.headers = {"Content-Type": "application/json" if json_ok else "text/html"}

            def raise_for_status(self):
                return None

            def json(self):
                if not self.json_ok:
                    raise AssertionError("non-JSON response should be rejected before parsing")
                return {
                    "items": [{
                        "TotalJobsCount": 1,
                        "requisitionList": [{
                            "Id": "10",
                            "Title": "Software Engineering Intern",
                            "PrimaryLocation": "Boston, MA, United States",
                            "PrimaryLocationCountry": "US",
                            "PostedDate": "2026-09-01",
                        }],
                    }]
                }

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(url)
                return Response("recruitingICEJobRequisitions" in url)

        session = Session()
        jobs = mod.fetch_source(session, source, datetime(2026, 9, 17, tzinfo=timezone.utc))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["oracle_job_id"], "10")
        self.assertEqual(session.calls[-1], source["api_urls"][1])



if __name__ == "__main__":
    unittest.main()
