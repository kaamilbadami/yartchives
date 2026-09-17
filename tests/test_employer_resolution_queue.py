import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "employer_resolution_queue.py"
spec = importlib.util.spec_from_file_location("employer_resolution_queue", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EmployerResolutionQueueTests(unittest.TestCase):
    def universe(self):
        return {
            "schema_version": 1,
            "seed_sets": [
                {"key": "benchmark-a", "kind": "coverage_benchmark"},
                {"key": "benchmark-b", "kind": "coverage_benchmark"},
            ],
            "employers": [],
        }

    def employer(self, employer_id, name, metadata, **extra):
        return {
            "id": employer_id,
            "name": name,
            "aliases": [],
            "seed_sets": sorted(metadata),
            "seed_metadata": metadata,
            **extra,
        }

    def test_flattens_metadata_and_preserves_per_seed_evidence(self):
        universe = self.universe()
        universe["employers"] = [self.employer("acme", "Acme", {
            "benchmark-a": {
                "domain_hints": ["careers.acme.com"],
                "states": ["md"],
                "evidence_count": 2,
                "authoritative_evidence_count": 1,
            },
            "benchmark-b": {
                "domain_hints": ["careers.acme.com", "jobs.acme.com"],
                "states": ["VA"],
                "evidence_count": 3,
                "authoritative_evidence_count": 2,
            },
        })]

        row = mod.build_queue(universe)["employers"][0]
        self.assertEqual(row["domain_hints"], ["careers.acme.com", "jobs.acme.com"])
        self.assertEqual(row["states"], ["MD", "VA"])
        self.assertEqual(row["evidence_count"], 5)
        self.assertEqual(row["authoritative_evidence_count"], 3)
        self.assertEqual([item["seed_key"] for item in row["evidence_sources"]], ["benchmark-a", "benchmark-b"])

    def test_priority_is_readiness_then_evidence_then_id(self):
        universe = self.universe()
        universe["employers"] = [
            self.employer("missing", "Missing", {"benchmark-a": {"evidence_count": 20}}),
            self.employer("shared", "Shared", {"benchmark-a": {
                "domain_hints": ["job-boards.greenhouse.io"],
                "evidence_count": 30,
                "authoritative_evidence_count": 30,
            }}),
            self.employer("ready-low", "Ready Low", {"benchmark-a": {
                "domain_hints": ["ready.example"], "evidence_count": 2,
            }}),
            self.employer("ready-high", "Ready High", {"benchmark-a": {
                "domain_hints": ["careers.example"], "evidence_count": 5,
                "authoritative_evidence_count": 2,
            }}),
        ]

        queue = mod.build_queue(universe)
        self.assertEqual(
            [row["id"] for row in queue["employers"]],
            ["ready-high", "ready-low", "shared", "missing"],
        )
        self.assertEqual(queue["summary"], {
            "unresolved_employers": 4,
            "selected_employers": 4,
            "ready": 2,
            "needs_tenant_identity": 1,
            "no_domain_hint": 1,
        })

    def test_tenant_path_makes_shared_provider_hint_ready(self):
        universe = self.universe()
        universe["employers"] = [self.employer("acme", "Acme", {"benchmark-a": {
            "domain_hints": ["https://job-boards.greenhouse.io/acme"],
            "evidence_count": 1,
        }})]
        row = mod.build_queue(universe)["employers"][0]
        self.assertEqual(row["resolution_readiness"], "ready")

    def test_resolved_employers_are_excluded(self):
        universe = self.universe()
        metadata = {"benchmark-a": {"domain_hints": ["careers.acme.com"], "evidence_count": 1}}
        universe["employers"] = [
            self.employer("done", "Done", metadata, careers_url="https://careers.done.com"),
            self.employer("todo", "Todo", metadata),
        ]
        self.assertEqual([row["id"] for row in mod.build_queue(universe)["employers"]], ["todo"])

    def test_ready_only_and_limit_are_deterministic(self):
        universe = self.universe()
        universe["employers"] = [
            self.employer(key, key.title(), {"benchmark-a": {
                "domain_hints": [f"careers.{key}.com"],
                "evidence_count": count,
            }})
            for key, count in (("one", 1), ("two", 2), ("three", 3))
        ]
        queue = mod.build_queue(universe, ready_only=True, limit=2)
        self.assertEqual([row["id"] for row in queue["employers"]], ["three", "two"])
        self.assertEqual(queue["summary"]["selected_employers"], 2)
        with self.assertRaisesRegex(ValueError, "limit must be positive"):
            mod.build_queue(universe, limit=0)


if __name__ == "__main__":
    unittest.main()
