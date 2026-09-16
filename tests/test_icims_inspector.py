import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
FIXTURES = ROOT / "tests" / "fixtures" / "icims"
MODULE_PATH = SCRIPTS / "icims_inspector.py"
spec = importlib.util.spec_from_file_location("icims_inspector", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixed_now():
    return datetime(2026, 9, 16, 19, 30, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

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


class IcimsInspectorTests(unittest.TestCase):
    def test_canonicalizes_slug_login_mobile_and_tracking_variants(self):
        variants = (
            "https://careers-gdms.icims.com/jobs/74848/job",
            "https://careers-gdms.icims.com/jobs/74848/payload-control-system/job?mobile=true&needsRedirect=false&utm_source=Simplify&ref=Simplify",
            "https://careers-gdms.icims.com/jobs/74848/login?mobile=true&amp%3BneedsRedirect=false&amp%3Bref=Simplify",
        )
        identities = [mod.derive_icims_endpoint(url) for url in variants]
        self.assertEqual(
            {item["canonical_job_url"] for item in identities},
            {"https://careers-gdms.icims.com/jobs/74848/job"},
        )
        self.assertEqual(
            {item["endpoint_url"] for item in identities},
            {"https://careers-gdms.icims.com/jobs/74848/job?in_iframe=1"},
        )

    def test_rejects_non_icims_and_unrecognized_shapes(self):
        for url in (
            "https://example.com/jobs/123/job",
            "http://careers-example.icims.com/jobs/123/job",
            "https://careers-example.icims.com/jobs/search",
            "https://careers-example.icims.com/jobs/not-a-number/job",
        ):
            with self.subTest(url=url):
                with self.assertRaises(mod.UnsupportedIcimsUrl):
                    mod.derive_icims_endpoint(url)

    def test_jsonld_posting_preserves_required_and_preferred_evidence(self):
        normalized = mod.normalize_html(fixture("gdms_74848.html"), job_id="74848")
        posting = normalized["posting"]
        requirements = normalized["requirements"]

        self.assertEqual(posting["posting_id"], "74848")
        self.assertEqual(posting["requisition_id"], "2026-74848")
        self.assertEqual(posting["application_status"], "available")
        self.assertEqual(
            posting["locations"]["values"],
            ["Manassas, VA, 20110, US", "Middletown, RI, US"],
        )
        self.assertNotIn("<li>", posting["description"])
        self.assertEqual(requirements["education"]["classification"], "required")
        self.assertEqual(requirements["student_status"]["classification"], "required")
        self.assertEqual(requirements["major_fields"]["classification"], "required")
        self.assertEqual(requirements["citizenship"]["classification"], "required")
        self.assertEqual(requirements["skills"]["classification"], "mixed")
        self.assertEqual(requirements["skills"]["required"][0]["technologies"], ["C++", "Python"])
        self.assertEqual(requirements["skills"]["preferred"][0]["technologies"], ["Git", "Linux"])
        self.assertTrue(any("clearance" in fact["statement"].lower() for fact in requirements["other_eligibility"]["preferred"]))

    def test_second_tenant_preserves_explicit_citizenship_and_sponsorship_negation(self):
        normalized = mod.normalize_html(fixture("alliance_13162.html"), job_id="13162")
        requirements = normalized["requirements"]
        self.assertEqual(normalized["posting"]["locations"]["values"], ["Ripon, WI, 54971, US"])
        self.assertEqual(requirements["education"]["classification"], "preferred")
        self.assertEqual(requirements["skills"]["classification"], "unspecified")
        self.assertEqual(requirements["skills"]["unspecified"][0]["technologies"], ["SQL"])
        self.assertEqual(requirements["citizenship"]["classification"], "not_required")
        self.assertEqual(requirements["citizenship"]["required"], [])
        self.assertIs(requirements["citizenship"]["not_required"][0]["negated"], True)
        self.assertEqual(requirements["work_authorization"]["classification"], "not_required")
        self.assertEqual(requirements["work_authorization"]["required"], [])

    def test_closed_posting_is_detected_from_generic_icims_message(self):
        result = mod.inspect_icims_url(
            "https://careers-wipfli.icims.com/jobs/7972/job",
            session=FakeSession(FakeResponse(fixture("wipfli_closed.html"))),
            now=fixed_now,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["retrieval_confidence"], "none")
        self.assertIsNone(result["posting"])

    def test_success_records_provider_confidence_and_provenance(self):
        session = FakeSession(FakeResponse(fixture("gdms_74848.html")))
        result = mod.inspect_icims_url(
            "https://careers-gdms.icims.com/jobs/74848/job?utm_source=Simplify",
            session=session,
            now=fixed_now,
        )
        self.assertEqual(result["provider"], "icims")
        self.assertEqual(result["status"], "inspected")
        self.assertEqual(result["retrieval_confidence"], "high")
        self.assertEqual(result["provenance"]["provider"], "icims")
        self.assertEqual(result["provenance"]["interface"], "icims_jobposting_jsonld")
        self.assertEqual(result["provenance"]["canonical_job_url"], "https://careers-gdms.icims.com/jobs/74848/job")
        self.assertEqual(result["provenance"]["inspected_at"], "2026-09-16T19:30:00Z")
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["url"], "https://careers-gdms.icims.com/jobs/74848/job?in_iframe=1")

    def test_generic_icims_html_is_a_medium_confidence_fallback(self):
        page = """
        <div class="iCIMS_JobContent">
          <h1 id="iCIMS_Header">Fallback Software Intern</h1>
          <h2 class="iCIMS_InfoField_Job">Required Qualifications</h2>
          <div class="iCIMS_InfoMsg_Job"><div class="iCIMS_Expandable_Text">
            <p>Python experience is required.</p>
          </div></div>
          <a class="iCIMS_ApplyOnlineButton">Apply</a>
        </div>
        """
        result = mod.inspect_icims_url(
            "https://careers-example.icims.com/jobs/4567/job",
            session=FakeSession(FakeResponse(page)),
            now=fixed_now,
        )
        self.assertEqual(result["status"], "inspected")
        self.assertEqual(result["retrieval_confidence"], "medium")
        self.assertEqual(result["provenance"]["interface"], "icims_public_html")
        self.assertEqual(result["posting"]["title"], "Fallback Software Intern")
        self.assertEqual(
            result["requirements"]["skills"]["required"][0]["technologies"],
            ["Python"],
        )

    def test_failures_are_structured_and_listing_is_preserved(self):
        base = {
            "id": "listing-1",
            "company": "Example",
            "title": "Data Intern",
            "url": "https://careers-example.icims.com/jobs/1234/job",
        }
        inspected = mod.inspect_listing(
            base,
            session=FakeSession(error=requests.Timeout("timed out")),
            now=fixed_now,
        )
        self.assertEqual(base["company"], "Example")
        self.assertEqual(inspected["company"], "Example")
        self.assertEqual(inspected["inspection"]["status"], "failed")
        self.assertIn("Timeout", inspected["inspection"]["error"])


if __name__ == "__main__":
    unittest.main()
