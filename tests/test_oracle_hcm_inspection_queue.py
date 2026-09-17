import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "update_workday_inspections.py"
spec = importlib.util.spec_from_file_location("update_workday_inspections_oracle", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)


def oracle_job(job_id, posting_id="297770", posted_at="2026-09-16T20:00:00Z"):
    return {
        "id": job_id,
        "company": "Example Oracle HCM Employer",
        "title": "Undergraduate Analytics Intern",
        "url": f"https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/{posting_id}?ref=Simplify",
        "posted_at": posted_at,
        "link_kind": "direct",
        "term": None,
        "opportunity_type": "internship",
        "education_level": "undergrad",
        "profiles": ["tech-business"],
    }


def inspection(url):
    return {
        "provider": "oracle_hcm",
        "status": "inspected",
        "retrieval_confidence": "high",
        "error": None,
        "posting": {"application_status": "available", "description": "Qualifications\nSQL required."},
        "requirements": {},
        "provenance": {"source_url": url, "inspected_at": "2026-09-17T00:00:00Z"},
    }


class OracleHcmInspectionQueueTests(unittest.TestCase):
    def test_oracle_tracking_variants_share_one_cache_identity(self):
        first = oracle_job("first", "297770")
        second = {**oracle_job("second", "297770"), "url": (
            "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/297770/"
            "?utm_medium=jobshare&utm_source=External+Job+Share"
        )}
        listing_index, by_url = mod.build_listing_index([first, second])
        canonical = "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/297770"
        self.assertEqual(listing_index, {"first": canonical, "second": canonical})
        self.assertEqual(list(by_url), [canonical])

    def test_oracle_has_independent_bounded_request_budget(self):
        jobs = [oracle_job("new", "297770"), oracle_job("older", "298216", "2026-09-11T00:00:00Z")]
        calls = []
        updated, stats = mod.refresh_cache(
            {"jobs": jobs},
            mod.empty_cache(),
            max_workday_requests=0,
            max_icims_requests=0,
            max_greenhouse_requests=0,
            max_ashby_requests=0,
            max_oracle_hcm_requests=1,
            now=lambda: NOW,
            inspector=lambda url: calls.append(url) or inspection(url),
        )
        self.assertEqual(len(calls), 1)
        self.assertIn("297770", calls[0])
        self.assertEqual(stats["provider_requests"]["oracle_hcm"], 1)
        self.assertEqual(stats["provider_caps"]["oracle_hcm"], 1)
        self.assertEqual(stats["oracle_hcm_listings"], 2)
        older = mod.oracle_hcm_identity(jobs[1])["canonical_url"]
        self.assertEqual(updated["queue"][older]["state"], "queued")
        self.assertEqual(updated["entries"][older]["inspection"]["provider"], "oracle_hcm")


if __name__ == "__main__":
    unittest.main()
