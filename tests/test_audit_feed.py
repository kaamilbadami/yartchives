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


if __name__ == "__main__":
    unittest.main()
