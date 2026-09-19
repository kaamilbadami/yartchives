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

    def test_known_ats_families_are_detected_from_job_urls(self):
        cases = {
            "https://acme.wd5.myworkdayjobs.com/en-US/Careers/job/R123": "workday",
            "https://boards.greenhouse.io/acme/jobs/12345": "greenhouse",
            "https://jobs.lever.co/acme/1234": "lever",
            "https://jobs.ashbyhq.com/acme/1234": "ashby",
            "https://jobs.smartrecruiters.com/Acme/1234": "smartrecruiters",
            "https://careers-acme.icims.com/jobs/1234/job": "icims",
            "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/1234": "oracle",
            "https://jobs.jobvite.com/acme/job/abcd": "jobvite",
            "https://jobs.acme.successfactors.com/job/1234": "successfactors",
            "https://acme.taleo.net/careersection/jobdetail.ftl?job=1234": "taleo",
            "https://jobs.acme.eightfold.ai/careers/job/1234": "eightfold",
            "https://www.usajobs.gov/job/1234": "usajobs",
            "https://careers.example.com/jobs/1234": "employer/custom",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(mod.ats_family(url), expected)

    def test_missing_listings_are_grouped_by_ats_family(self):
        rows = [
            {
                "company": "Alpha",
                "title": "Software Intern",
                "location": "Hartford, CT",
                "url": "https://alpha.wd5.myworkdayjobs.com/en-US/Careers/job/R101",
                "source": "Employer site",
            },
            {
                "company": "Beta",
                "title": "Software Intern",
                "location": "Stamford, CT",
                "url": "https://beta.wd3.myworkdayjobs.com/en-US/Careers/job/R202",
                "source": "Employer site",
            },
            {
                "company": "Gamma",
                "title": "Software Intern",
                "location": "New Haven, CT",
                "url": "https://boards.greenhouse.io/gamma/jobs/30303",
                "source": "Employer site",
            },
        ]

        report = mod.build_report(
            rows,
            {"generated_at": "2026-09-16T00:00:00Z", "content_hash": "x"},
            [],
            CATALOG,
            ["cs"],
            ["CT"],
            audit_meta={"name": "CT CS"},
        )

        self.assertEqual(report["summary"]["missing_by_ats_family"], {"workday": 2, "greenhouse": 1})
        self.assertEqual([item["ats_family"] for item in report["results"]], ["workday", "workday", "greenhouse"])
        rendered = mod.markdown(report)
        self.assertIn("## Missing listings by ATS family", rendered)
        self.assertIn("`workday`: **2**", rendered)
        self.assertIn("`greenhouse`: **1**", rendered)

    def test_regional_misses_are_grouped_by_state_reason_and_discovery_source(self):
        rows = [
            {
                "company": "Alpha",
                "title": "Software Intern",
                "location": "Hartford, CT",
                "url": "https://alpha.example/jobs/1",
                "source": "Web search",
                "expected_state": "CT",
            },
            {
                "company": "Beta",
                "title": "Cybersecurity Intern",
                "location": "New York, NY",
                "url": "https://beta.example/jobs/2",
                "source": "LinkedIn",
                "expected_state": "NY",
            },
            {
                "company": "Acme Corp",
                "title": "Software Engineering Intern",
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/12345",
                "source": "LinkedIn",
                "expected_state": "CT",
            }
        ]
        report = mod.build_report(
            rows,
            {"generated_at": "2026-09-17T00:00:00Z", "content_hash": "x"},
            [feed_job()],
            CATALOG,
            ["cs"],
            ["CT", "NY"],
            audit_meta={"name": "Regional CS"},
        )
        self.assertEqual(report["summary"]["missing_by_state"], {"CT": 1, "NY": 1})
        self.assertEqual(report["summary"]["missing_by_reason_code"], {"uncovered_source": 2})
        self.assertEqual(
            report["summary"]["missing_by_discovery_source"],
            {"LinkedIn": 1, "Web search": 1},
        )
        self.assertEqual(sum(report["summary"]["by_state"]["CT"].values()), 2)

        # Check recall output logic
        self.assertIn("recall_by_state", report["summary"])
        self.assertEqual(report["summary"]["recall_by_state"]["CT"]["total"], 2)
        self.assertEqual(report["summary"]["recall_by_state"]["CT"]["missing"], 1)
        self.assertEqual(report["summary"]["recall_by_state"]["CT"]["captured"], 1)
        self.assertEqual(report["summary"]["recall_by_state"]["CT"]["recall"], 0.5)

        self.assertEqual(report["summary"]["recall_by_state"]["NY"]["total"], 1)
        self.assertEqual(report["summary"]["recall_by_state"]["NY"]["missing"], 1)
        self.assertEqual(report["summary"]["recall_by_state"]["NY"]["captured"], 0)
        self.assertEqual(report["summary"]["recall_by_state"]["NY"]["recall"], 0.0)

        self.assertIn("recall_by_region", report["summary"])
        self.assertEqual(report["summary"]["recall_by_region"]["New England"]["total"], 2)
        self.assertEqual(report["summary"]["recall_by_region"]["New England"]["missing"], 1)
        self.assertEqual(report["summary"]["recall_by_region"]["New England"]["captured"], 1)
        self.assertEqual(report["summary"]["recall_by_region"]["New England"]["recall"], 0.5)

        self.assertEqual(report["summary"]["recall_by_region"]["Mid-Atlantic"]["total"], 1)
        self.assertEqual(report["summary"]["recall_by_region"]["Mid-Atlantic"]["missing"], 1)
        self.assertEqual(report["summary"]["recall_by_region"]["Mid-Atlantic"]["captured"], 0)
        self.assertEqual(report["summary"]["recall_by_region"]["Mid-Atlantic"]["recall"], 0.0)

        rendered = mod.markdown(report)
        self.assertIn("## Results by benchmark state", rendered)
        self.assertIn("`CT`: **2** listings, **1** missing (50.0% recall)", rendered)
        self.assertIn("`NY`: **1** listings, **1** missing (0.0% recall)", rendered)
        self.assertIn("## Results by region", rendered)
        self.assertIn("`New England`: **2** listings, **1** missing (50.0% recall)", rendered)
        self.assertIn("`Mid-Atlantic`: **1** listings, **1** missing (0.0% recall)", rendered)
        self.assertIn("## Missing listings by reason code", rendered)


if __name__ == "__main__":
    unittest.main()
