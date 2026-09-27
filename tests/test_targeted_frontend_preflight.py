import unittest

from scripts.targeted_frontend_preflight import (
    ALL_FRONTEND_TESTS,
    plan_for_paths,
)


class TargetedFrontendPreflightTests(unittest.TestCase):
    def test_ui_change_runs_only_ui_contract(self):
        plan = plan_for_paths(["apply-next-ui.js"])
        self.assertEqual(plan["syntax_checks"], ["apply-next-ui.js"])
        self.assertEqual(plan["tests"], ["tests/apply-next-ui.test.cjs"])

    def test_location_change_runs_downstream_ranking_and_ui_contracts(self):
        plan = plan_for_paths(["apply-next-location.js"])
        self.assertIn("tests/apply-next-location.test.cjs", plan["tests"])
        self.assertIn("tests/apply-next-dimensions.test.cjs", plan["tests"])
        self.assertIn("tests/apply-next-presentation.test.cjs", plan["tests"])
        self.assertIn("tests/apply-next-ui.test.cjs", plan["tests"])
        self.assertNotIn("tests/analytics.test.cjs", plan["tests"])

    def test_dimensions_change_is_syntax_checked_and_has_direct_regression_test(self):
        plan = plan_for_paths(["apply-next-dimensions.js"])
        self.assertEqual(plan["syntax_checks"], ["apply-next-dimensions.js"])
        self.assertIn("tests/apply-next-dimensions.test.cjs", plan["tests"])

    def test_changed_cjs_test_runs_itself(self):
        plan = plan_for_paths(["tests/apply-next-ui.test.cjs"])
        self.assertEqual(plan["syntax_checks"], [])
        self.assertEqual(plan["tests"], ["tests/apply-next-ui.test.cjs"])

    def test_known_static_asset_change_is_bounded(self):
        plan = plan_for_paths(["index.html"])
        self.assertEqual(
            plan["tests"],
            ["tests/apply-next-ui.test.cjs", "tests/deploy-assets.test.cjs"],
        )

    def test_unknown_root_frontend_file_falls_back_to_full_frontend_tests(self):
        plan = plan_for_paths(["new-widget.js"])
        self.assertEqual(plan["syntax_checks"], ["new-widget.js"])
        self.assertEqual(plan["tests"], sorted(ALL_FRONTEND_TESTS))

    def test_non_frontend_change_is_noop(self):
        plan = plan_for_paths(["README.md", "scripts/build_feed.py"])
        self.assertEqual(plan, {"syntax_checks": [], "tests": []})

    def test_multiple_paths_deduplicate_shared_downstream_tests(self):
        plan = plan_for_paths(["apply-next-location.js", "apply-next-dimensions.js"])
        self.assertEqual(
            plan["tests"].count("tests/apply-next-ui.test.cjs"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
