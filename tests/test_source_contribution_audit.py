import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_contribution_audit", ROOT / "scripts" / "source_contribution_audit.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class SourceContributionAuditTests(unittest.TestCase):
    def test_unique_overlap_and_removal_semantics(self):
        feed = {
            "generated_at": "2026-09-17T00:00:00Z",
            "sources": {"a": {"count": 3}, "b": {"count": 2}, "unused": {"count": 0, "configured": True}},
            "jobs": [
                {"source_keys": ["a"], "link_kind": "direct"},
                {"source_keys": ["a", "b"], "link_kind": "listing"},
                {"source_keys": ["b"], "link_kind": "source"},
            ],
        }
        catalog = {
            "a": {"name": "A", "class": "curated GitHub/list"},
            "b": {"name": "B", "class": "direct employer / ATS"},
        }
        report = mod.build_report(feed, catalog)
        rows = {row["key"]: row for row in report["sources"]}
        self.assertEqual(rows["a"]["unique_jobs"], 1)
        self.assertEqual(rows["a"]["overlap_jobs"], 1)
        self.assertEqual(rows["b"]["unique_jobs"], 1)
        self.assertEqual(report["pairwise_overlap"], [{"left": "a", "right": "b", "canonical_jobs": 1}])
        self.assertEqual(report["summary"]["direct_employer_ats_provenance_jobs"], 2)
        self.assertEqual(report["configured_zero_contribution"], ["unused"])

    def test_link_quality_buckets_are_source_attributable(self):
        feed = {
            "sources": {"a": {"count": 4}},
            "jobs": [
                {"source_keys": ["a"], "link_kind": "direct"},
                {"source_keys": ["a"], "link_kind": "listing"},
                {"source_keys": ["a"], "link_kind": "source"},
                {"source_keys": ["a"], "url": "https://example.com/careers"},
            ],
        }
        report = mod.build_report(feed, {"a": {"name": "A"}})
        self.assertEqual(report["sources"][0]["link_quality"], {
            "aggregator_intermediary": 1,
            "direct_employer_ats": 1,
            "employer_careers_page": 1,
            "unresolved_non_authoritative": 1,
        })


if __name__ == "__main__":
    unittest.main()
