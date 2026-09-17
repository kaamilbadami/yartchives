import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "external_employer_seed_audit.py"
spec = importlib.util.spec_from_file_location("external_employer_seed_audit", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ExternalEmployerSeedAuditTests(unittest.TestCase):
    def universe(self):
        return {
            "schema_version": 1,
            "seed_sets": [{"key": "seed", "kind": "test"}],
            "employers": [
                {
                    "id": "adobe",
                    "name": "Adobe",
                    "aliases": [],
                    "seed_sets": ["seed"],
                },
                {
                    "id": "amtrak",
                    "name": "Amtrak",
                    "aliases": [],
                    "seed_sets": ["seed"],
                    "seed_metadata": {"seed": {"domain_hints": ["careers.amtrak.com"]}},
                },
            ],
        }

    def test_audit_separates_enrichments_new_employers_and_provider_gaps(self):
        rows = [
            {
                "name": "Adobe",
                "ats_system": "Workday",
                "verified": "true",
                "apply_host": "adobe.wd5.myworkdayjobs.com",
                "checked_at": "2026-08-08",
                "evidence_method": "Workday tenant probe",
            },
            {
                "name": "Amtrak",
                "ats_system": "SAP SuccessFactors",
                "verified": "true",
                "apply_host": "careers.amtrak.com",
                "checked_at": "2026-08-13",
                "evidence_method": "Careers-portal apply host",
            },
            {
                "name": "NewCo",
                "ats_system": "Jobvite",
                "verified": "true",
                "apply_host": "jobs.jobvite.com/newco",
                "checked_at": "2026-08-13",
                "evidence_method": "recorded portal URL",
            },
            {
                "name": "Unverified Co",
                "ats_system": "Workday",
                "verified": "false",
                "apply_host": "example.wd1.myworkdayjobs.com",
            },
        ]
        board_rows = [
            {"canonical_url": "https://newco.example/jobs", "ats_platform": "Jobvite"},
            {"canonical_url": "https://other.example/jobs", "ats_platform": "Jobvite"},
            {"canonical_url": "https://third.example/jobs", "ats_platform": "Workday"},
        ]

        original = self.universe()
        report = mod.audit(original, rows, board_rows)

        self.assertEqual(report["authoritative_employer_dataset"]["verified_host_rows"], 3)
        self.assertEqual(report["authoritative_employer_dataset"]["matched_verified_host_rows"], 2)
        self.assertEqual(report["authoritative_employer_dataset"]["existing_employer_enrichments"], 1)
        self.assertEqual(report["authoritative_employer_dataset"]["verified_host_new_employer_candidates"], 1)
        self.assertEqual(report["existing_employer_enrichments"][0]["current_name"], "Adobe")
        self.assertEqual(report["verified_host_new_employer_candidates"][0]["name"], "NewCo")
        self.assertEqual(report["provider_gap_counts"], {"Jobvite": 1})
        self.assertEqual(report["board_dataset"]["platform_counts"], {"Jobvite": 2, "Workday": 1})
        self.assertNotIn("careers_url", original["employers"][0])

    def test_url_only_board_dataset_cannot_create_employer_candidates(self):
        report = mod.audit(
            self.universe(),
            [],
            [{"canonical_url": "https://jobs.example.com/acme", "ats_platform": "Greenhouse"}],
        )

        self.assertEqual(report["verified_host_new_employer_candidates"], [])
        self.assertIn("never create employer identities", report["board_dataset"]["identity_policy"])

    def test_provider_aliases_map_to_supported_families(self):
        self.assertEqual(mod._provider_family("Oracle Cloud HCM"), "oracle")
        self.assertEqual(mod._provider_family("Taleo"), "oracle")
        self.assertEqual(mod._provider_family("Phenom People"), "phenom")
        self.assertIsNone(mod._provider_family("Jobvite"))


if __name__ == "__main__":
    unittest.main()
