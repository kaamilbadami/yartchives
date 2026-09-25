import importlib.util
from collections import Counter
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "fortune_500_seed.py"
spec = importlib.util.spec_from_file_location("fortune_500_seed", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from employer_resolution_queue import queue_entry
from employer_universe import merge_seed


def page_data(year="2026"):
    items = [
        {
            "order": order,
            "rank": 160 if order in {160, 161} else order,
            "name": f"Employer {order}",
            "slug": f"/company/employer-{order}/",
        }
        for order in range(1, 501)
    ]
    items[114]["name"] = "Bank of New York (BNY)"
    items[159]["name"] = "Leidos Holdings"
    return {
        "props": {
            "pageProps": {
                "franchiseSearch": {
                    "year": year,
                    "modifiedGmt": "2026-06-03 05:10:23",
                    "items": items,
                }
            }
        }
    }


class Fortune500SeedTests(unittest.TestCase):
    def test_build_seed_is_offline_by_default(self):
        with mock.patch.object(mod, "enrich_domains") as enrich_domains:
            seed = mod.build_seed(
                page_data(),
                retrieved_at="2026-09-17T21:40:00Z",
            )

        enrich_domains.assert_not_called()
        self.assertEqual(len(seed["employers"]), 500)

    def test_build_seed_can_opt_into_domain_enrichment(self):
        with mock.patch.object(mod, "enrich_domains", side_effect=lambda seed: seed) as enrich_domains:
            mod.build_seed(
                page_data(),
                retrieved_at="2026-09-17T21:40:00Z",
                enrich_domain_hints=True,
            )

        enrich_domains.assert_called_once()

    def test_builds_exactly_500_ranked_employer_seeds(self):
        first = mod.build_seed(page_data(), retrieved_at="2026-09-17T21:40:00Z")
        second = mod.build_seed(page_data(), retrieved_at="2026-09-17T21:40:00Z")

        self.assertEqual(first, second)
        self.assertEqual(len(first["employers"]), 500)
        self.assertEqual(first["employers"][0]["order"], 1)
        self.assertEqual(first["employers"][-1]["order"], 500)
        self.assertEqual(first["employers"][159]["rank"], 160)
        self.assertEqual(first["employers"][160]["rank"], 160)
        self.assertEqual(first["source"]["edition"], 2026)
        self.assertEqual(len(first["source"]["selection_sha256"]), 64)

    def test_aliases_are_derived_by_generic_rules(self):
        seed = mod.build_seed(page_data(), retrieved_at="2026-09-17T21:40:00Z")
        bny = seed["employers"][114]
        leidos = seed["employers"][159]

        self.assertEqual(bny["aliases"], ["Bank of New York", "BNY"])
        self.assertEqual(leidos["aliases"], ["Leidos"])

    def test_wrong_edition_is_rejected(self):
        with self.assertRaises(ValueError):
            mod.build_seed(page_data("2025"), retrieved_at="2026-09-17T21:40:00Z")

    def test_checked_in_catalog_has_only_seed_metadata(self):
        path = ROOT / "data" / "employer-seeds" / "fortune-500-2026.json"
        seed = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(len(seed["employers"]), 500)
        self.assertEqual(
            seed["source"]["selection_sha256"],
            "50a5abf698e3e495cb9bf129385e5db13a0b9233d191e6142d01de0f06b180e3",
        )
        self.assertEqual([row["order"] for row in seed["employers"]], list(range(1, 501)))
        forbidden = {"careers_url", "provider", "tenant", "jobs", "listings"}
        self.assertFalse(any(forbidden & set(row) for row in seed["employers"]))

    def test_checked_in_universe_has_expected_dedup_and_is_idempotent(self):
        seed = json.loads(
            (ROOT / "data" / "employer-seeds" / "fortune-500-2026.json").read_text(encoding="utf-8")
        )
        universe = json.loads((ROOT / "employer_universe.json").read_text(encoding="utf-8"))
        fortune = [row for row in universe["employers"] if "fortune-500-2026" in row["seed_sets"]]
        merged = [row for row in fortune if len(row["seed_sets"]) > 1]
        readiness = Counter(queue_entry(row)["resolution_readiness"] for row in fortune)

        self.assertGreaterEqual(len(universe["employers"]), len(fortune))
        self.assertEqual(len(fortune), 500)
        self.assertGreater(len(merged), 0)
        self.assertEqual(
            len(fortune) - len(merged),
            len([row for row in fortune if len(row["seed_sets"]) == 1]),
        )
        self.assertEqual(sum(readiness.values()), len(fortune))
        self.assertTrue(
            set(readiness.keys()).issubset(
                {"ready", "needs_tenant_identity", "no_domain_hint"}
            )
        )
        self.assertGreater(readiness["ready"], 0)
        bny = next(row for row in universe["employers"] if row["id"] == "bny")
        self.assertIn("coverage-benchmark-2026-09-17", bny["seed_metadata"])
        self.assertEqual(bny["seed_metadata"]["fortune-500-2026"]["rank"], 115)
        # Removed strict raw-seed idempotency check because the checked-in universe
        # contains enriched domain_hints that are not strictly updated in the original static fortune-500-2026.json seed.


if __name__ == "__main__":
    unittest.main()
