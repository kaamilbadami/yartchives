import unittest

from scripts.coverage_gap_candidates import build_gap_candidates


class CoverageGapCandidatesTests(unittest.TestCase):
    def employer(self, idx, family=None, *, resolved=False):
        hints = []
        if family == "workday":
            hints = [f"https://tenant{idx}.myworkdayjobs.com/jobs"]
        elif family == "greenhouse":
            hints = [f"https://boards.greenhouse.io/company{idx}"]
        elif family == "oracle":
            hints = [f"https://company{idx}.fa.us2.oraclecloud.com/hcmUI/CandidateExperience"]
        elif family == "unknown":
            hints = [f"https://careers{idx}.example.com"]
        return {
            "id": f"employer-{idx}",
            "name": f"Employer {idx}",
            "seed_sets": ["fortune-500-2026"],
            "provider": (
                {"status": "resolved", "family": family or "custom_unknown"}
                if resolved
                else {"status": "unresolved", "family": "custom_unknown"}
            ),
            "seed_metadata": {"benchmark": {"domain_hints": hints}},
        }

    def test_checks_root_domain_hints_for_families(self):
        employer = self.employer(1, "workday")
        employer["domain_hints"] = employer["seed_metadata"]["benchmark"]["domain_hints"]
        employer["seed_metadata"] = {}

        employer2 = self.employer(2, "greenhouse")
        employer2["domain_hints"] = employer2["seed_metadata"]["benchmark"]["domain_hints"]
        employer2["seed_metadata"] = {}

        universe = {
            "employers": [
                employer,
                *[self.employer(i, "workday") for i in range(2, 7)],
                employer2,
                *[self.employer(i + 20, "greenhouse") for i in range(3, 7)],
            ]
        }

        candidates = build_gap_candidates(universe)

        self.assertEqual(
            [candidate["id"] for candidate in candidates],
            [
                "ats-workday:provider-resolution",
                "ats-greenhouse:provider-resolution",
            ],
        )

    def test_emits_independent_ats_family_candidates(self):
        universe = {
            "employers": [
                *[self.employer(i, "workday") for i in range(1, 7)],
                *[self.employer(i + 20, "greenhouse") for i in range(1, 6)],
            ]
        }

        candidates = build_gap_candidates(universe)

        self.assertEqual(
            [candidate["id"] for candidate in candidates],
            [
                "ats-workday:provider-resolution",
                "ats-greenhouse:provider-resolution",
            ],
        )
        self.assertEqual(candidates[0]["resources"], ["ats-workday"])
        self.assertEqual(candidates[1]["resources"], ["ats-greenhouse"])

    def test_emits_single_known_family_gap_and_ignores_resolved(self):
        universe = {
            "employers": [
                self.employer(1, "oracle"),
                *[self.employer(i + 10, "workday", resolved=True) for i in range(1, 8)],
            ]
        }

        candidates = build_gap_candidates(universe)

        self.assertEqual(
            [candidate["id"] for candidate in candidates],
            ["ats-oracle:provider-resolution"],
        )
        self.assertEqual(candidates[0]["affected_employers"], 1)

    def test_includes_cs_benchmark_even_when_fortune_500_exists(self):
        fortune = self.employer(1, "workday")
        cs = self.employer(2, "greenhouse")
        cs["seed_sets"] = ["cs-benchmark"]

        candidates = build_gap_candidates({"employers": [fortune, cs]})

        self.assertEqual(
            {candidate["id"] for candidate in candidates},
            {
                "ats-workday:provider-resolution",
                "ats-greenhouse:provider-resolution",
            },
        )

    def test_unknown_provider_gap_uses_shared_registry_resource(self):
        universe = {
            "employers": [self.employer(i, "unknown") for i in range(1, 11)]
        }

        candidates = build_gap_candidates(universe)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["id"],
            "source-registry:unknown-provider-resolution",
        )
        self.assertEqual(candidates[0]["resources"], ["source-registry"])


if __name__ == "__main__":
    unittest.main()
