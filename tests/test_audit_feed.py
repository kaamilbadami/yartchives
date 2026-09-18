import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit_feed", ROOT / "scripts" / "audit_feed.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class StaleUnavailableAuditTests(unittest.TestCase):
    def test_classifies_only_evidence_backed_stale_unavailable_risks(self):
        doc = {
            "generated_at": "2026-09-18T12:00:00Z",
            "sources": {
                "dead-source": {"ok": False},
                "healthy-source": {"ok": True},
            },
            "jobs": [
                {
                    "id": "failed-only",
                    "company": "A",
                    "title": "Intern",
                    "location": "CT",
                    "source_keys": ["dead-source"],
                    "posted_at": "2026-09-17T12:00:00Z",
                },
                {
                    "id": "mixed",
                    "company": "B",
                    "title": "Intern",
                    "location": "NY",
                    "source_keys": ["dead-source", "healthy-source"],
                    "posted_at": "2026-09-17T12:00:00Z",
                },
                {
                    "id": "dead-link",
                    "company": "C",
                    "title": "Intern",
                    "location": "MD",
                    "source_keys": ["healthy-source"],
                    "link_status": "dead",
                    "posted_at": "2026-09-17T12:00:00Z",
                },
                {
                    "id": "unknown-direct",
                    "company": "D",
                    "title": "Intern",
                    "location": "DC",
                    "source_keys": ["healthy-source"],
                    "link_kind": "direct",
                    "link_status": "unknown",
                    "posted_at": "2026-09-17T12:00:00Z",
                },
                {
                    "id": "unavailable",
                    "company": "E",
                    "title": "Intern",
                    "location": "Remote",
                    "source_keys": ["healthy-source"],
                    "posted_at": "2026-09-17T12:00:00Z",
                },
            ],
        }
        inspections = {
            "listing_index": {"unavailable": "workday:e"},
            "entries": {
                "workday:e": {
                    "inspection": {"status": "unavailable"}
                }
            },
        }

        report = mod.stale_unavailable_report(
            doc,
            inspections,
            datetime(2026, 9, 18, 12, tzinfo=timezone.utc),
        )

        self.assertEqual([j["id"] for j in report["failed_source_only"]], ["failed-only"])
        self.assertEqual([j["id"] for j in report["known_dead_links"]], ["dead-link"])
        self.assertEqual([j["id"] for j in report["unknown_direct_links"]], ["unknown-direct"])
        self.assertEqual([j["id"] for j in report["unavailable_inspections"]], ["unavailable"])
        self.assertEqual(report["evidence_backed_risk_jobs"], 4)

    def test_old_posting_is_review_bucket_not_evidence_backed_stale(self):
        doc = {
            "generated_at": "2026-09-18T12:00:00Z",
            "sources": {"healthy": {"ok": True}},
            "jobs": [
                {
                    "id": "old",
                    "company": "A",
                    "title": "Intern",
                    "location": "CT",
                    "source_keys": ["healthy"],
                    "posted_at": "2026-05-01T12:00:00Z",
                },
                {
                    "id": "missing-date",
                    "company": "B",
                    "title": "Intern",
                    "location": "NY",
                    "source_keys": ["healthy"],
                    "posted_at": None,
                },
            ],
        }

        report = mod.stale_unavailable_report(
            doc,
            {},
            datetime(2026, 9, 18, 12, tzinfo=timezone.utc),
        )

        self.assertEqual(report["evidence_backed_risk_jobs"], 0)
        self.assertEqual([j["id"] for j in report["age_review_90d"]], ["old"])
        self.assertEqual([j["id"] for j in report["missing_posted_at"]], ["missing-date"])


class PostingDateAuditTests(unittest.TestCase):
    def test_reports_authority_missing_provenance_and_source_conflicts(self):
        doc = {
            "generated_at": "2026-09-18T12:00:00Z",
            "jobs": [
                {
                    "id": "authoritative",
                    "company": "A",
                    "title": "Intern",
                    "posted_at": "2026-09-15T12:00:00Z",
                    "posted_date_provenance": "authoritative_employer",
                    "posted_date_source_key": "direct-a",
                    "posted_date_observations": [
                        {
                            "source_key": "direct-a",
                            "posted_at": "2026-09-15T12:00:00Z",
                            "provenance": "authoritative_employer",
                        }
                    ],
                },
                {
                    "id": "override",
                    "company": "B",
                    "title": "Intern",
                    "posted_at": "2026-09-17T12:00:00Z",
                    "posted_date_provenance": "aggregator",
                    "posted_date_source_key": "agg",
                    "posted_date_observations": [
                        {
                            "source_key": "direct-b",
                            "posted_at": "2026-09-01T12:00:00Z",
                            "provenance": "authoritative_employer",
                        },
                        {
                            "source_key": "agg",
                            "posted_at": "2026-09-17T12:00:00Z",
                            "provenance": "aggregator",
                        },
                    ],
                },
                {
                    "id": "legacy",
                    "company": "C",
                    "title": "Intern",
                    "posted_at": "2026-09-16T12:00:00Z",
                },
                {
                    "id": "future",
                    "company": "D",
                    "title": "Intern",
                    "posted_at": "2026-09-19T12:00:00Z",
                    "posted_date_provenance": "aggregator",
                },
            ],
        }

        report = mod.posting_date_report(
            doc,
            datetime(2026, 9, 18, 12, tzinfo=timezone.utc),
        )

        self.assertEqual(report["by_provenance"], {
            "aggregator": 2,
            "authoritative_employer": 1,
        })
        self.assertEqual([j["id"] for j in report["missing_provenance"]], ["legacy"])
        self.assertEqual([j["id"] for j in report["future_dates"]], ["future"])
        self.assertEqual([j["id"] for j in report["conflicting_observations"]], ["override"])
        self.assertEqual([j["id"] for j in report["aggregator_overrides_authoritative"]], ["override"])


class DestinationLinkReportTests(unittest.TestCase):
    def test_destination_link_report_metrics(self):
        doc = {
            "jobs": [
                {
                    "id": "1",
                    "link_kind": "direct",
                    "link_status": "ok",
                    "url": "https://careers.google.com/jobs/results/123",
                    "source_keys": ["src-a"]
                },
                {
                    "id": "2",
                    "link_kind": "direct",
                    "link_status": "dead",
                    "url": "https://jobs.ashbyhq.com/example/456",
                    "source_keys": ["src-a"]
                },
                {
                    "id": "3",
                    "link_kind": "direct",
                    "link_status": "unknown",
                    "url": "https://job-boards.greenhouse.io/test/jobs/123",
                    "source_keys": ["src-b"]
                },
                {
                    "id": "4",
                    "link_kind": "direct",
                    "url": "https://example.com/careers/abc",
                    "source_keys": ["src-a", "src-c"]
                },
                {
                    "id": "5",
                    "link_kind": "direct",
                    "link_status": "ok",
                    "url": "https://careers.company.com/job/5",
                    "source_keys": ["src-b"]
                }
            ]
        }

        inspections = {
            "listing_index": {"5": "workday:5"},
            "entries": {
                "workday:5": {
                    "inspection": {"status": "unavailable"}
                }
            }
        }

        report = mod.destination_link_report(doc, inspections)

        self.assertEqual(report["link_rates"]["reachable"], 1)
        self.assertEqual(report["link_rates"]["broken"], 2)
        self.assertEqual(report["link_rates"]["transient"], 1)
        self.assertEqual(report["link_rates"]["unverified"], 1)

        self.assertEqual(report["provider_rates"]["unknown"]["reachable"], 1)
        self.assertEqual(report["provider_rates"]["ashby"]["broken"], 1)
        self.assertEqual(report["provider_rates"]["greenhouse"]["transient"], 1)
        self.assertEqual(report["provider_rates"]["unknown"]["unverified"], 1)
        self.assertEqual(report["provider_rates"]["unknown"]["broken"], 1)

        self.assertEqual(report["source_rates"]["src-a"]["reachable"], 1)
        self.assertEqual(report["source_rates"]["src-a"]["broken"], 1)
        self.assertEqual(report["source_rates"]["src-a"]["unverified"], 1)
        self.assertEqual(report["source_rates"]["src-b"]["transient"], 1)
        self.assertEqual(report["source_rates"]["src-b"]["broken"], 1)
        self.assertEqual(report["source_rates"]["src-c"]["unverified"], 1)


class BuildAuditReportTests(unittest.TestCase):
    def test_builds_and_renders_comprehensive_audit_report(self):
        doc = {
            "generated_at": "2026-09-18T12:00:00Z",
            "sources": {"direct-source": {"ok": True}},
            "jobs": [
                {
                    "id": "job1",
                    "company": "Company A",
                    "title": "Software Intern",
                    "location": "CT",
                    "link_kind": "direct",
                    "link_status": "ok",
                    "url": "https://example.wd1.myworkdayjobs.com/en-US/careers/job/CT/Role_R123",
                    "posted_at": "2026-09-15T12:00:00Z",
                    "posted_date_provenance": "authoritative_employer",
                    "source_keys": ["direct-source"],
                },
                {
                    "id": "job2",
                    "company": "Company B",
                    "title": "Data Intern",
                    "location": "NY",
                    "link_kind": "source",
                    "url": "",
                    "posted_at": None,
                    "source_keys": ["speedyapply-ai"],
                },
            ],
        }

        report = mod.build_audit_report(
            doc,
            {},
            datetime(2026, 9, 18, 12, tzinfo=timezone.utc),
        )

        self.assertEqual(report["summary"]["total_jobs"], 2)
        self.assertEqual(report["summary"]["broken_destinations"]["workday_contract_violations"], 1)
        self.assertEqual(report["summary"]["missing_dates"]["missing_posted_at"], 1)

        self.assertEqual(report["summary"]["broken_destinations"]["reachable"], 1)
        self.assertEqual(report["summary"]["broken_destinations"]["broken"], 0)
        self.assertEqual(report["summary"]["broken_destinations"]["transient"], 0)
        self.assertEqual(report["summary"]["broken_destinations"]["unverified"], 0)

        rendered = mod.render_markdown_report(report)
        self.assertIn("# Yartchives feed quality audit report", rendered)
        self.assertIn("Total indexed jobs: **2**", rendered)
        self.assertIn("Missing posting timestamp (`posted_at`): **1**", rendered)
        self.assertIn("- Reachable: **1**", rendered)
        self.assertIn("- `workday` (1 total): 1 reachable", rendered)
        self.assertIn("- `direct-source` (1 total): 1 reachable", rendered)

if __name__ == "__main__":
    unittest.main()
