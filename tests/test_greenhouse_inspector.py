import importlib.util
import json
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
FIXTURES = ROOT / "tests" / "fixtures" / "greenhouse"
MODULE_PATH = SCRIPTS / "greenhouse_inspector.py"
spec = importlib.util.spec_from_file_location("greenhouse_inspector", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixed_now():
    return datetime(2026, 9, 16, 21, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

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


class GreenhouseInspectorTests(unittest.TestCase):
    def test_canonicalizes_current_legacy_and_tracking_variants(self):
        variants = (
            "https://job-boards.greenhouse.io/DoorDashUSA/jobs/8171041",
            "https://boards.greenhouse.io/doordashusa/jobs/8171041?gh_src=abc&utm_source=feed",
            "https://job-boards.greenhouse.io/doordashusa/jobs/8171041?gh_jid=8171041&amp%3Bref=Simplify#apply",
            "https://job-boards.greenhouse.io/embed/job_app?for=doordashusa&amp;token=8171041&amp;t=source",
        )
        identities = [mod.derive_greenhouse_endpoint(url) for url in variants]
        self.assertEqual(
            {item["canonical_job_url"] for item in identities},
            {"https://job-boards.greenhouse.io/doordashusa/jobs/8171041"},
        )
        self.assertEqual(
            {item["endpoint_url"] for item in identities},
            {"https://boards-api.greenhouse.io/v1/boards/doordashusa/jobs/8171041"},
        )

    def test_does_not_merge_different_job_ids(self):
        first = mod.derive_greenhouse_endpoint(
            "https://job-boards.greenhouse.io/doordashusa/jobs/8171041"
        )
        second = mod.derive_greenhouse_endpoint(
            "https://boards.greenhouse.io/doordashusa/jobs/8171042"
        )
        self.assertNotEqual(first["canonical_job_url"], second["canonical_job_url"])

    def test_rejects_non_greenhouse_and_unrecognized_shapes(self):
        for url in (
            "https://example.com/doordashusa/jobs/8171041",
            "http://boards.greenhouse.io/doordashusa/jobs/8171041",
            "https://job-boards.greenhouse.io/doordashusa",
            "https://job-boards.greenhouse.io/doordashusa/jobs/not-numeric",
        ):
            with self.subTest(url=url):
                with self.assertRaises(mod.UnsupportedGreenhouseUrl):
                    mod.derive_greenhouse_endpoint(url)

    def test_normalizes_doordash_required_preferred_and_work_authorization(self):
        normalized = mod.normalize_payload(
            fixture("doordash_8171041.json"),
            board_token="doordashusa",
            expected_job_id="8171041",
        )
        posting = normalized["posting"]
        requirements = normalized["requirements"]
        self.assertEqual(posting["posting_id"], "8171041")
        self.assertEqual(posting["requisition_id"], "P-112001")
        self.assertEqual(posting["application_status"], "available")
        self.assertEqual(
            posting["locations"]["values"],
            ["New York, NY", "San Francisco, CA", "Sunnyvale, CA"],
        )
        self.assertNotIn("&lt;", posting["description"])
        self.assertEqual(requirements["skills"]["classification"], "mixed")
        self.assertEqual(
            requirements["skills"]["required"][0]["technologies"],
            ["Python", "Java", "SQL", "AWS"],
        )
        self.assertEqual(
            requirements["skills"]["preferred"][0]["technologies"],
            ["Git", "Linux"],
        )
        self.assertEqual(requirements["work_authorization"]["classification"], "required")
        self.assertEqual(requirements["citizenship"]["classification"], "unknown")
        self.assertTrue(
            any(
                "does not sponsor" in fact["statement"].lower()
                for fact in requirements["work_authorization"]["required"]
            )
        )

    def test_normalizes_second_employer_citizenship_and_preferred_skills(self):
        normalized = mod.normalize_payload(
            fixture("anduril_5239083007.json"),
            board_token="andurilindustries",
            expected_job_id="5239083007",
        )
        requirements = normalized["requirements"]
        self.assertEqual(requirements["citizenship"]["classification"], "required")
        self.assertIn("U.S. Person", requirements["citizenship"]["required"][0]["statement"])
        self.assertEqual(
            requirements["skills"]["preferred"][0]["technologies"],
            ["Python", "MATLAB"],
        )

    def test_successful_retrieval_records_api_provenance(self):
        session = FakeSession(FakeResponse(fixture("doordash_8171041.json")))
        result = mod.inspect_greenhouse_url(
            "https://boards.greenhouse.io/doordashusa/jobs/8171041?gh_src=abc",
            session=session,
            now=fixed_now,
        )
        self.assertEqual(result["status"], "inspected")
        self.assertEqual(result["provider"], "greenhouse")
        self.assertEqual(result["retrieval_confidence"], "high")
        self.assertEqual(result["provenance"]["interface"], "greenhouse_job_board_api")
        self.assertEqual(result["provenance"]["board_token"], "doordashusa")
        self.assertEqual(result["provenance"]["job_id"], "8171041")
        self.assertEqual(result["provenance"]["inspected_at"], "2026-09-16T21:00:00Z")
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["headers"]["Accept"], "application/json")

    def test_not_found_is_confirmed_unavailable(self):
        result = mod.inspect_greenhouse_url(
            "https://job-boards.greenhouse.io/doordashusa/jobs/8171041",
            session=FakeSession(FakeResponse({"status": 404}, status_code=404)),
            now=fixed_now,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["retrieval_confidence"], "none")
        self.assertIsNone(result["posting"])
        self.assertIn("HTTP 404", result["error"])

    def test_transient_failure_is_structured(self):
        result = mod.inspect_greenhouse_url(
            "https://job-boards.greenhouse.io/doordashusa/jobs/8171041",
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
            normalized = mod.normalize_payload(
                fixture("doordash_8171041.json"),
                board_token="doordashusa",
                expected_job_id="8171041",
            )
        self.assertIs(normalized["requirements"], sentinel)
        shared.assert_called_once()


if __name__ == "__main__":
    unittest.main()
