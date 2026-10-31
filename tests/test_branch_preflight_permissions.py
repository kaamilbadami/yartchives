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
        tests = jobs.split("  tests:", 1)[1].split("  publish-pr:", 1)[0]
        self.assertNotIn("permissions:", tests)
        self.assertNotIn("secrets.", tests)
        self.assertIn("bash scripts/run_quality_checks.sh all", tests)

    def test_privileged_publication_runs_only_after_success(self):
        publish = WORKFLOW.split("  publish-pr:", 1)[1]
        self.assertIn("needs.tests.result == 'success'", publish)
        self.assertIn("actions: write", publish)
        self.assertIn("pull-requests: write", publish)
        self.assertIn("persist-credentials: false", publish)
        self.assertNotIn("bash scripts/run_quality_checks.sh", publish)


if __name__ == "__main__":
    unittest.main()
