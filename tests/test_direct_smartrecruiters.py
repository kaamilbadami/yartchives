import unittest
import warnings
from bs4 import MarkupResemblesLocatorWarning
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "direct_smartrecruiters.py"
spec = importlib.util.spec_from_file_location("direct_smartrecruiters", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DirectSmartRecruitersTests(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)

    def test_derive_smartrecruiters_endpoint_valid_url(self):
        url = "https://jobs.smartrecruiters.com/ServiceNow/744000150270254-senior-staff-product-manager-conversational-ai"
        endpoint = mod.derive_smartrecruiters_endpoint(url)
        self.assertEqual(endpoint["company_identifier"], "ServiceNow")
        self.assertEqual(endpoint["job_id"], "744000150270254")
        self.assertEqual(endpoint["canonical_job_url"], "https://jobs.smartrecruiters.com/ServiceNow/744000150270254")

    def test_derive_smartrecruiters_endpoint_valid_url_no_slug(self):
        url = "https://jobs.smartrecruiters.com/ServiceNow/744000150270254"
        endpoint = mod.derive_smartrecruiters_endpoint(url)
        self.assertEqual(endpoint["company_identifier"], "ServiceNow")
        self.assertEqual(endpoint["job_id"], "744000150270254")
        self.assertEqual(endpoint["canonical_job_url"], "https://jobs.smartrecruiters.com/ServiceNow/744000150270254")

    def test_derive_smartrecruiters_endpoint_invalid_host(self):
        url = "https://jobs.greenhouse.io/ServiceNow/744000150270254"
        with self.assertRaisesRegex(ValueError, "Not a SmartRecruiters job board URL"):
            mod.derive_smartrecruiters_endpoint(url)

    def test_derive_smartrecruiters_endpoint_invalid_path(self):
        url = "https://jobs.smartrecruiters.com/ServiceNow"
        with self.assertRaisesRegex(ValueError, "URL path does not contain enough parts"):
            mod.derive_smartrecruiters_endpoint(url)

    def test_source_from_job(self):
        job = {
            "company": "ServiceNow",
            "url": "https://jobs.smartrecruiters.com/ServiceNow/744000150270254",
            "profiles": ["cs"],
            "link_kind": "direct"
        }
        source = mod.source_from_job(job)
        self.assertIsNotNone(source)
        self.assertEqual(source["company_identifier"], "ServiceNow")
        self.assertEqual(source["api_url"], "https://api.smartrecruiters.com/v1/companies/ServiceNow/postings")

    def test_source_from_job_not_cs(self):
        job = {
            "company": "ServiceNow",
            "url": "https://jobs.smartrecruiters.com/ServiceNow/744000150270254",
            "profiles": ["finance"],
            "link_kind": "direct"
        }
        source = mod.source_from_job(job)
        self.assertIsNone(source)

    def test_job_from_item(self):
        source = {
            "key": "auto-smartrecruiters-servicenow",
            "name": "ServiceNow",
            "company": "ServiceNow",
            "company_identifier": "ServiceNow",
            "homepage": "https://jobs.smartrecruiters.com/ServiceNow",
        }
        item = {
            "id": "744000150270254",
            "name": "Software Engineer Intern",
            "location": {
                "city": "Santa Clara",
                "region": "CA",
                "country": "US",
                "remote": False
            },
            "releasedDate": "2026-09-18T02:52:15.071Z",
            "ref": "https://api.smartrecruiters.com/v1/companies/ServiceNow/postings/744000150270254"
        }
        reference = datetime(2026, 9, 20, tzinfo=timezone.utc)

        job = mod.job_from_item(source, item, reference)
        self.assertIsNotNone(job)
        self.assertEqual(job["title"], "Software Engineer Intern")
        self.assertEqual(job["company"], "ServiceNow")
        self.assertEqual(job["location"], "Santa Clara, CA, US")
        self.assertEqual(job["url"], "https://jobs.smartrecruiters.com/ServiceNow/744000150270254")
        self.assertTrue(job["direct_employer"])
        self.assertEqual(job["smartrecruiters_job_id"], "744000150270254")

    def test_job_from_item_remote_handling(self):
        source = {
            "key": "auto-smartrecruiters-servicenow",
            "name": "ServiceNow",
            "company": "ServiceNow",
            "company_identifier": "ServiceNow",
            "homepage": "https://jobs.smartrecruiters.com/ServiceNow",
        }
        item = {
            "id": "123",
            "name": "Software Engineer Intern",
            "location": {
                "city": "San Diego",
                "region": "CA",
                "country": "US",
                "remote": True
            },
        }
        reference = datetime(2026, 9, 20, tzinfo=timezone.utc)

        job = mod.job_from_item(source, item, reference)
        self.assertIsNotNone(job)
        self.assertEqual(job["location"], "San Diego, CA, US (Remote)")


if __name__ == "__main__":
    unittest.main()
