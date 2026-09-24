from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "refresh-inspections.yml"


class RefreshInspectionsWorkflowTests(unittest.TestCase):
    def test_workflow_exists(self):
        self.assertTrue(WORKFLOW.exists())

    def test_runtime_state_is_hydrated_before_bounded_refresh(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        hydrate = text.index("- name: Hydrate latest runtime artifacts")
        migrate = text.index("- name: Migrate cached requirement semantics")
        refresh = text.index("- name: Refresh bounded posting inspections")
        self.assertLess(hydrate, migrate)
        self.assertLess(migrate, refresh)
        self.assertIn("scripts/download_latest_feed.py", text[hydrate:migrate])

    def test_inspections_are_published_as_artifact_not_committed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        publish = text.index("- name: Publish bounded inspections artifact")
        block = text[publish:]
        self.assertIn("actions/upload-artifact@", block)
        self.assertIn("name: yartchives-inspections", block)
        self.assertIn("path: data/workday-inspections.json", block)
        self.assertNotIn("- name: Commit inspections", text)
        self.assertNotIn('git commit -m "chore: refresh bounded inspections"', text)
        self.assertNotIn("git push origin main", text)


if __name__ == "__main__":
    unittest.main()
