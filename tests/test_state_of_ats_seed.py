import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "state_of_ats_seed.py"
spec = importlib.util.spec_from_file_location("state_of_ats_seed", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class StateOfATSSeedTests(unittest.TestCase):
    def test_build_seed_keeps_only_verified_rows_with_hosts(self):
        rows = [
            {
                "name": "Verified Co",
                "slug": "verified-co",
                "ats_system": "Workday",
                "verified": "true",
                "apply_host": "verified.wd1.myworkdayjobs.com",
                "evidence_method": "Workday tenant probe",
                "checked_at": "2026-08-12",
                "hq_country_code": "US",
                "source_url": "https://example.test/verified",
            },
            {
                "name": "No Host",
                "slug": "no-host",
                "ats_system": "Greenhouse",
                "verified": "true",
                "apply_host": "",
                "evidence_method": "",
                "checked_at": "",
                "hq_country_code": "US",
                "source_url": "https://example.test/no-host",
            },
            {
                "name": "Unverified",
                "slug": "unverified",
                "ats_system": "iCIMS",
                "verified": "false",
                "apply_host": "careers-unverified.icims.com",
                "evidence_method": "probe",
                "checked_at": "2026-08-12",
                "hq_country_code": "US",
                "source_url": "https://example.test/unverified",
            },
        ]

        seed = mod.build_seed(rows)

        self.assertEqual(seed["source"]["key"], "state-of-ats-2026-verified-hosts")
        self.assertEqual(seed["source"]["selected_count"], 1)
        self.assertEqual([item["name"] for item in seed["employers"]], ["Verified Co"])
        employer = seed["employers"][0]
        self.assertEqual(employer["domain_hints"], ["verified.wd1.myworkdayjobs.com"])
        self.assertEqual(employer["ats_system"], "Workday")
        self.assertEqual(employer["checked_at"], "2026-08-12")

    def test_build_seed_is_deterministic_by_name_then_slug(self):
        rows = [
            {
                "name": "Zulu",
                "slug": "zulu",
                "ats_system": "Workday",
                "verified": "true",
                "apply_host": "zulu.example",
                "evidence_method": "probe",
                "checked_at": "2026-08-12",
                "hq_country_code": "",
                "source_url": "https://example.test/zulu",
            },
            {
                "name": "Alpha",
                "slug": "alpha",
                "ats_system": "Workday",
                "verified": "true",
                "apply_host": "alpha.example",
                "evidence_method": "probe",
                "checked_at": "2026-08-12",
                "hq_country_code": "",
                "source_url": "https://example.test/alpha",
            },
        ]

        first = mod.build_seed(rows)
        second = mod.build_seed(list(reversed(rows)))
        self.assertEqual(first, second)
        self.assertEqual([item["name"] for item in first["employers"]], ["Alpha", "Zulu"])

    def test_checked_in_seed_has_pinned_verified_host_count(self):
        seed = json.loads(
            (ROOT / "data" / "employer-seeds" / "state-of-ats-2026-verified-hosts.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(seed["source"]["upstream_commit"], mod.UPSTREAM_COMMIT)
        self.assertEqual(seed["source"]["selected_count"], mod.EXPECTED_SELECTED_COUNT)
        self.assertEqual(len(seed["employers"]), mod.EXPECTED_SELECTED_COUNT)
        self.assertTrue(all(item["apply_host"] for item in seed["employers"]))
        self.assertTrue(
            all(item["domain_hints"] == [item["apply_host"]] for item in seed["employers"])
        )


if __name__ == "__main__":
    unittest.main()
