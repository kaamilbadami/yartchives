import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "employer_universe.py"
spec = importlib.util.spec_from_file_location("employer_universe", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EmployerUniverseTests(unittest.TestCase):
    def empty_universe(self):
        return {"schema_version": 1, "seed_sets": [], "employers": []}

    def test_merge_preserves_seed_provenance_and_deduplicates_aliases(self):
        first = {
            "schema_version": 1,
            "source": {"key": "fortune-500-2026", "kind": "fortune_500", "edition": 2026},
            "employers": [{"name": "Lockheed Martin", "aliases": ["Lockheed Martin Corp."]}],
        }
        second = {
            "schema_version": 1,
            "source": {"key": "regional-benchmark", "kind": "coverage_benchmark"},
            "employers": [{"name": "Lockheed Martin Corp.", "aliases": ["Lockheed Martin"]}],
        }

        merged = mod.merge_seed(self.empty_universe(), first)
        merged = mod.merge_seed(merged, second)

        self.assertEqual(len(merged["employers"]), 1)
        employer = merged["employers"][0]
        self.assertEqual(employer["id"], "lockheed-martin")
        self.assertEqual(employer["name"], "Lockheed Martin")
        self.assertEqual(employer["aliases"], ["Lockheed Martin Corp."])
        self.assertEqual(employer["seed_sets"], ["fortune-500-2026", "regional-benchmark"])

    def test_merge_preserves_metadata_by_seed(self):
        benchmark = {
            "schema_version": 1,
            "source": {"key": "regional-benchmark", "kind": "coverage_benchmark"},
            "employers": [{
                "name": "Lockheed Martin",
                "states": ["MD", "VA"],
                "domain_hints": ["lockheedmartinjobs.com"],
                "evidence_count": 4,
                "authoritative_evidence_count": 2,
            }],
        }
        fortune = {
            "schema_version": 1,
            "source": {"key": "fortune-500-2026", "kind": "fortune_500", "edition": 2026},
            "employers": [{"name": "Lockheed Martin", "rank": 57}],
        }

        merged = mod.merge_seed(self.empty_universe(), benchmark)
        merged = mod.merge_seed(merged, fortune)
        employer = merged["employers"][0]

        self.assertEqual(employer["seed_metadata"]["regional-benchmark"]["states"], ["MD", "VA"])
        self.assertEqual(
            employer["seed_metadata"]["regional-benchmark"]["domain_hints"],
            ["lockheedmartinjobs.com"],
        )
        self.assertEqual(employer["seed_metadata"]["regional-benchmark"]["evidence_count"], 4)
        self.assertEqual(employer["seed_metadata"]["fortune-500-2026"]["rank"], 57)

    def test_remerging_seed_replaces_only_that_seed_metadata(self):
        benchmark = {
            "schema_version": 1,
            "source": {"key": "regional-benchmark", "kind": "coverage_benchmark"},
            "employers": [{"name": "Example", "states": ["MD"], "evidence_count": 1}],
        }
        fortune = {
            "schema_version": 1,
            "source": {"key": "fortune-500-2026", "kind": "fortune_500", "edition": 2026},
            "employers": [{"name": "Example", "rank": 10}],
        }
        refreshed = {
            **benchmark,
            "employers": [{"name": "Example", "states": ["MD", "VA"], "evidence_count": 3}],
        }

        merged = mod.merge_seed(self.empty_universe(), benchmark)
        merged = mod.merge_seed(merged, fortune)
        merged = mod.merge_seed(merged, refreshed)
        employer = merged["employers"][0]

        self.assertEqual(employer["seed_metadata"]["regional-benchmark"]["states"], ["MD", "VA"])
        self.assertEqual(employer["seed_metadata"]["regional-benchmark"]["evidence_count"], 3)
        self.assertEqual(employer["seed_metadata"]["fortune-500-2026"], {"rank": 10})

    def test_same_seed_is_idempotent(self):
        seed = {
            "schema_version": 1,
            "source": {"key": "fortune-500-2026", "kind": "fortune_500", "edition": 2026},
            "employers": [{"name": "Example Holdings", "rank": 123}],
        }
        once = mod.merge_seed(self.empty_universe(), seed)
        twice = mod.merge_seed(once, seed)
        self.assertEqual(once, twice)

    def test_duplicate_employer_in_seed_is_rejected(self):
        seed = {
            "schema_version": 1,
            "source": {"key": "fortune-500-2026", "kind": "fortune_500", "edition": 2026},
            "employers": [{"name": "Example Inc."}, {"name": "example inc"}],
        }
        with self.assertRaises(ValueError):
            mod.validate_seed(seed)

    def test_unknown_seed_reference_is_rejected(self):
        universe = {
            "schema_version": 1,
            "seed_sets": [],
            "employers": [{
                "id": "example",
                "name": "Example",
                "aliases": [],
                "seed_sets": ["missing-seed"],
            }],
        }
        with self.assertRaises(ValueError):
            mod.validate_universe(universe)

    def test_seed_metadata_must_reference_employer_seed_membership(self):
        universe = {
            "schema_version": 1,
            "seed_sets": [{"key": "regional-benchmark", "kind": "coverage_benchmark"}],
            "employers": [{
                "id": "example",
                "name": "Example",
                "aliases": [],
                "seed_sets": [],
                "seed_metadata": {"regional-benchmark": {"states": ["MD"]}},
            }],
        }
        with self.assertRaises(ValueError):
            mod.validate_universe(universe)


if __name__ == "__main__":
    unittest.main()
