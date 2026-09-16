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
spec = importlib.util.spec_from_file_location("update_workday_inspections_priority", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = datetime(2026, 9, 16, 17, 30, tzinfo=timezone.utc)


def job(job_id, req, *, title, term, education_level, posted_at, profiles):
    return {
        "id": job_id,
        "company": "Example",
        "title": title,
        "url": f"https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Role_{req}",
        "posted_at": posted_at,
        "link_kind": "direct",
        "term": term,
        "opportunity_type": "internship",
        "education_level": education_level,
        "profiles": profiles,
    }


def inspected(url):
    return {
        "status": "inspected",
        "retrieval_confidence": "high",
        "error": None,
        "posting": {"application_status": "available"},
        "requirements": {},
        "provenance": {"source_url": url, "inspected_at": "2026-09-16T17:30:00Z"},
    }


class InspectionPriorityTests(unittest.TestCase):
    def test_fresh_classified_unknown_term_can_outrank_older_generic_known_term(self):
        decision_relevant = job(
            "data-analyst",
            "REQ-DATA",
            title="Data Analyst Intern",
            term="",
            education_level="unspecified",
            posted_at="2026-09-16T12:00:00Z",
            profiles=["tech-business"],
        )
        generic_known_term = job(
            "generic",
            "REQ-GENERIC",
            title="Summer Intern",
            term="Summer 2027",
            education_level="undergrad",
            posted_at="2026-09-10T12:00:00Z",
            profiles=[],
        )
        calls = []
        updated, stats = mod.refresh_cache(
            {"jobs": [generic_known_term, decision_relevant]},
            mod.empty_cache(),
            max_workday_requests=1,
            max_icims_requests=0,
            max_greenhouse_requests=0,
            now=lambda: NOW,
            inspector=lambda url: calls.append(url) or inspected(url),
        )
        self.assertEqual(stats["requested"], 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("REQ-DATA", calls[0])
        generic_url = mod.workday_identity(generic_known_term)["canonical_url"]
        self.assertEqual(updated["queue"][generic_url]["state"], "queued")

    def test_priority_reasons_explain_information_gain_and_career_area(self):
        candidate = job(
            "software",
            "REQ-SWE",
            title="Software Engineer Intern",
            term="",
            education_level="unspecified",
            posted_at="2026-09-16T12:00:00Z",
            profiles=["cs"],
        )
        score, reasons = mod.public_priority(candidate, NOW)
        self.assertGreater(score, 0)
        self.assertIn("term unknown; inspection can resolve it", reasons)
        self.assertIn("education not restrictive; inspection can clarify", reasons)
        self.assertIn("classified career area: cs", reasons)
        self.assertIn("posted within 2 days", reasons)

    def test_wrong_term_and_graduate_only_still_sink(self):
        candidate = job(
            "wrong",
            "REQ-WRONG",
            title="Data Analyst Intern",
            term="Summer 2026",
            education_level="graduate-only",
            posted_at="2026-09-16T12:00:00Z",
            profiles=["tech-business"],
        )
        score, reasons = mod.public_priority(candidate, NOW)
        self.assertLess(score, 0)
        self.assertIn("other term: Summer 2026", reasons)
        self.assertIn("graduate-only", reasons)


if __name__ == "__main__":
    unittest.main()
