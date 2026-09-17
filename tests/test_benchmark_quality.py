import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "benchmark_quality.py"
spec = importlib.util.spec_from_file_location("benchmark_quality", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(company="Acme", state="CT", source="Web search", kind="authoritative", suffix="1"):
    return {
        "company": company,
        "title": f"Software Intern {suffix}",
        "location": f"Hartford, {state}",
        "url": f"https://jobs.acme.example/{suffix}",
        "source": source,
        "discovery_url": f"https://search.example/?q={suffix}",
        "url_kind": kind,
        "expected_state": state,
    }


class BenchmarkQualityTests(unittest.TestCase):
    def test_reports_required_distributions_and_url_counts(self):
        document = {
            "name": "regional",
            "benchmark_fixed_at": "2026-09-17T20:00:00Z",
            "scope": {"states": ["CT", "NY"]},
            "sampling_method": {"selection_independent_of_yartchives": True},
            "discoveries": [
                row(suffix="1"),
                row(company="Beta", state="NY", source="LinkedIn", kind="discovery_surface", suffix="2"),
            ],
        }
        report = mod.analyze(document)
        self.assertTrue(report["valid"])
        self.assertEqual(report["sample_size"], 2)
        self.assertEqual(report["state_distribution"]["CT"]["count"], 1)
        self.assertEqual(report["discovery_source_distribution"]["LinkedIn"]["count"], 1)
        self.assertEqual(report["url_counts"]["authoritative"], 1)
        self.assertEqual(report["url_counts"]["discovery_surface"], 1)
        self.assertEqual(report["concentration"]["largest_employer_share"], 0.5)

    def test_enforces_declared_quality_constraints(self):
        document = {
            "benchmark_fixed_at": "2026-09-17T20:00:00Z",
            "scope": {"states": ["CT", "NY"]},
            "sampling_method": {
                "selection_independent_of_yartchives": True,
                "quality_constraints": {
                    "minimum_sample_size": 3,
                    "minimum_per_state": 1,
                    "maximum_employer_share": 0.6,
                    "minimum_authoritative_url_rate": 0.75,
                },
            },
            "discoveries": [row(suffix="1"), row(state="NY", suffix="2")],
        }
        report = mod.analyze(document)
        self.assertFalse(report["valid"])
        self.assertFalse(report["checks"]["minimum_sample_size"]["passed"])
        self.assertFalse(report["checks"]["maximum_employer_share"]["passed"])
        self.assertTrue(report["checks"]["minimum_authoritative_url_rate"]["passed"])

    def test_rejects_rows_outside_scope_and_missing_required_fields(self):
        document = {
            "scope": {"states": ["CT"]},
            "discoveries": [{"company": "Acme", "expected_state": "NJ", "url_kind": "other"}],
        }
        report = mod.analyze(document)
        self.assertFalse(report["valid"])
        self.assertTrue(any("missing required fields" in value for value in report["errors"]))
        self.assertTrue(any("outside declared scope" in value for value in report["errors"]))


if __name__ == "__main__":
    unittest.main()
