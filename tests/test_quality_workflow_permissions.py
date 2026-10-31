"""Regression guards for least-privilege Copilot PR validation."""
from pathlib import Path
import re
import unittest

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github/workflows/quality.yml").read_text()


def job_section(name):
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", WORKFLOW)
    assert match, f"Missing job: {name}"
    return match.group(1)


class QualityWorkflowPermissionsTests(unittest.TestCase):
    def test_default_token_is_read_only(self):
        self.assertRegex(WORKFLOW, r"(?m)^permissions:\n  contents: read$")
        self.assertNotRegex(WORKFLOW.split("jobs:", 1)[0], r"(?m)^  (actions|statuses|pull-requests): write$")

    def test_untrusted_jobs_cannot_write(self):
        for name in ("targeted-frontend-preflight", "tests"):
            with self.subTest(job=name):
                section = job_section(name)
                self.assertNotIn("permissions:", section)
                self.assertNotIn("secrets.", section)
                self.assertNotIn("github.token", section)
        self.assertIn("run: bash scripts/run_quality_checks.sh python", job_section("tests"))

    def test_status_publication_is_separate_trusted_job(self):
        section = job_section("publish-pr-recovery-status")
        self.assertIn("needs: [tests]", section)
        self.assertIn("github.event_name == 'workflow_dispatch'", section)
        self.assertIn("inputs.pr_recovery == true", section)
        self.assertIn("needs.tests.result == 'success'", section)
        self.assertIn("statuses: write", section)
        self.assertIn("context=tests", section)
        self.assertNotIn("actions/checkout", section)

    def test_write_capable_automerge_wakeup_not_run_for_prs(self):
        section = job_section("wake-automerge")
        self.assertIn("actions: write", section)
        self.assertIn("github.event_name == 'workflow_dispatch'", section)
        self.assertIn("github.ref == 'refs/heads/main'", section)
        self.assertNotIn("github.event_name == 'pull_request'", section)
        self.assertNotIn("actions/checkout", section)


if __name__ == "__main__":
    unittest.main()
