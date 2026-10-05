from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAST_WORKFLOW = ROOT / ".github" / "workflows" / "update-feed-fast.yml"
FULL_WORKFLOW = ROOT / ".github" / "workflows" / "update-feed.yml"
FRESHNESS_WORKFLOW = ROOT / ".github" / "workflows" / "feed-freshness.yml"


class FastFeedWorkflowTests(unittest.TestCase):
    def test_fast_path_is_bounded_and_publishes_validated_artifact(self):
        text = FAST_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "47 * * * *"', text)
        self.assertIn("timeout-minutes: 15", text)
        self.assertIn("python scripts/build_feed.py", text)
        self.assertIn("python scripts/enrich_feed.py data/listings.json", text)
        self.assertIn("python scripts/repair_links.py data/listings.json", text)
        self.assertIn("--offline", text)
        self.assertIn("python scripts/reconcile_workday_duplicates.py", text)
        self.assertIn("python scripts/stabilize_job_ids.py", text)
        validate = text.index("- name: Validate fast-path feed")
        publish = text.index("- name: Publish fast-path feed artifact")
        self.assertLess(validate, publish)
        self.assertIn("name: yartchives-listings-fast", text[publish:])
        self.assertIn("if-no-files-found: error", text[publish:])

    def test_fast_path_excludes_slow_enrichment_and_gap_fillers(self):
        text = FAST_WORKFLOW.read_text(encoding="utf-8")
        for forbidden in (
            "employer_resolution_lifecycle.py",
            "parallel_ats_collect.py",
            "enrich_ai_profiles.py",
            "provider_links.py",
            "jobright_links.py",
            "source_links.py",
            "coverage_audit.py",
        ):
            self.assertNotIn(forbidden, text)

    def test_rich_pipeline_remains_intact_for_quality(self):
        text = FULL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("parallel_ats_collect.py", text)
        self.assertIn("enrich_ai_profiles.py", text)
        self.assertIn("provider_links.py", text)
        self.assertIn("coverage_audit.py", text)
        self.assertIn("name: yartchives-listings", text)

    def test_watchdog_is_offset_and_fast_path_is_recovery_target(self):
        text = FRESHNESS_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "7 * * * *"', text)
        watchdog = (ROOT / "scripts" / "watchdog_feed_freshness.py").read_text(encoding="utf-8")
        self.assertIn('default="update-feed-fast.yml"', watchdog)


if __name__ == "__main__":
    unittest.main()
