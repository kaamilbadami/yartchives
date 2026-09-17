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
            mod.Index(jobs if jobs is not None else [feed_job()]),
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
        self.assertEqual(result["reason_code"], "exact_match")

    def test_location_country_suffix_does_not_create_false_miss(self):
        result = self.classify({
            "company": "Acme Corp",
            "title": "Software Engineering Intern",
            "location": "Hartford, CT, United States",
            "url": "https://discovery.example/other-url",
        }, profiles=["cs"], states=["CT"])
        self.assertEqual(result["status"], "already_in_yartchives")

    def test_full_state_name_and_zip_normalize_to_same_location(self):
        self.assertEqual(
            mod.location_key("Hartford, Connecticut 06103, United States"),
            mod.location_key("Hartford, CT"),
        )

    def test_existing_listing_with_wrong_profile_is_filter_issue(self):
        result = self.classify({
            "company": "Acme Corp",
            "title": "Software Engineering Intern",
            "location": "Hartford, CT",
            "url": "https://jobs.acme.com/job/12345?foo=bar",
        }, jobs=[feed_job(profiles=["tech-business"])], profiles=["cs"], states=["CT"])
        self.assertEqual(result["status"], "filtered_or_misclassified")
        self.assertEqual(result["reason_code"], "present_but_hidden")
        self.assertIn("missing expected profile", result["reason"])

    def test_row_state_overrides_multi_state_sample_scope(self):
        result = self.classify({
            "company": "Acme Corp",
            "title": "Software Engineering Intern",
            "location": "Hartford, CT",
            "url": "https://jobs.acme.com/job/12345?foo=bar",
            "expected_state": "CT",
        }, profiles=["cs"], states=["CT", "NY", "MD", "DC"])
        self.assertEqual(result["status"], "already_in_yartchives")
        self.assertEqual(result["expected"]["states"], ["CT"])

    def test_icims_job_paths_share_provider_identity(self):
        left = "https://careers-gdeb.icims.com/jobs/20338/cybersecurity---2027-summer-internship/job"
        right = "https://careers-gdeb.icims.com/jobs/20338/another-display-slug/login"
        self.assertEqual(mod.url_identity(left), mod.url_identity(right))
        self.assertEqual(mod.url_identity(left), ("careers-gdeb.icims.com", "icims-job=20338"))

    def test_icims_provider_identity_matches_company_alias(self):
        record = {
            "company": "General Dynamics Electric Boat",
            "title": "Cybersecurity - 2027 Summer Internship",
            "location": "Groton, CT",
            "url": "https://careers-gdeb.icims.com/jobs/20338/cybersecurity---2027-summer-internship/job",
            "expected_profile": "cs",
            "expected_state": "CT",
            "expected_opportunity_type": "internship",
        }
        jobs = [feed_job(
            company="General Dynamics",
            title="Cybersecurity - 2027 Summer Internship",
            location="Groton, CT, 06340, US",
            url="https://careers-gdeb.icims.com/jobs/20338/cybersecurity---2027-summer-internship/job?in_iframe=1",
            profiles=["cs"],
            states=["CT"],
            opportunity_type="internship",
        )]
        result = self.classify(record, jobs=jobs)
        self.assertEqual(result["status"], "already_in_yartchives")
        self.assertEqual(result["reason_code"], "provider_identity_match")

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
        self.assertEqual(result["reason_code"], "known_employer_missing_role")

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

    def test_configured_direct_employer_missing_listing_is_pipeline_miss(self):
        result = self.classify({
            "company": "The Hartford",
            "title": "Technology Intern",
            "location": "Hartford, CT",
            "url": "https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External/job/R123",
            "source": "LinkedIn",
        }, jobs=[])
        self.assertEqual(result["status"], "configured_source_miss")
        self.assertEqual(result["reason_code"], "configured_source_listing_absent")
        self.assertIn("configured direct source", result["reason"])

    def test_known_upstream_source_missing_listing_is_pipeline_miss(self):
        result = self.classify({
            "company": "NoFeedEmployer",
            "title": "Software Intern",
            "location": "Hartford, CT",
            "url": "https://example.com/jobs/1",
            "source_key": "simplify",
        }, jobs=[])
        self.assertEqual(result["status"], "configured_source_miss")

    def test_controlled_miss_category_regression_matrix(self):
        cases = [
            (
                "configured source outranks generic employer presence",
                {
                    "company": "The Hartford",
                    "title": "Technology Intern",
                    "location": "Hartford, CT",
                    "url": "https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External/job/R123",
                    "source": "LinkedIn",
                },
                [feed_job(
                    company="The Hartford",
                    title="Finance Rotation Program Intern",
                    url="https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External/job/R999",
                )],
                ["cs"],
                ["CT"],
                "configured_source_miss",
            ),
            (
                "known employer without configured role source",
                {
                    "company": "Acme Corp",
                    "title": "Cybersecurity Intern",
                    "location": "New Haven, CT",
                    "url": "https://jobs.acme.com/job/99999",
                    "source": "LinkedIn",
                },
                [feed_job()],
                ["cs"],
                ["CT"],
                "employer_exists_but_listing_missing",
            ),
            (
                "uncovered employer and source",
                {
                    "company": "NewCo",
                    "title": "Software Intern",
                    "location": "Hartford, CT",
                    "url": "https://newco.example/jobs/555",
                    "source": "LinkedIn Jobs",
                },
                [],
                [],
                [],
                "source_not_covered",
            ),
            (
                "present listing hidden by expected filter",
                {
                    "company": "Acme Corp",
                    "title": "Software Engineering Intern",
                    "location": "Hartford, CT",
                    "url": "https://jobs.acme.com/job/12345?foo=bar",
                },
                [feed_job(profiles=["tech-business"])],
                ["cs"],
                ["CT"],
                "filtered_or_misclassified",
            ),
        ]
        for name, record, jobs, profiles, states, expected_status in cases:
            with self.subTest(name=name):
                result = self.classify(record, jobs=jobs, profiles=profiles, states=states)
                self.assertEqual(result["status"], expected_status)

    def test_json_and_csv_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "items.json").write_text(json.dumps({"discoveries": [{"company": "A"}]}), encoding="utf-8")
            self.assertEqual(mod.load_rows(root / "items.json")[0]["company"], "A")
            (root / "items.csv").write_text("company,title\nB,Intern\n", encoding="utf-8")
            self.assertEqual(mod.load_rows(root / "items.csv")[0]["company"], "B")

    def test_self_describing_json_reads_scope_and_collection_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ct-cs.json"
            path.write_text(json.dumps({
                "name": "Connecticut CS coverage audit",
                "collected_at": "2026-09-16T12:00:00Z",
                "scope": {"profiles": ["cs"], "states": ["CT"]},
                "discoveries": [{"company": "A", "title": "Software Intern"}],
            }), encoding="utf-8")
            metadata, rows = mod.load_audit_input(path)
            self.assertEqual(metadata["scope"], {"profiles": ["cs"], "states": ["CT"]})
            self.assertEqual(metadata["collected_at"], "2026-09-16T12:00:00Z")
            self.assertEqual(rows[0]["title"], "Software Intern")

    def test_report_has_machine_readable_status_counts(self):
        report = mod.build_report(
            [{"company": "Acme Corp", "title": "Software Engineering Intern", "location": "Hartford, CT"}],
            {"generated_at": "2026-09-16T00:00:00Z", "content_hash": "x"},
            [feed_job()],
            self.catalog,
            ["cs"],
            ["CT"],
            audit_meta={"name": "CT CS", "collected_at": "2026-09-16T12:00:00Z"},
        )
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["summary"]["status_counts"]["already_in_yartchives"], 1)
        self.assertEqual(report["summary"]["status_counts"]["configured_source_miss"], 0)
        rendered = mod.markdown(report)
        self.assertIn("# CT CS", rendered)
        self.assertIn("Yartchives feed snapshot", rendered)

    def test_discovery_timestamp_is_preserved_for_latency_audits(self):
        record = {
            "company": "Acme Corp",
            "title": "Software Engineering Intern",
            "location": "Hartford, CT",
            "url": "https://jobs.acme.com/job/12345",
            "first_discovered_at": "2026-09-16T10:00:00Z",
        }
        result = self.classify(record, jobs=[feed_job()])
        self.assertEqual(result["first_discovered_at"], "2026-09-16T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
