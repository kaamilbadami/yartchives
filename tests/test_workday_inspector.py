import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

import requests

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "workday_inspector.py"
FIXTURES = ROOT / "tests" / "fixtures" / "workday"
spec = importlib.util.spec_from_file_location("workday_inspector", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixed_now():
    return datetime(2026, 9, 16, 16, 30, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, payload=None, status_code=200, json_error=None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


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


class WorkdayInspectorTests(unittest.TestCase):
    def test_derives_cxs_endpoint_from_localized_and_plain_urls(self):
        localized = mod.derive_cxs_endpoint(
            "https://alpha.wd5.myworkdayjobs.com/en-US/External_Careers/"
            "job/New-York/Software-Intern_R-123?source=feed"
        )
        self.assertEqual(localized["tenant"], "alpha")
        self.assertEqual(localized["site"], "External_Careers")
        self.assertEqual(
            localized["endpoint_url"],
            "https://alpha.wd5.myworkdayjobs.com/wday/cxs/alpha/External_Careers/"
            "job/New-York/Software-Intern_R-123",
        )

        plain = mod.derive_cxs_endpoint(
            "https://beta.wd103.myworkdayjobs.com/Jobs/job/Remote/Analyst_REQ-9"
        )
        self.assertEqual(plain["tenant"], "beta")
        self.assertEqual(plain["site"], "Jobs")

    def test_rejects_non_workday_and_non_job_urls(self):
        for url in (
            "https://example.com/External/job/A/B",
            "http://alpha.wd5.myworkdayjobs.com/External/job/A/B",
            "https://alpha.wd5.myworkdayjobs.com/External",
        ):
            with self.subTest(url=url):
                with self.assertRaises(mod.UnsupportedWorkdayUrl):
                    mod.derive_cxs_endpoint(url)

    def test_software_fixture_preserves_required_preferred_and_unknown(self):
        normalized = mod.normalize_payload(fixture("software_intern.json"))
        posting = normalized["posting"]
        requirements = normalized["requirements"]

        self.assertEqual(posting["requisition_id"], "REQ-10001")
        self.assertEqual(posting["locations"]["status"], "authoritative")
        self.assertEqual(
            posting["locations"]["values"],
            ["US-CT-WINDSOR LOCKS", "Windsor Locks, Connecticut"],
        )
        self.assertNotIn("<p>", posting["description"])

        self.assertEqual(requirements["education"]["classification"], "required")
        self.assertIn("Bachelor’s", requirements["education"]["required"][0]["statement"])
        self.assertEqual(requirements["student_status"]["classification"], "required")
        self.assertEqual(requirements["major_fields"]["classification"], "required")
        self.assertEqual(requirements["citizenship"]["classification"], "mixed")
        self.assertIn(
            "requires a U.S. Person",
            requirements["citizenship"]["required"][0]["statement"],
        )
        self.assertEqual(requirements["work_authorization"]["classification"], "unknown")
        self.assertEqual(requirements["graduation"]["classification"], "unknown")

        self.assertEqual(requirements["skills"]["classification"], "mixed")
        self.assertEqual(
            requirements["skills"]["required"][0]["technologies"], ["C", "Python"]
        )
        self.assertEqual(requirements["skills"]["preferred"][0]["technologies"], ["Git"])
        self.assertTrue(
            any("90 credit hours" in fact["statement"]
                for fact in requirements["other_eligibility"]["required"])
        )

    def test_claims_fixture_separates_required_authorization_and_preferences(self):
        normalized = mod.normalize_payload(fixture("claims_intern.json"))
        posting = normalized["posting"]
        requirements = normalized["requirements"]

        self.assertEqual(posting["requisition_id"], "R-20002")
        self.assertIn("Boston, Massachusetts", posting["locations"]["values"])
        self.assertEqual(requirements["work_authorization"]["classification"], "required")
        auth = [fact["statement"] for fact in requirements["work_authorization"]["required"]]
        self.assertTrue(any("authorized to work" in statement for statement in auth))
        self.assertTrue(any("does not sponsor" in statement for statement in auth))
        self.assertEqual(requirements["citizenship"]["classification"], "unknown")

        self.assertEqual(requirements["education"]["classification"], "required")
        self.assertEqual(requirements["graduation"]["classification"], "preferred")
        self.assertEqual(requirements["major_fields"]["classification"], "preferred")
        self.assertEqual(requirements["skills"]["classification"], "preferred")
        self.assertEqual(
            requirements["skills"]["preferred"][0]["technologies"], ["Microsoft Office"]
        )
        self.assertTrue(
            any("GPA" in fact["statement"]
                for fact in requirements["other_eligibility"]["preferred"])
        )

    def test_success_records_status_confidence_and_provenance(self):
        session = FakeSession(FakeResponse(fixture("software_intern.json")))
        url = (
            "https://aerospace.wd5.myworkdayjobs.com/en-US/External_Careers/"
            "job/Connecticut/Software-Engineering-Intern_REQ-10001"
        )
        result = mod.inspect_workday_url(url, session=session, now=fixed_now)

        self.assertEqual(result["status"], "inspected")
        self.assertEqual(result["confidence"], "high")
        self.assertIsNone(result["error"])
        self.assertEqual(result["provenance"]["interface"], "workday_cxs_json")
        self.assertEqual(result["provenance"]["tenant"], "aerospace")
        self.assertEqual(result["provenance"]["site"], "External_Careers")
        self.assertEqual(result["provenance"]["inspected_at"], "2026-09-16T16:30:00Z")
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["timeout"], mod.TIMEOUT)

    def test_unavailable_or_changed_response_does_not_destroy_base_listing(self):
        base = {
            "id": "listing-1",
            "company": "Example Company",
            "title": "Software Intern",
            "location": "Connecticut",
            "url": (
                "https://exampleco.wd5.myworkdayjobs.com/Careers/"
                "job/Connecticut/Software-Intern_REQ-1"
            ),
            "profiles": ["cs"],
        }
        original = json.loads(json.dumps(base))
        unavailable = mod.inspect_listing(
            base,
            session=FakeSession(FakeResponse(status_code=404)),
            now=fixed_now,
        )
        self.assertEqual(base, original)
        self.assertEqual(
            {key: value for key, value in unavailable.items() if key != "inspection"}, original
        )
        self.assertEqual(unavailable["inspection"]["status"], "unavailable")
        self.assertIsNone(unavailable["inspection"]["posting"])

        changed = mod.inspect_listing(
            base,
            session=FakeSession(FakeResponse({"unexpected": "shape"})),
            now=fixed_now,
        )
        self.assertEqual(changed["inspection"]["status"], "changed_response")
        self.assertEqual(changed["company"], "Example Company")

    def test_network_and_unsupported_url_failures_are_structured(self):
        network = mod.inspect_workday_url(
            "https://exampleco.wd5.myworkdayjobs.com/Careers/job/CT/Intern_R1",
            session=FakeSession(error=requests.Timeout("timed out")),
            now=fixed_now,
        )
        self.assertEqual(network["status"], "failed")
        self.assertEqual(network["confidence"], "none")
        self.assertIn("Timeout", network["error"])

        unsupported = mod.inspect_workday_url(
            "https://jobs.example.com/job/1", session=FakeSession(), now=fixed_now
        )
        self.assertEqual(unsupported["status"], "unsupported_url")
        self.assertEqual(unsupported["confidence"], "none")
        self.assertEqual(unsupported["provenance"]["interface"], "workday_cxs_json")


if __name__ == "__main__":
    unittest.main()
