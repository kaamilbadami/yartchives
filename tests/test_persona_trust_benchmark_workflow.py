from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "persona-trust-benchmark.yml"
SCRIPT = ROOT / "scripts" / "persona_external_discovery.py"


class PersonaTrustBenchmarkWorkflowTests(unittest.TestCase):
    def test_workflow_runs_full_measurement_loop(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("schedule:", text)
        self.assertIn("external_discovery_benchmark.py", text)
        self.assertIn("persona_external_discovery.py", text)
        self.assertIn("coverage_audit.py", text)
        self.assertIn("persona-frozen-benchmark.json", text)
        self.assertIn("persona-miss-report.md", text)

    def test_workflow_uses_existing_azure_secrets_and_never_commits(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("secrets.AZURE_OPENAI_API_KEY", text)
        self.assertIn("secrets.AZURE_OPENAI_ENDPOINT", text)
        self.assertIn("secrets.AZURE_OPENAI_DEPLOYMENT", text)
        self.assertNotIn("git commit", text)
        self.assertNotIn("git push", text)

    def test_discovery_agent_requires_web_search_and_authoritative_urls(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('{"type": "web_search"}', text)
        self.assertIn('"web_search_call"', text)
        self.assertIn("DISCOVERY_HOSTS", text)
        self.assertIn("_validate_authoritative_url", text)
        self.assertIn("Do not use or infer anything from the Yartchives feed", text)


if __name__ == "__main__":
    unittest.main()
