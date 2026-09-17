import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "ashby_inspector.py"
spec = importlib.util.spec_from_file_location("ashby_inspector", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

POSTING_ID = "eb77c97c-fa9d-4bf0-9566-e5ba4453b7d3"
CANONICAL = f"https://jobs.ashbyhq.com/persona/{POSTING_ID}"


def fixed_now():
    return datetime(2026, 9, 16, 23, 55, tzinfo=timezone.utc)


def payload():
    return {
        "apiVersion": "1",
        "jobs": [
            {
                "title": "Software Engineer, Intern (Summer 2027)",
                "location": "San Francisco, CA",
                "secondaryLocations": [{"location": "New York, NY"}],
                "department": "Engineering",
                "team": "Platform",
                "isListed": True,
                "isRemote": False,
                "workplaceType": "OnSite",
                "descriptionHtml": (
                    "<h3>What we're looking for</h3>"
                    "<p>Experience with Python is required.</p>"
                    "<p>SQL experience is preferred.</p>"
                    "<p>Must be authorized to work in the United States without sponsorship.</p>"
                ),
                "descriptionPlain": "Experience with Python is required.",
                "publishedAt": "2026-09-15T14:00:00+00:00",
                "employmentType": "Intern",
                "jobUrl": CANONICAL,
                "applyUrl": f"{CANONICAL}/application",
            }
        ],
    }


class FakeResponse:
    def __init__(self, body=None, status_code=200):
        self.body = body
        self.status_code = status_code

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


class AshbyInspectorTests(unittest.TestCase):
    def test_canonicalizes_job_and_application_variants(self):
        variants = (
            CANONICAL,
            f"{CANONICAL}?utm_source=feed",
            f"{CANONICAL}/application?embed=true&utm_source=Simplify",
            f"{CANONICAL}/apply#application",
        )
        identities = [mod.derive_ashby_endpoint(url) for url in variants]
        self.assertEqual({item["canonical_job_url"] for item in identities}, {CANONICAL})
        self.assertEqual(
            {item["endpoint_url"] for item in identities},
            {"https://api.ashbyhq.com/posting-api/job-board/persona"},
        )

    def test_rejects_board_pages_non_ashby_and_non_uuid_jobs(self):
        for url in (
            "https://jobs.ashbyhq.com/persona",
            "https://jobs.ashbyhq.com/persona/not-a-uuid",
            f"http://jobs.ashbyhq.com/persona/{POSTING_ID}",
            f"https://example.com/persona/{POSTING_ID}",
        ):
            with self.subTest(url=url):
                with self.assertRaises(mod.UnsupportedAshbyUrl):
                    mod.derive_ashby_endpoint(url)

    def test_normalizes_description_locations_and_shared_requirements(self):
        normalized = mod.normalize_payload(payload()["jobs"][0], posting_id=POSTING_ID)
        posting = normalized["posting"]
        requirements = normalized["requirements"]
        self.assertEqual(posting["posting_id"], POSTING_ID)
        self.assertEqual(posting["locations"]["values"], ["San Francisco, CA", "New York, NY"])
        self.assertEqual(posting["employment_type"], "Intern")
        self.assertEqual(posting["application_status"], "available")
        self.assertEqual(requirements["skills"]["required"][0]["technologies"], ["Python"])
        self.assertEqual(requirements["skills"]["preferred"][0]["technologies"], ["SQL"])
        self.assertEqual(requirements["work_authorization"]["classification"], "required")

    def test_retrieval_finds_requested_posting_and_records_provenance(self):
        session = FakeSession(FakeResponse(payload()))
        result = mod.inspect_ashby_url(
            f"{CANONICAL}/application?embed=true",
            session=session,
            now=fixed_now,
        )
        self.assertEqual(result["status"], "inspected")
        self.assertEqual(result["provider"], "ashby")
        self.assertEqual(result["retrieval_confidence"], "high")
        self.assertEqual(result["posting"]["posting_id"], POSTING_ID)
        self.assertEqual(result["provenance"]["interface"], "ashby_public_job_postings_api")
        self.assertEqual(result["provenance"]["board_name"], "persona")
        self.assertEqual(result["provenance"]["canonical_job_url"], CANONICAL)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(
            session.calls[0]["url"],
            "https://api.ashbyhq.com/posting-api/job-board/persona",
        )

    def test_missing_published_posting_is_confirmed_unavailable(self):
        result = mod.inspect_ashby_url(
            CANONICAL,
            session=FakeSession(FakeResponse({"apiVersion": "1", "jobs": []})),
            now=fixed_now,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("no longer contains", result["error"])

    def test_transient_failure_is_structured(self):
        result = mod.inspect_ashby_url(
            CANONICAL,
            session=FakeSession(error=requests.Timeout("timed out")),
            now=fixed_now,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["retrieval_confidence"], "none")
        self.assertIn("Timeout", result["error"])

    def test_semantics_are_delegated_to_shared_extractor(self):
        sentinel = {"shared": True}
        with mock.patch.object(
            mod.posting_requirements,
            "extract_requirements",
            return_value=sentinel,
        ) as shared:
            normalized = mod.normalize_payload(payload()["jobs"][0], posting_id=POSTING_ID)
        self.assertIs(normalized["requirements"], sentinel)
        shared.assert_called_once()


if __name__ == "__main__":
    unittest.main()
