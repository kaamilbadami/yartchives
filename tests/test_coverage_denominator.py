import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "coverage_audit_runner.py"
spec = importlib.util.spec_from_file_location("coverage_audit_runner", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def feed_job(**overrides):
    row = {
        "id": "abc123",
        "company": "Acme Corp",
        "title": "Software Engineering Intern",
        "location": "Hartford, CT",
        "url": "https://jobs.acme.com/job/12345?foo=bar",
        "profiles": ["cs"],
        "states": ["CT"],
        "opportunity_type": "internship",
        "education_level": "undergrad",
        "source_keys": ["simplify"],
    }
    row.update(overrides)
    return row


CATALOG = {
    "keys": {"simplify", "usajobs"},
    "names": {"simplify", "usajobs"},
    "hosts": {"raw.githubusercontent.com", "usajobs.gov"},
    "companies": set(),
}


class CoverageDenominatorTests(unittest.TestCase):
    def test_cross_surface_observations_collapse_to_one_listing(self):
        rows = [
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, CT",
                "url": "https://www.linkedin.com/jobs/view/777777",
                "source": "LinkedIn",
            },
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, Connecticut, United States",
                "url": "https://jobs.acme.com/job/12345",
                "source": "Employer site",
            },
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, CT 06103",
                "url": "https://app.joinhandshake.com/jobs/99999",
                "source": "Handshake",
            },
        ]

        deduped = mod.dedupe_external_rows(rows)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["_audit_observation_count"], 3)
        self.assertEqual(
            set(deduped[0]["_audit_observed_sources"]),
            {"LinkedIn", "Employer site", "Handshake"},
        )
        self.assertEqual(deduped[0]["url"], "https://jobs.acme.com/job/12345")

    def test_distinct_authoritative_requisitions_do_not_collapse(self):
        rows = [
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/11111",
                "source": "Employer site",
            },
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/22222",
                "source": "Employer site",
            },
        ]
        self.assertEqual(len(mod.dedupe_external_rows(rows)), 2)

    def test_tracking_variants_of_same_direct_url_collapse(self):
        rows = [
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/12345?utm_source=linkedin",
                "source": "LinkedIn",
            },
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/12345?utm_source=handshake",
                "source": "Handshake",
            },
        ]
        self.assertEqual(len(mod.dedupe_external_rows(rows)), 1)

    def test_report_uses_unique_listing_denominator(self):
        rows = [
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, CT",
                "url": "https://www.linkedin.com/jobs/view/777777",
                "source": "LinkedIn",
            },
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, Connecticut",
                "url": "https://jobs.acme.com/job/12345?foo=bar",
                "source": "Employer site",
            },
        ]

        report = mod.build_report(
            rows,
            {"generated_at": "2026-09-16T00:00:00Z", "content_hash": "x"},
            [feed_job()],
            CATALOG,
            ["cs"],
            ["CT"],
            audit_meta={"name": "CT CS"},
        )

        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["summary"]["external_observations"], 2)
        self.assertEqual(report["summary"]["external_unique_listings"], 1)
        self.assertEqual(report["summary"]["duplicate_observations_collapsed"], 1)
        self.assertEqual(report["summary"]["external_listings"], 1)
        self.assertEqual(report["summary"]["visible_rate"], 1.0)
        self.assertEqual(report["results"][0]["observation_count"], 2)
        self.assertEqual(
            set(report["results"][0]["observed_sources"]),
            {"LinkedIn", "Employer site"},
        )

        rendered = mod.markdown(report)
        self.assertIn("External observations collected: **2**", rendered)
        self.assertIn("Unique external listings (denominator): **1**", rendered)
        self.assertIn("Duplicate observations collapsed: **1**", rendered)


if __name__ == "__main__":
    unittest.main()
