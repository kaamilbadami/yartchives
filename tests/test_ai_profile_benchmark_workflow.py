from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ai-profile-benchmark.yml"


class AiProfileBenchmarkWorkflowTests(unittest.TestCase):
    def test_workflow_has_only_manual_or_authorized_issue_comment_triggers(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("issue_comment:", text)
        self.assertIn("types:\n      - created", text)
        self.assertNotIn("\n  schedule:", text)
        self.assertNotIn("\n  push:", text)
        self.assertNotIn("\n  pull_request:", text)


    def test_issue_comment_runs_use_comment_specific_concurrency(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event.comment.id", text)
        self.assertIn("github.event_name == 'issue_comment'", text)
        self.assertIn("cancel-in-progress: true", text)

    def test_issue_comment_trigger_is_tightly_authorized(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event.issue.number == 737", text)
        self.assertIn("github.event.comment.body == '/run-ai-profile-benchmark'", text)
        self.assertIn("github.event.comment.user.login == github.repository_owner", text)
        self.assertIn("github.event_name == 'workflow_dispatch' ||", text)

    def test_comment_trigger_uses_bounded_defaults(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("gemini-3.5-flash-lite", text)
        self.assertIn("GENERAL_LIMIT:", text)
        self.assertIn("'200'", text)
        self.assertIn("REFERENCE_LIMIT:", text)
        self.assertIn("'300'", text)

    def test_workflow_requires_secret_and_never_commits(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("secrets.GEMINI_API_KEY", text)
        self.assertIn("scripts/ai_profile_benchmark.py", text)
        self.assertIn("actions/upload-artifact@", text)
        self.assertNotIn("git commit", text)
        self.assertNotIn("git push", text)

    def test_workflow_hydrates_latest_runtime_feed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/download_latest_feed.py", text)
        self.assertIn("--repo", text)


if __name__ == "__main__":
    unittest.main()
