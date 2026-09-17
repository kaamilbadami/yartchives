import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "employer_resolution_lifecycle.py"
spec = importlib.util.spec_from_file_location("employer_resolution_lifecycle", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)


class EmployerResolutionLifecycleTests(unittest.TestCase):
    def universe(self, employers):
        return {
            "schema_version": 1,
            "seed_sets": [
                {"key": "benchmark", "kind": "coverage_benchmark"},
                {"key": "state-of-ats-2026-verified-hosts", "kind": "external_ats_evidence"},
            ],
            "employers": employers,
        }

    def employer(self, employer_id, count=1, **extra):
        return {
            "id": employer_id,
            "name": employer_id.title(),
            "aliases": [],
            "seed_sets": ["benchmark"],
            "seed_metadata": {"benchmark": {
                "domain_hints": [f"careers.{employer_id}.example"],
                "evidence_count": count,
                "authoritative_evidence_count": count,
                "states": ["MD"],
            }},
            **extra,
        }

    def resolved(self, url, platform="workday", requests=1):
        return {
            "status": "resolved",
            "url": url,
            "platform": platform,
            "provider": {"status": "resolved", "family": platform},
            "evidence": [
                {"type": "http", "status": 200, "requested_url": url}
                for _ in range(requests)
            ],
        }

    def test_shared_provider_root_is_not_treated_as_fresh_success(self):
        employer = self.employer(
            "shared",
            careers_url="https://www.greenhouse.com/",
            careers_platform="greenhouse",
            provider={"status": "resolved", "family": "greenhouse"},
            careers_resolution={
                "status": "resolved",
                "resolved_at": "2026-09-17T19:00:00Z",
                "last_attempt_at": "2026-09-17T19:00:00Z",
            },
        )
        calls = []

        def resolver(entry, **kwargs):
            calls.append(entry["id"])
            return {
                "status": "unresolved",
                "url": None,
                "platform": None,
                "provider": None,
                "evidence": [{"type": "http", "status": 404, "requested_url": "https://shared.example"}],
            }

        updated, summary = mod.run_lifecycle(self.universe([employer]), now=NOW, resolver=resolver)
        self.assertEqual(calls, ["shared"])
        row = updated["employers"][0]
        self.assertNotIn("careers_url", row)
        self.assertEqual(row["careers_resolution"]["status"], "unresolved")
        self.assertEqual(summary["outcomes"], {"unresolved": 1})

    def test_default_lifecycle_budgets_are_scaled_but_bounded(self):
        self.assertEqual(mod.DEFAULT_EMPLOYER_BUDGET, 20)
        self.assertEqual(mod.DEFAULT_REQUEST_BUDGET, 120)

    def test_reuses_fresh_success_without_network_work(self):
        employer = self.employer(
            "fresh",
            careers_url="https://fresh.example/careers",
            careers_platform="workday",
            careers_resolution={
                "status": "resolved",
                "resolved_at": "2026-09-15T20:00:00Z",
                "last_attempt_at": "2026-09-15T20:00:00Z",
            },
        )
        calls = []
        updated, summary = mod.run_lifecycle(
            self.universe([employer]), now=NOW, resolver=lambda entry, **kwargs: calls.append(entry)
        )
        self.assertEqual(calls, [])
        self.assertEqual(summary["attempted_employers"], 0)
        self.assertEqual(updated["employers"][0]["careers_url"], "https://fresh.example/careers")

    def test_stale_success_is_refreshed(self):
        employer = self.employer(
            "stale",
            careers_url="https://old.example/careers",
            careers_platform="company-branded",
            careers_resolution={
                "status": "resolved",
                "resolved_at": "2026-09-01T20:00:00Z",
                "last_attempt_at": "2026-09-01T20:00:00Z",
            },
        )
        updated, summary = mod.run_lifecycle(
            self.universe([employer]),
            now=NOW,
            resolver=lambda entry, **kwargs: self.resolved("https://new.example/careers", "greenhouse"),
        )
        row = updated["employers"][0]
        self.assertEqual(row["careers_url"], "https://new.example/careers")
        self.assertEqual(row["careers_platform"], "greenhouse")
        self.assertEqual(row["careers_resolution"]["resolved_at"], "2026-09-17T20:00:00Z")
        self.assertEqual(summary["outcomes"], {"resolved": 1})

    def test_transient_failure_preserves_last_good_resolution(self):
        employer = self.employer(
            "transient",
            careers_url="https://good.example/careers",
            careers_platform="workday",
            provider={"status": "resolved", "family": "workday"},
            careers_resolution={
                "status": "resolved",
                "resolved_at": "2026-09-01T20:00:00Z",
                "last_attempt_at": "2026-09-01T20:00:00Z",
            },
        )
        failure = {
            "status": "unresolved", "url": None, "platform": None, "provider": None,
            "evidence": [{"type": "http", "status": 503, "requested_url": "https://transient.example"}],
        }
        updated, summary = mod.run_lifecycle(
            self.universe([employer]), now=NOW, resolver=lambda entry, **kwargs: failure
        )
        row = updated["employers"][0]
        self.assertEqual(row["careers_url"], "https://good.example/careers")
        self.assertEqual(row["provider"]["family"], "workday")
        self.assertEqual(row["careers_resolution"]["status"], "resolved")
        self.assertEqual(row["careers_resolution"]["attempt_status"], "transient")
        self.assertEqual(row["careers_resolution"]["resolved_at"], "2026-09-01T20:00:00Z")
        self.assertEqual(summary["outcomes"], {"transient": 1})

    def test_employer_and_request_budgets_bound_work_deterministically(self):
        universe = self.universe([
            self.employer("low", 1),
            self.employer("high", 3),
            self.employer("middle", 2),
        ])
        calls = []

        def resolver(entry, *, max_pages):
            calls.append((entry["id"], max_pages))
            return self.resolved(
                f"https://{entry['id']}.example/careers",
                requests=min(2, max_pages),
            )

        updated, summary = mod.run_lifecycle(
            universe, now=NOW, employer_budget=3, request_budget=3, resolver=resolver
        )
        self.assertEqual(calls, [("high", 3), ("middle", 1)])
        self.assertEqual(summary["attempted_employers"], 2)
        self.assertEqual(summary["requests_used"], 3)
        self.assertNotIn("careers_url", updated["employers"][0])

    def test_lifecycle_attempts_fortune_before_verified_ats_before_other(self):
        fortune = self.employer("fortune", 1)
        fortune["seed_sets"].append("fortune-500-2026")
        fortune["seed_metadata"]["fortune-500-2026"] = {
            "domain_hints": ["fortune.wd1.myworkdayjobs.com"]
        }

        ats = self.employer("ats", 50)
        ats["seed_sets"].append("state-of-ats-2026-verified-hosts")
        ats["seed_metadata"]["state-of-ats-2026-verified-hosts"] = {
            "domain_hints": ["ats.wd1.myworkdayjobs.com"]
        }

        other = self.employer("other", 100)
        universe = {
            "schema_version": 1,
            "seed_sets": [
                {"key": "benchmark", "kind": "coverage_benchmark"},
                {"key": "fortune-500-2026", "kind": "fortune_500"},
                {"key": "state-of-ats-2026-verified-hosts", "kind": "external_ats_evidence"},
            ],
            "employers": [other, ats, fortune],
        }
        calls = []

        def resolver(entry, *, max_pages):
            calls.append(entry["id"])
            return self.resolved(f"https://{entry['id']}.example/careers", requests=1)

        updated, summary = mod.run_lifecycle(
            universe,
            now=NOW,
            employer_budget=3,
            request_budget=3,
            resolver=resolver,
        )
        self.assertEqual(calls, ["fortune", "other"])
        ats_row = next(row for row in updated["employers"] if row["id"] == "ats")
        self.assertEqual(ats_row["careers_resolution"]["status"], "provider_resolved")
        self.assertEqual(summary["fast_path_provider_resolved"], 1)

    def test_verified_workday_tenant_fast_paths_without_network(self):
        employer = self.employer("verified")
        employer["seed_sets"].append("state-of-ats-2026-verified-hosts")
        employer["seed_metadata"]["state-of-ats-2026-verified-hosts"] = {
            "ats_system": "Workday",
            "domain_hints": ["verified.wd1.myworkdayjobs.com"],
            "evidence_method": "Workday tenant probe",
            "source_url": "https://example.com/verified",
        }
        calls = []

        updated, summary = mod.run_lifecycle(
            self.universe([employer]),
            now=NOW,
            resolver=lambda entry, **kwargs: calls.append(entry),
        )

        self.assertEqual(calls, [])
        row = updated["employers"][0]
        self.assertNotIn("careers_url", row)
        self.assertEqual(row["careers_platform"], "workday")
        self.assertEqual(row["provider"]["family"], "workday")
        self.assertEqual(row["careers_resolution"]["status"], "provider_resolved")
        self.assertEqual(row["careers_resolution"]["attempt_status"], "verified_seed")
        self.assertEqual(summary["fast_path_provider_resolved"], 1)
        self.assertEqual(summary["attempted_employers"], 0)
        self.assertEqual(summary["requests_used"], 0)

    def test_shared_verified_provider_host_is_not_fast_pathed(self):
        employer = {
            "id": "shared-greenhouse",
            "name": "Shared Greenhouse",
            "aliases": [],
            "seed_sets": ["state-of-ats-2026-verified-hosts"],
            "seed_metadata": {
                "state-of-ats-2026-verified-hosts": {
                    "ats_system": "Greenhouse",
                    "domain_hints": ["job-boards.greenhouse.io"],
                    "evidence_method": "vendor board API",
                    "source_url": "https://example.com/shared-greenhouse",
                }
            },
        }

        updated, summary = mod.run_lifecycle(
            self.universe([employer]),
            now=NOW,
            resolver=lambda entry, **kwargs: self.fail("shared provider root should not be network-resolved"),
        )

        row = updated["employers"][0]
        self.assertNotIn("provider", row)
        self.assertNotIn("careers_resolution", row)
        self.assertEqual(summary["fast_path_provider_resolved"], 0)
        self.assertEqual(summary["attempted_employers"], 0)


    def test_fresh_workday_provider_resolution_is_completed_and_preserved_on_failure(self):
        employer = self.employer(
            "workday-known",
            careers_platform="workday",
            provider={"status": "resolved", "family": "workday", "host": "workday-known.wd1.myworkdayjobs.com"},
            careers_resolution={
                "status": "provider_resolved",
                "attempt_status": "verified_seed",
                "resolved_at": "2026-09-17T19:00:00Z",
                "last_attempt_at": "2026-09-17T19:00:00Z",
            },
        )
        calls = []

        def resolver(entry, **kwargs):
            calls.append(entry["id"])
            return {
                "status": "unresolved",
                "url": None,
                "platform": None,
                "provider": None,
                "evidence": [{"type": "http", "status": 404, "requested_url": "https://workday-known.wd1.myworkdayjobs.com/careers"}],
            }

        updated, summary = mod.run_lifecycle(self.universe([employer]), now=NOW, resolver=resolver)
        self.assertEqual(calls, ["workday-known"])
        row = updated["employers"][0]
        self.assertEqual(row["provider"]["family"], "workday")
        self.assertEqual(row["careers_resolution"]["status"], "provider_resolved")
        self.assertEqual(row["careers_resolution"]["attempt_status"], "unresolved")
        self.assertEqual(summary["attempted_employers"], 1)

    def test_fresh_nonworkday_provider_resolution_stays_network_free(self):
        employer = self.employer(
            "eightfold-known",
            careers_platform="eightfold",
            provider={"status": "resolved", "family": "eightfold", "host": "eightfold-known.eightfold.ai"},
            careers_resolution={
                "status": "provider_resolved",
                "attempt_status": "verified_seed",
                "resolved_at": "2026-09-17T19:00:00Z",
                "last_attempt_at": "2026-09-17T19:00:00Z",
            },
        )
        calls = []
        updated, summary = mod.run_lifecycle(
            self.universe([employer]),
            now=NOW,
            resolver=lambda entry, **kwargs: calls.append(entry),
        )
        self.assertEqual(calls, [])
        self.assertEqual(updated["employers"][0]["careers_resolution"]["status"], "provider_resolved")
        self.assertEqual(summary["attempted_employers"], 0)

    def test_resolution_preserves_seed_provenance_and_reports_provider_distribution(self):
        employer = self.employer("acme", 2)
        original_metadata = employer["seed_metadata"]
        updated, summary = mod.run_lifecycle(
            self.universe([employer]),
            now=NOW,
            resolver=lambda entry, **kwargs: self.resolved("https://acme.example/careers", "icims"),
        )
        row = updated["employers"][0]
        self.assertEqual(row["seed_metadata"], original_metadata)
        self.assertEqual(row["seed_sets"], ["benchmark"])
        self.assertEqual(summary["resolved_provider_families"], {"icims": 1})


if __name__ == "__main__":
    unittest.main()
