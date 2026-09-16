import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "coverage_audit.py"
spec = importlib.util.spec_from_file_location("coverage_audit", MODULE_PATH)
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


class CoverageAuditTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            "keys": {"simplify", "usajobs"},
            "names": {"simplify", "usajobs"},
            "hosts": {"raw.githubusercontent.com", "usajobs.gov", "thehartford.wd5.myworkdayjobs.com"},
            "source_hosts": {"raw.githubusercontent.com", "usajobs.gov"},
            "direct_hosts": {"thehartford.wd5.myworkdayjobs.com"},
            "companies": {"the hartford"},
            "direct_companies": {"the hartford"},
        }

    def classify(self, record, jobs=None, profiles=None, states=None):
        if jobs is None:
            jobs = [feed_job()]
        return mod.classify(
            record,
            mod.Index(jobs),
            self.catalog,
            profiles or [],
            states or [],
        )

    def test_tracking_url_matches_existing_listing(self):
        result = self.classify({
            "company": "Acme, Inc.",
            "title": "Software Engineering Intern",
            "location": "Hartford, CT",
            "url": "https://jobs.acme.com/job/12345?foo=bar&utm_source=linkedin",
        }, profiles=["cs"], states=["ct"])
        self.assertEqual(result["status"], "already_in_yartchives")

    def test_existing_listing_with_wrong_profile_is_filter_issue(self):
        result = self.classify({
            "company": "Acme Corp",
            "title": "Software Engineering Intern",
            "location": "Hartford, CT",
            "url": "https://jobs.acme.com/job/12345?foo=bar",
        }, jobs=[feed_job(profiles=["tech-business"])], profiles=["cs"], states=["CT"])
        self.assertEqual(result["status"], "filtered_or_misclassified")
        self.assertIn("missing expected profile", result["reason"])

    def test_same_ats_identity_detects_resolution_issue(self):
        result = self.classify({
            "company": "Different Display Name",
            "title": "SWE Intern",
            "location": "Stamford, CT",
            "url": "https://jobs.acme.com/en-US/careers/12345?utm_source=x",
        }, jobs=[feed_job(url="https://jobs.acme.com/jobs/12345")])
        self.assertEqual(result["status"], "duplicate_resolution_issue")

    def test_different_requisition_same_signature_is_not_counted_as_captured(self):
        result = self.classify({
            "company": "Acme Corp",
            "title": "Software Engineering Intern",
            "location": "Hartford, CT",
            "url": "https://jobs.acme.com/job/99999",
            "source": "LinkedIn",
        }, jobs=[feed_job(url="https://jobs.acme.com/job/12345")])
        self.assertEqual(result["status"], "employer_exists_but_listing_missing")
        self.assertIn("different requisition", result["reason"])

    def test_existing_employer_missing_role(self):
        result = self.classify({
            "company": "Acme Corp",
            "title": "Cybersecurity Intern",
            "location": "New Haven, CT",
            "url": "https://jobs.acme.com/job/99999",
            "source": "LinkedIn",
        }, profiles=["cs"], states=["CT"])
        self.assertEqual(result["status"], "employer_exists_but_listing_missing")

    def test_linkedin_only_new_employer_is_source_not_covered(self):
        result = self.classify({
            "company": "NewCo",
            "title": "Software Intern",
            "location": "Hartford, CT",
            "url": "https://newco.example/jobs/555",
            "source": "LinkedIn Jobs",
        }, jobs=[])
        self.assertEqual(result["status"], "source_not_covered")
        self.assertIn("audit-only", result["recommended_action"])

    def test_configured_direct_employer_missing_listing_is_configured_source_miss(self):
        result = self.classify({
            "company": "The Hartford",
            "title": "Technology Intern",
            "location": "Hartford, CT",
            "url": "https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External/job/R123",
            "source": "LinkedIn",
        }, jobs=[])
        self.assertEqual(result["status"], "configured_source_miss")

    def test_configured_direct_host_beats_discovery_source_label(self):
        result = self.classify({
            "company": "Hartford Fire Insurance",
            "title": "Technology Intern",
            "location": "Hartford, CT",
            "url": "https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External/job/R123",
            "source": "LinkedIn",
        }, jobs=[])
        self.assertEqual(result["status"], "configured_source_miss")
        self.assertIn("direct listing host", result["reason"])

    def test_external_duplicate_observations_are_collapsed(self):
        rows = [
            {
                "company": "Acme Corp",
                "title": "Software Intern",
                "location": "Hartford, CT",
                "url": "https://www.linkedin.com/jobs/view/777777",
                "source": "LinkedIn",
            },
            {
                "company": "Acme Corp",
                "title": "Software Intern",
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/88888",
                "source": "Employer site",
            },
            {
                "company": "Acme Corp",
                "title": "Software Intern",
                "location": "Hartford, CT",
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
        self.assertEqual(deduped[0]["url"], "https://jobs.acme.com/job/88888")

    def test_distinct_direct_requisitions_do_not_collapse(self):
        rows = [
            {
                "company": "Acme Corp",
                "title": "Software Intern",
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/11111",
                "source": "Employer",
            },
            {
                "company": "Acme Corp",
                "title": "Software Intern",
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/22222",
                "source": "Employer",
            },
        ]
        self.assertEqual(len(mod.dedupe_external_rows(rows)), 2)

    def test_json_and_csv_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "items.json").write_text(
                json.dumps({"discoveries": [{"company": "A"}]}), encoding="utf-8"
            )
            self.assertEqual(mod.load_rows(root / "items.json")[0]["company"], "A")
            (root / "items.csv").write_text("company,title\nB,Intern\n", encoding="utf-8")
            self.assertEqual(mod.load_rows(root / "items.csv")[0]["company"], "B")

    def test_self_describing_json_normalizes_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ct-cs.json"
            path.write_text(json.dumps({
                "name": "Connecticut CS coverage audit",
                "collected_at": "2026-09-16T12:00:00Z",
                "scope": {"profiles": ["CS"], "states": ["ct"]},
                "discoveries": [{"company": "A", "title": "Software Intern"}],
            }), encoding="utf-8")
            metadata, rows = mod.load_audit_input(path)
            self.assertEqual(metadata["scope"], {"profiles": ["cs"], "states": ["CT"]})
            self.assertEqual(rows[0]["title"], "Software Intern")

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
                "location": "Hartford, CT",
                "url": "https://jobs.acme.com/job/12345?foo=bar",
                "source": "Employer",
            },
        ]
        report = mod.build_report(
            rows,
            {"generated_at": "2026-09-16T00:00:00Z", "content_hash": "x"},
            [feed_job()],
            self.catalog,
            ["CS"],
            ["ct"],
            audit_meta={"name": "CT CS"},
        )
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["summary"]["external_observations"], 2)
        self.assertEqual(report["summary"]["external_unique_listings"], 1)
        self.assertEqual(report["summary"]["confirmed_in_feed"], 1)
        self.assertEqual(report["summary"]["visible_rate"], 1.0)
        self.assertIn("## Sample quality", mod.markdown(report))

    def test_sample_quality_flags_missing_company_and_title(self):
        quality = mod.sample_quality([{"location": "Hartford, CT"}])
        self.assertEqual(quality["error_count"], 2)
        self.assertGreaterEqual(quality["warning_count"], 2)

    def test_write_text_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "result.md"
            mod._write_text(str(path), "ok\n")
            self.assertEqual(path.read_text(), "ok\n")


if __name__ == "__main__":
    unittest.main()
