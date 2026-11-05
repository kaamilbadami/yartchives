"""Regression tests for risk tiers; never conflate classification with approval."""
import unittest

from scripts.merge_risk_policy import classify_merge_risk


def changed(path, status="modified", **kwargs):
    return {"filename": path, "status": status, **kwargs}


class MergeRiskPolicyTests(unittest.TestCase):
    def test_ordinary_product_and_ats_work(self):
        self.assertEqual(classify_merge_risk([
            changed("tests/test_dispatch_copilot_pilot.py"),
            changed("scripts/build_feed.py"), changed("data/sources.json"),
        ]), (1, "ordinary change"))

    def test_small_nonprivileged_automation_is_level_two(self):
        self.assertEqual(classify_merge_risk([
            changed("scripts/queue_coverage_gap.py"),
            changed("tests/test_queue_coverage_gap.py"),
        ]), (2, "routine automation"))

    def test_workflow_merge_authority_secrets_and_dispatch_code_level_three(self):
        for path in (
            ".github/workflows/autonomous-dispatch.yml",
            ".github/workflows/quality.yml",
            ".github/CODEOWNERS",
            "scripts/auto_merge_agent_prs.py",
            "scripts/merge_risk_policy.py",
            "scripts/dispatch_copilot_pilot.py",
            "requirements.txt",
            "scripts/unknown_new_automation.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(classify_merge_risk([changed(path)])[0], 3)

    def test_mixed_scope_escalates_to_strictest(self):
        self.assertEqual(classify_merge_risk([
            changed("docs/readme.md"),
            changed("scripts/queue_coverage_gap.py"),
            changed(".github/workflows/quality.yml"),
        ])[0], 3)

    def test_unknown_rename_and_missing_evidence_fail_closed(self):
        for files in (
            [], [{}], [changed("docs/a.md", "renamed", previous_filename="docs/b.md")],
            [changed("../unsafe.py")], [changed("docs/a.md", "mystery")],
        ):
            with self.subTest(files=files):
                self.assertEqual(classify_merge_risk(files)[0], 3)


if __name__ == "__main__":
    unittest.main()
