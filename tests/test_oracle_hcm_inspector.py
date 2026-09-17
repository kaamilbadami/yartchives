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
MODULE_PATH = SCRIPTS / "oracle_hcm_inspector.py"
spec = importlib.util.spec_from_file_location("oracle_hcm_inspector", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixed_now():
    return datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)


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

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


def payload(job_id="297770"):
    return {
        "items": [
            {
                "Id": job_id,
                "RequisitionId": 300000123456789,
                "Title": "Undergraduate Analytics Intern",
                "ExternalResponsibilitiesStr": "<p>Build dashboards and analyze data.</p>",
                "ExternalQualificationsStr": (
                    "<p>Essential Requirements</p><ul><li>Experience with SQL is required.</li>"
                    "<li>Python experience preferred.</li></ul>"
                ),
                "PrimaryLocation": "Round Rock, TX, United States",
                "secondaryLocations": [{"Name": "Hopkinton, MA, United States"}],
                "ExternalPostedStartDate": "2026-09-15T00:00:00+00:00",
                "ExternalPostedEndDate": "2026-10-01T00:00:00+00:00",
            }
        ]
    }


class OracleHcmInspectorTests(unittest.TestCase):
    def test_canonicalizes_tracking_and_requisition_number_variants(self):
        endpoint = mod.derive_oracle_hcm_endpoint(
            "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/R270849/?utm_source=feed&amp%3Bref=Simplify"
        )
        self.assertEqual(
            endpoint["canonical_job_url"],
            "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/R270849",
        )
        self.assertEqual(endpoint["site_number"], "careers")
        self.assertEqual(endpoint["job_id"], "R270849")
        self.assertEqual(
            endpoint["endpoint_url"],
            "https://iawmqy.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails",
        )

    def test_rejects_non_oracle_and_non_job_shapes(self):
        for url in (
            "https://example.com/hcmUI/CandidateExperience/en/sites/careers/job/297770",
            "http://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/297770",
            "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/jobs",
        ):
            with self.subTest(url=url):
                with self.assertRaises(mod.UnsupportedOracleHcmUrl):
                    mod.derive_oracle_hcm_endpoint(url)

    def test_normalizes_public_fields_and_shared_requirements(self):
        normalized = mod.normalize_payload(payload(), expected_job_id="297770")
        posting = normalized["posting"]
        requirements = normalized["requirements"]
        self.assertEqual(posting["title"], "Undergraduate Analytics Intern")
        self.assertEqual(posting["posting_id"], "297770")
        self.assertEqual(posting["locations"]["values"], [
            "Round Rock, TX, United States",
            "Hopkinton, MA, United States",
        ])
        self.assertEqual(requirements["skills"]["required"][0]["technologies"], ["SQL"])
        self.assertEqual(requirements["skills"]["preferred"][0]["technologies"], ["Python"])

    def test_successful_retrieval_uses_candidate_experience_finder(self):
        session = FakeSession(FakeResponse(payload()))
        result = mod.inspect_oracle_hcm_url(
            "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/297770?ref=Simplify",
            session=session,
            now=fixed_now,
        )
        self.assertEqual(result["status"], "inspected")
        self.assertEqual(result["provider"], "oracle_hcm")
        self.assertEqual(result["retrieval_confidence"], "high")
        self.assertEqual(result["provenance"]["interface"], "oracle_hcm_candidate_experience_api")
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(
            session.calls[0]["params"]["finder"],
            'ById;Id="297770",siteNumber=careers',
        )
        self.assertEqual(session.calls[0]["headers"]["Ora-Irc-Language"], "en")

    def test_empty_collection_is_confirmed_unavailable(self):
        result = mod.inspect_oracle_hcm_url(
            "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/297770",
            session=FakeSession(FakeResponse({"items": []})),
            now=fixed_now,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("not currently published", result["error"])

    def test_transient_failure_is_structured(self):
        result = mod.inspect_oracle_hcm_url(
            "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/297770",
            session=FakeSession(error=requests.Timeout("timed out")),
            now=fixed_now,
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("Timeout", result["error"])

    def test_semantics_are_delegated_to_shared_extractor(self):
        sentinel = {"shared": True}
        with mock.patch.object(mod.posting_requirements, "extract_requirements", return_value=sentinel) as shared:
            normalized = mod.normalize_payload(payload(), expected_job_id="297770")
        self.assertIs(normalized["requirements"], sentinel)
        shared.assert_called_once()


if __name__ == "__main__":
    unittest.main()
