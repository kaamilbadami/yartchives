from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import update_workday_inspections as updater


NOW = datetime(2026, 9, 16, 22, 30, tzinfo=timezone.utc)


class CachedRequirementRenormalizationTests(unittest.TestCase):
    def test_cached_workday_description_is_renormalized_without_a_request(self):
        job = {
            "id": "avis-like",
            "company": "Example",
            "title": "IT Data Analytics Intern",
            "url": "https://tenant.wd5.myworkdayjobs.com/Careers/job/NJ/IT-Data-Analytics-Intern_REQ-1",
            "posted_at": "2026-09-16T12:00:00Z",
            "link_kind": "direct",
            "term": None,
            "opportunity_type": "internship",
            "education_level": "unspecified",
        }
        canonical = updater.workday_identity(job)["canonical_url"]
        cache = updater.empty_cache()
        cache["entries"][canonical] = {
            "provider": "workday",
            "inspection": {
                "provider": "workday",
                "status": "inspected",
                "retrieval_confidence": "high",
                "error": None,
                "posting": {
                    "application_status": "available",
                    "description": (
                        "What we're looking for:\n"
                        "Foundational knowledge of Python, SQL/PLSQL, Tableau, and Oracle "
                        "(coursework or project experience acceptable).\n"
                        "Strong communication skills and the ability to collaborate across teams."
                    ),
                },
                "requirements": {},
                "provenance": {"source_url": canonical, "inspected_at": "2026-09-16T20:00:00Z"},
            },
            "last_attempted_at": "2026-09-16T20:00:00Z",
            "last_success_at": "2026-09-16T20:00:00Z",
            "last_error": None,
        }
        calls = []
        updated, stats = updater.refresh_cache(
            {"jobs": [job]},
            cache,
            max_workday_requests=25,
            max_icims_requests=0,
            max_greenhouse_requests=0,
            now=lambda: NOW,
            inspector=lambda url: calls.append(url),
        )

        self.assertEqual(calls, [])
        self.assertEqual(stats["requested"], 0)
        skills = updated["entries"][canonical]["inspection"]["requirements"]["skills"]
        self.assertEqual(skills["classification"], "required")
        self.assertEqual(
            skills["required"][0]["technologies"],
            ["Python", "SQL", "Tableau", "Oracle"],
        )


if __name__ == "__main__":
    unittest.main()
