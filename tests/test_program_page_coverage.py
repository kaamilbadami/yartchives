import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_feed.py"
SPEC = importlib.util.spec_from_file_location("build_feed", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


class ProgramPageCoverageTests(unittest.TestCase):
    def test_authoritative_program_page_emits_listing_only_with_required_evidence(self):
        source = {
            "key": "nsa-student-programs",
            "name": "NSA Student Programs",
            "kind": "program_page",
            "company": "National Security Agency",
            "homepage": "https://www.nsa.gov/Careers/Student-Programs/",
            "apply_url": "https://apply.intelligencecareers.gov/job-listings?agency=NSA",
            "program_title": "2027 Summer Internships",
            "location": "Fort Meade, MD",
            "term": "Summer 2027",
            "profile_hint": ["cs", "engineering"],
            "posted_date_provenance": "authoritative_government",
            "required_patterns": [
                r"2027\s+Summer\s+Internships",
                r"Computer\s+Science",
            ],
        }
        html = "<h2>2027 Summer Internships</h2><li>Computer Science</li>"

        jobs = mod.parse_program_page(
            html,
            source,
            datetime(2026, 10, 2, tzinfo=timezone.utc),
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "National Security Agency")
        self.assertEqual(jobs[0]["term"], "Summer 2027")
        self.assertIn("cs", jobs[0]["profiles"])
        self.assertTrue(jobs[0]["direct_employer"])
        self.assertEqual(
            jobs[0]["url"],
            "https://apply.intelligencecareers.gov/job-listings?agency=NSA",
        )

    def test_program_page_fails_closed_when_authoritative_evidence_disappears(self):
        source = {
            "key": "program",
            "name": "Program",
            "kind": "program_page",
            "company": "Example",
            "program_title": "Summer 2027 Internships",
            "required_patterns": [r"Summer\s+2027"],
        }

        with self.assertRaisesRegex(ValueError, "missing required evidence"):
            mod.parse_program_page(
                "<p>No current programs</p>",
                source,
                datetime(2026, 10, 2, tzinfo=timezone.utc),
            )

    def test_high_value_employer_seed_tracks_nsa_and_atlas_air(self):
        seed = json.loads(
            (ROOT / "data" / "employer-seeds" / "cs-benchmark.json").read_text(
                encoding="utf-8"
            )
        )
        by_name = {row["name"]: row for row in seed["employers"]}

        self.assertIn("National Security Agency", by_name)
        self.assertIn("Atlas Air Worldwide", by_name)
        self.assertIn("NSA", by_name["National Security Agency"]["aliases"])
        self.assertIn("Atlas Air", by_name["Atlas Air Worldwide"]["aliases"])
        self.assertTrue(by_name["National Security Agency"]["domain_hints"])
        self.assertTrue(by_name["Atlas Air Worldwide"]["domain_hints"])

    def test_feed_refresh_ingests_cs_benchmark_seed(self):
        workflow = (ROOT / ".github" / "workflows" / "update-feed.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("--seed data/employer-seeds/cs-benchmark.json", workflow)


if __name__ == "__main__":
    unittest.main()
