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
spec = importlib.util.spec_from_file_location("update_workday_inspections", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = datetime(2026, 9, 16, 23, 55, tzinfo=timezone.utc)
POSTING_ID = "eb77c97c-fa9d-4bf0-9566-e5ba4453b7d3"
CANONICAL = f"https://jobs.ashbyhq.com/persona/{POSTING_ID}"


def job(job_id, url):
    return {
        "id": job_id,
        "company": "Persona",
        "title": "Software Engineer, Intern (Summer 2027)",
        "url": url,
        "posted_at": "2026-09-16T12:00:00Z",
        "link_kind": "direct",
        "term": "Summer 2027",
        "opportunity_type": "internship",
        "education_level": "undergrad",
        "profiles": ["cs"],
    }


def inspection(url):
    return {
        "provider": "ashby",
        "status": "inspected",
        "retrieval_confidence": "high",
        "error": None,
        "posting": {"application_status": "available", "description": "Python required."},
        "requirements": {},
        "provenance": {
            "provider": "ashby",
            "source_url": url,
            "inspected_at": "2026-09-16T23:55:00Z",
        },
    }


class AshbyInspectionQueueTests(unittest.TestCase):
    def test_job_and_application_variants_share_one_cache_identity(self):
        regular = job("regular", CANONICAL)
        application = job("application", f"{CANONICAL}/application?embed=true&utm_source=Simplify")
        listing_index, by_url = mod.build_listing_index([regular, application])
        self.assertEqual(
            listing_index,
            {"application": CANONICAL, "regular": CANONICAL},
        )
        self.assertEqual(list(by_url), [CANONICAL])
        self.assertEqual(len(by_url[CANONICAL]), 2)

    def test_ashby_has_independent_bounded_request_budget(self):
        jobs = [
            job("first", CANONICAL),
            job(
                "second",
                "https://jobs.ashbyhq.com/persona/11111111-1111-4111-8111-111111111111",
            ),
        ]
        calls = []
        updated, stats = mod.refresh_cache(
            {"jobs": jobs},
            mod.empty_cache(),
            max_workday_requests=0,
            max_icims_requests=0,
            max_greenhouse_requests=0,
            max_ashby_requests=1,
            now=lambda: NOW,
            inspector=lambda url: calls.append(url) or inspection(url),
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(stats["provider_requests"]["ashby"], 1)
        self.assertEqual(stats["provider_caps"]["ashby"], 1)
        self.assertEqual(stats["ashby_listings"], 2)
        self.assertEqual(stats["ashby_postings"], 2)
        remaining = next(
            canonical for canonical, info in updated["queue"].items()
            if info["state"] == "queued"
        )
        self.assertEqual(updated["entries"][remaining]["inspection"]["provider"], "ashby")
        self.assertEqual(updated["entries"][remaining]["inspection"]["queue"]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
