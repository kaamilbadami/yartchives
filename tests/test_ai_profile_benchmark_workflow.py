from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ai-profile-benchmark.yml"


class AiProfileBenchmarkWorkflowTests(unittest.TestCase):
    def test_workflow_is_manual_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("\n  schedule:", text)
        self.assertNotIn("\n  push:", text)
        self.assertNotIn("\n  pull_request:", text)

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
