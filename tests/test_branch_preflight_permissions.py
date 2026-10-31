"""Ensure branch-push CI never runs untrusted test code with write tokens."""
from pathlib import Path
import unittest

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github/workflows/branch-preflight.yml").read_text()


class BranchPreflightPermissionsTests(unittest.TestCase):
    def test_untrusted_branch_test_job_is_read_only(self):
        header, jobs = WORKFLOW.split("jobs:", 1)
        self.assertIn("  contents: read", header)
        self.assertNotIn("  actions: write", header)
        self.assertNotIn("  pull-requests: write", header)
        tests = jobs.split("  tests:", 1)[1]
        self.assertNotIn("permissions:", tests)
        self.assertNotIn("secrets.", tests)
        self.assertIn("bash scripts/run_quality_checks.sh all", tests)

    def test_trusted_publisher_follows_successful_branch_check(self):
        self.assertNotIn("  publish-pr:", WORKFLOW)
        publisher = (Path(__file__).resolve().parents[1] / ".github/workflows/publish-validated-agent-pr.yml").read_text()
        for expected in ("workflow_run:", "- Branch preflight", "pull-requests: write", "github.event.workflow_run.event == 'push'", '[[ "$current_sha" != "$VALIDATED_SHA" ]]'):
            self.assertIn(expected, publisher)
        self.assertNotIn("actions/checkout", publisher)


if __name__ == "__main__":
    unittest.main()
