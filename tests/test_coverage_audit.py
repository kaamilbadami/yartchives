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
            "hosts": {"raw.githubusercontent.com", "usajobs.gov"},
            "companies": {"the hartford"},
        }

    def classify(self, record, jobs=None, profiles=None, states=None):
        return mod.classify(
            record,
            mod.Index(jobs or [feed_job()]),
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
        }, profiles=["cs"], states=["CT"])
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

    def test_configured_direct_employer_missing_listing_is_filter_issue(self):
        result = self.classify({
            "company": "The Hartford",
            "title": "Technology Intern",
            "location": "Hartford, CT",
            "url": "https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External/job/R123",
            "source": "LinkedIn",
        }, jobs=[])
        self.assertEqual(result["status"], "filtered_or_misclassified")
        self.assertIn("configured direct source", result["reason"])

    def test_json_and_csv_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "items.json").write_text(json.dumps({"discoveries": [{"company": "A"}]}), encoding="utf-8")
            self.assertEqual(mod.load_rows(root / "items.json")[0]["company"], "A")
            (root / "items.csv").write_text("company,title\nB,Intern\n", encoding="utf-8")
            self.assertEqual(mod.load_rows(root / "items.csv")[0]["company"], "B")

    def test_report_has_machine_readable_status_counts(self):
        report = mod.build_report(
            [{"company": "Acme Corp", "title": "Software Engineering Intern", "location": "Hartford, CT"}],
            {"generated_at": "2026-09-16T00:00:00Z", "content_hash": "x"},
            [feed_job()],
            self.catalog,
            ["cs"],
            ["CT"],
        )
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["summary"]["status_counts"]["already_in_yartchives"], 1)
        self.assertIn("Yartchives external coverage audit", mod.markdown(report))


if __name__ == "__main__":
    unittest.main()
