"""Contracts for safe required-status recovery on synthetic PR merge commits."""
from pathlib import Path
import unittest

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github/workflows/quality.yml").read_text()


class MergeRecoveryTests(unittest.TestCase):
    def test_exact_merge_sha_is_tested(self):
        self.assertIn("pr_number:", WORKFLOW)
        self.assertIn("steps.merge_target.outputs.merge_sha || github.ref", WORKFLOW)
        self.assertIn("tested_merge_sha:", WORKFLOW)
        self.assertIn('[[ "$PR_NUMBER" =~ ^[1-9][0-9]*$ ]]', WORKFLOW)

    def test_untrusted_tests_are_read_only(self):
        header, jobs = WORKFLOW.split("jobs:", 1)
        self.assertIn("contents: read", header)
        tests = jobs.split("  tests:", 1)[1].split("  publish-pr-recovery-status:", 1)[0]
        self.assertNotIn("statuses: write", tests)
        self.assertNotIn("actions: write", tests)
        self.assertNotIn("secrets.", tests)

    def test_success_status_revalidates_same_merge_sha(self):
        publish = WORKFLOW.split("  publish-pr-recovery-status:", 1)[1].split("  live-source-smoke:", 1)[0]
        self.assertIn("needs.tests.result == 'success'", publish)
        self.assertIn('"$target" == "$TESTED_MERGE_SHA"', publish)
        self.assertIn("statuses: write", publish)
        self.assertNotIn("actions/checkout", publish)


if __name__ == "__main__":
    unittest.main()
