from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "update-feed.yml"


class UpdateFeedWorkflowTests(unittest.TestCase):
    def test_employer_universe_is_persisted_immediately_after_resolution(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        resolver = text.index("- name: Refresh bounded employer careers resolutions")
        persist = text.index("- name: Persist employer universe before long feed build")
        snapshot = text.index("- name: Snapshot existing final feed")

        self.assertLess(resolver, persist)
        self.assertLess(persist, snapshot)
        self.assertIn('git add employer_universe.json', text[persist:snapshot])
        self.assertIn('git push origin HEAD:main', text[persist:snapshot])

    def test_final_generated_commit_does_not_rebundle_employer_universe(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        final_commit = text.index("- name: Commit updated feed and inspections")
        tail = text[final_commit:]

        self.assertIn(
            'GENERATED_PATHS="data/listings.json data/workday-inspections.json"',
            tail,
        )
        self.assertNotIn(
            'GENERATED_PATHS="data/listings.json data/workday-inspections.json employer_universe.json"',
            tail,
        )
        self.assertNotIn("yartchives-generated-employer-universe", tail)


if __name__ == "__main__":
    unittest.main()
