import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "jobright_links.py"
spec = importlib.util.spec_from_file_location("jobright_links", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakeResponse:
    def __init__(self, *, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        return self._payload


class JobrightLinksTests(unittest.TestCase):
    def test_current_detail_fixture_exposes_canonical_metadata_not_url(self):
        data = json.loads((FIXTURES / "jobright_detail_current.json").read_text(encoding="utf-8"))
        html = (
            '<script id="jobright-helper-job-detail-info" type="application/json">'
            + json.dumps(data)
            + "</script>"
        )
        parsed = mod.detail_data_from_html(html)
        self.assertEqual(mod.detail_row(parsed)["jobResult"]["jobId"], "6a8de421cc0cf27068525e33")
        self.assertEqual(mod.search_titles({"title": "Planning Intern / New York, NY"}, parsed), [
            "Planning Intern / New York, NY", "Planning Intern", "Planning Intern | New York, NY",
        ])
        self.assertIsNone(mod.direct_from_exact_id([mod.detail_row(parsed)], "6a8de421cc0cf27068525e33"))

    def test_detail_metadata_recovers_unique_workday_candidate(self):
        data = json.loads((FIXTURES / "jobright_detail_current.json").read_text(encoding="utf-8"))
        html = '<script id="jobright-helper-job-detail-info">' + json.dumps(data) + "</script>"
        workday = "https://imeg.wd1.myworkdayjobs.com/en-US/Imeg_Careers/job/Planning-Intern---New-York--NY_R-16669"
        search_payload = {"result": {"jobList": [{
            "jobResult": {
                "jobId": "visitor-id-different-from-detail",
                "jobTitle": "Planning Intern | New York, NY",
                "jobLocation": "New York, NY",
                "originalUrl": workday,
            },
            "companyResult": {"companyName": "IMEG"},
        }]}}
        job = {
            "listing_url": "https://jobright.ai/jobs/info/6a8de421cc0cf27068525e33",
            "company": "IMEG",
            "title": "Planning Intern / New York, NY",
            "location": "New York, NY, United States",
        }
        with (
            patch.object(mod.requests, "get", return_value=FakeResponse(text=html)),
            patch.object(mod.requests, "post", return_value=FakeResponse(payload=search_payload)),
            patch.object(mod.links, "validate_candidate_once", return_value=workday),
        ):
            self.assertEqual(mod.fetch_direct(job), (workday, "jobright-metadata"))

    def test_detail_exact_id_prefers_workday_url_without_search(self):
        data = json.loads((FIXTURES / "jobright_detail_current.json").read_text(encoding="utf-8"))
        workday = "https://imeg.wd1.myworkdayjobs.com/en-US/Imeg_Careers/job/Planning-Intern---New-York--NY_R-16669"
        data["jobResult"]["originalUrl"] = workday
        html = '<script id="jobright-helper-job-detail-info">' + json.dumps(data) + "</script>"
        job = {"listing_url": "https://jobright.ai/jobs/info/6a8de421cc0cf27068525e33"}
        with (
            patch.object(mod.requests, "get", return_value=FakeResponse(text=html)),
            patch.object(mod.requests, "post") as post,
            patch.object(mod.links, "validate_candidate_once", return_value=workday),
        ):
            self.assertEqual(mod.fetch_direct(job), (workday, "jobright-detail-id"))
        post.assert_not_called()

    def test_metadata_rejects_distinct_direct_urls(self):
        rows = [
            {
                "jobResult": {
                    "jobTitle": "Planning Intern | New York, NY",
                    "jobLocation": "New York, NY",
                    "originalUrl": "https://one.example/jobs/1",
                },
                "companyResult": {"companyName": "IMEG"},
            },
            {
                "jobResult": {
                    "jobTitle": "Planning Intern | New York, NY",
                    "jobLocation": "New York, NY",
                    "originalUrl": "https://two.example/jobs/2",
                },
                "companyResult": {"companyName": "IMEG"},
            },
        ]
        self.assertIsNone(
            mod.direct_from_exact_metadata(rows, "IMEG", "Planning Intern | New York, NY", "New York, NY")
        )

    def test_jobright_id(self):
        self.assertEqual(
            mod.jobright_id("https://jobright.ai/jobs/info/6aa9c1db09ae03adcacdef24?utm_source=git"),
            "6aa9c1db09ae03adcacdef24",
        )
        self.assertEqual(mod.jobright_id("https://example.com/jobs/info/x"), "")

    def test_clean_title_strips_markdown_bold(self):
        self.assertEqual(mod.clean_title("**Policy Research Intern**"), "Policy Research Intern")

    def test_exact_id_prefers_original_url(self):
        rows = [{
            "jobResult": {
                "jobId": "abc123",
                "originalUrl": "https://example.com/careers/jobs/123",
                "applyLink": "https://other.example.com/jobs/123",
            }
        }]
        self.assertEqual(
            mod.direct_from_exact_id(rows, "abc123"),
            "https://example.com/careers/jobs/123",
        )

    def test_wrong_id_is_rejected(self):
        rows = [{
            "jobResult": {
                "jobId": "other",
                "originalUrl": "https://example.com/careers/jobs/123",
            }
        }]
        self.assertIsNone(mod.direct_from_exact_id(rows, "abc123"))

    def test_duplicate_exact_id_is_rejected(self):
        rows = [
            {"jobResult": {"jobId": "abc123", "originalUrl": "https://one.example.com/jobs/1"}},
            {"jobResult": {"jobId": "abc123", "originalUrl": "https://two.example.com/jobs/2"}},
        ]
        self.assertIsNone(mod.direct_from_exact_id(rows, "abc123"))

    def test_aggregator_url_is_not_promoted(self):
        rows = [{
            "jobResult": {
                "jobId": "abc123",
                "originalUrl": "https://jobright.ai/jobs/info/abc123",
            }
        }]
        self.assertIsNone(mod.direct_from_exact_id(rows, "abc123"))


if __name__ == "__main__":
    unittest.main()
