import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "refresh_employer_universe.py"
spec = importlib.util.spec_from_file_location("refresh_employer_universe", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class RefreshEmployerUniverseTests(unittest.TestCase):
    def test_refresh_ingests_benchmark_employers_with_metadata(self):
        universe = {
            "schema_version": 1,
            "seed_sets": [{
                "key": "fortune-500-2026",
                "kind": "fortune_500",
                "edition": 2026,
                "status": "planned",
            }],
            "employers": [],
        }
        benchmark = {
            "name": "Regional CS benchmark",
            "collected_at": "2026-09-17T15:30:00Z",
            "scope": {"states": ["MD", "DC"]},
            "discoveries": [
                {
                    "company": "Lockheed Martin",
                    "expected_state": "MD",
                    "url_kind": "authoritative",
                    "url": "https://www.lockheedmartinjobs.com/job/example",
                },
                {
                    "company": "Lockheed Martin",
                    "expected_state": "DC",
                    "url_kind": "discovery_surface",
                    "url": "https://www.linkedin.com/jobs/view/example",
                },
                {
                    "company": "Leidos",
                    "expected_state": "MD",
                    "url_kind": "authoritative",
                    "url": "https://careers.leidos.com/jobs/123",
                },
            ],
        }

        refreshed = mod.refresh_universe(universe, [benchmark])

        self.assertEqual(
            [item["id"] for item in refreshed["employers"]],
            ["leidos", "lockheed-martin"],
        )
        lockheed = next(item for item in refreshed["employers"] if item["id"] == "lockheed-martin")
        key = "coverage-benchmark-2026-09-17"
        self.assertIn(key, lockheed["seed_sets"])
        self.assertEqual(lockheed["seed_metadata"][key]["states"], ["DC", "MD"])
        self.assertEqual(lockheed["seed_metadata"][key]["evidence_count"], 2)
        self.assertEqual(lockheed["seed_metadata"][key]["authoritative_evidence_count"], 1)
        self.assertEqual(
            lockheed["seed_metadata"][key]["domain_hints"],
            ["lockheedmartinjobs.com"],
        )

    def test_refresh_is_idempotent(self):
        universe = {"schema_version": 1, "seed_sets": [], "employers": []}
        benchmark = {
            "name": "Regional benchmark",
            "collected_at": "2026-09-17T15:30:00Z",
            "scope": {"states": ["MD"]},
            "discoveries": [{
                "company": "Example",
                "expected_state": "MD",
                "url_kind": "authoritative",
                "url": "https://jobs.example.com/intern/1",
            }],
        }

        once = mod.refresh_universe(universe, [benchmark])
        twice = mod.refresh_universe(once, [benchmark])
        self.assertEqual(once, twice)

    def test_multiple_benchmarks_preserve_independent_provenance(self):
        universe = {"schema_version": 1, "seed_sets": [], "employers": []}
        first = {
            "name": "First benchmark",
            "collected_at": "2026-09-17T15:30:00Z",
            "scope": {"states": ["MD"]},
            "discoveries": [{"company": "Example", "expected_state": "MD"}],
        }
        second = {
            "name": "Second benchmark",
            "collected_at": "2026-09-18T15:30:00Z",
            "scope": {"states": ["VA"]},
            "discoveries": [{"company": "Example", "expected_state": "VA"}],
        }

        refreshed = mod.refresh_universe(universe, [first, second])
        employer = refreshed["employers"][0]

        self.assertEqual(
            employer["seed_sets"],
            ["coverage-benchmark-2026-09-17", "coverage-benchmark-2026-09-18"],
        )
        self.assertEqual(
            employer["seed_metadata"]["coverage-benchmark-2026-09-17"]["states"],
            ["MD"],
        )
        self.assertEqual(
            employer["seed_metadata"]["coverage-benchmark-2026-09-18"]["states"],
            ["VA"],
        )


if __name__ == "__main__":
    unittest.main()
