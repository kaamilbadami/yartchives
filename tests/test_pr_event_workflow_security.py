"""Security boundaries for workflows triggered by pull request events."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class TrustedPrEventWorkflowTests(unittest.TestCase):
    def test_dispatch_never_checks_out_untrusted_pr_head(self):
        workflow = (WORKFLOWS / "autonomous-dispatch.yml").read_text()
        self.assertIn("  pull_request:", workflow)
        self.assertIn("ref: main # Never execute PR-head code", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("github.event.pull_request.head.sha", workflow)

    def test_housekeeping_uses_main_and_limits_branch_cleanup(self):
        workflow = (WORKFLOWS / "repository-housekeeping.yml").read_text()
        cleanup = workflow.split("  reconcile-stale-branches:", 1)[1].split("  reconcile-merged-pr-issues:", 1)[0]
        reconcile = workflow.split("  reconcile-merged-pr-issues:", 1)[1]
        self.assertIn("if: github.event_name != 'pull_request'", cleanup)
        self.assertIn("github.event.pull_request.merged == true", reconcile)
        self.assertIn("ref: main # Only run trusted reconciliation code", reconcile)
        self.assertIn("persist-credentials: false", reconcile)
        self.assertNotIn("github.event.pull_request.head.sha", reconcile)


if __name__ == "__main__":
    unittest.main()
