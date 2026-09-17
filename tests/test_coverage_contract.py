import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("coverage_contract", ROOT / "scripts" / "coverage_contract.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def contract(**overrides):
    gates = {
        "minimum_unique_benchmark_listings": 2,
        "minimum_benchmark_states": 1,
        "maximum_sample_age_hours": 24,
        "maximum_feed_age_hours": 2,
        "minimum_capture_rate": 0.95,
        "minimum_visible_rate": 0.95,
        "minimum_authoritative_link_rate": 0.95,
        "maximum_median_discovery_latency_hours": 6,
        "require_latency_measurement": True,
    }
    gates.update(overrides)
    return {"name": "test", "promise": "test promise", "gates": gates}


def report(results):
    return {
        "audit": {"collected_at": "2026-09-17T11:00:00Z"},
        "feed": {"generated_at": "2026-09-17T11:30:00Z"},
        "scope": {"states": ["CT"]},
        "summary": {"external_unique_listings": len(results)},
        "results": results,
    }


class CoverageContractTests(unittest.TestCase):
    NOW = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)

    def test_all_gates_can_earn_ready_status(self):
        rows = [
            {"status": "already_in_yartchives", "first_discovered_at": "2026-09-17T10:00:00Z", "matched_job": {"first_seen": "2026-09-17T11:00:00Z", "link_kind": "direct"}},
            {"status": "already_in_yartchives", "first_discovered_at": "2026-09-17T09:00:00Z", "matched_job": {"first_seen": "2026-09-17T11:00:00Z", "link_kind": "direct"}},
        ]
        status = mod.evaluate(contract(), [report(rows)], self.NOW)
        self.assertTrue(status["ready"])
        self.assertEqual(status["status"], "ready_as_only_source")

    def test_missing_latency_evidence_blocks_claim(self):
        rows = [
            {"status": "already_in_yartchives", "matched_job": {"link_kind": "direct"}},
            {"status": "already_in_yartchives", "matched_job": {"link_kind": "direct"}},
        ]
        status = mod.evaluate(contract(), [report(rows)], self.NOW)
        latency = next(check for check in status["checks"] if check["name"] == "median_discovery_latency_hours")
        self.assertFalse(status["ready"])
        self.assertFalse(latency["measurable"])

    def test_probable_capture_does_not_count_as_visible(self):
        rows = [
            {"status": "already_in_yartchives", "first_discovered_at": "2026-09-17T10:00:00Z", "matched_job": {"first_seen": "2026-09-17T11:00:00Z", "link_kind": "direct"}},
            {"status": "filtered_or_misclassified", "first_discovered_at": "2026-09-17T10:00:00Z", "matched_job": {"first_seen": "2026-09-17T11:00:00Z", "link_kind": "direct"}},
        ]
        status = mod.evaluate(contract(minimum_capture_rate=1.0), [report(rows)], self.NOW)
        checks = {check["name"]: check for check in status["checks"]}
        self.assertTrue(checks["capture_rate"]["passed"])
        self.assertFalse(checks["visible_rate"]["passed"])

    def test_same_requisition_across_reports_counts_once(self):
        duplicate = {
            "company": "Example Corp",
            "title": "Software Engineering Intern",
            "location": "Hartford, CT",
            "url": "https://example.wd1.myworkdayjobs.com/jobs/job/Hartford/R12345",
            "status": "already_in_yartchives",
            "first_discovered_at": "2026-09-17T10:00:00Z",
            "matched_job": {
                "first_seen": "2026-09-17T11:00:00Z",
                "link_kind": "direct",
            },
        }
        first_report = report([duplicate])
        second_report = report([
            {
                **duplicate,
                "url": "https://example.wd1.myworkdayjobs.com/en-US/jobs/job/Hartford/R12345",
            },
            {
                "company": "Another Corp",
                "title": "Data Intern",
                "location": "New Haven, CT",
                "url": "https://jobs.example.com/requisitions/67890",
                "status": "source_not_covered",
            },
        ])

        status = mod.evaluate(contract(minimum_capture_rate=0.5, minimum_visible_rate=0.5), [first_report, second_report], self.NOW)
        checks = {check["name"]: check for check in status["checks"]}

        self.assertEqual(status["evidence"]["unique_benchmark_listings"], 2)
        self.assertEqual(checks["benchmark_size"]["actual"], 2)
        self.assertEqual(checks["capture_rate"]["actual"], 0.5)
        self.assertEqual(checks["visible_rate"]["actual"], 0.5)
        self.assertEqual(checks["authoritative_link_rate"]["actual"], 1.0)
        self.assertEqual(status["evidence"]["latency_observations"], 1)


if __name__ == "__main__":
    unittest.main()
