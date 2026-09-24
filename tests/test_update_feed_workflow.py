from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "update-feed.yml"


class UpdateFeedWorkflowTests(unittest.TestCase):
    def test_employer_universe_is_still_persisted_before_long_feed_build(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        resolver = text.index("- name: Refresh bounded employer careers resolutions")
        persist = text.index("- name: Persist employer universe before long feed build")
        snapshot = text.index("- name: Snapshot existing final feed")
        self.assertLess(resolver, persist)
        self.assertLess(persist, snapshot)
        self.assertIn("git add employer_universe.json", text[persist:snapshot])

    def test_runtime_state_is_hydrated_before_feed_snapshot(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        hydrate = text.index("- name: Hydrate latest runtime artifacts")
        snapshot = text.index("- name: Snapshot existing final feed")
        self.assertLess(hydrate, snapshot)
        self.assertIn("scripts/download_latest_feed.py", text[hydrate:snapshot])

    def test_validated_feed_is_published_as_artifact_before_slow_audits(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        validate = text.index("- name: Validate generated feed")
        publish = text.index("- name: Publish validated feed artifact")
        audit = text.index("- name: Print coverage audit")
        self.assertLess(validate, publish)
        self.assertLess(publish, audit)
        block = text[publish:audit]
        self.assertIn("actions/upload-artifact@", block)
        self.assertIn("name: yartchives-listings", block)
        self.assertIn("path: data/listings.json", block)
        self.assertIn("if-no-files-found: error", block)

    def test_runtime_feed_no_longer_uses_git_as_publication_transport(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("- name: Commit fast-path opportunity feed", text)
        self.assertNotIn('git add data/listings.json', text)
        self.assertNotIn('git commit -m "chore: refresh opportunity feed"', text)

    def test_workflow_does_not_run_full_test_suite(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("python -m unittest discover", text)
        self.assertNotIn(".test.cjs", text)
        self.assertIn("node --check apply-next", text)
        self.assertIn("python -m py_compile", text)
        self.assertIn("scripts/download_latest_feed.py", text)

    def test_metric_stage_names_with_spaces_are_shell_quoted(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn('--record \\"', text)
        self.assertIn('--record "link repair" -- python scripts/repair_links.py', text)
        self.assertIn('--record "ATS reconciliation" -- python scripts/reconcile_workday_duplicates.py', text)


if __name__ == "__main__":
    unittest.main()
