import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "guard_jules_redispatch.py"
SPEC = importlib.util.spec_from_file_location("guard_jules_redispatch", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


def issue(*, labels=(), state="open", autonomous=True):
    body = "<!-- autonomous-task -->\npriority: P1\narea: feed\nautonomous: true\n" if autonomous else ""
    return {
        "number": 152,
        "state": state,
        "body": body,
        "labels": [{"name": label} for label in labels],
    }


class JulesRedispatchGuardTests(unittest.TestCase):
    def test_completed_attempt_without_lifecycle_label_is_blocked(self):
        comments = [
            {
                "body": (
                    "Jules completed session `9525680641951949874` and released this automation slot.\n\n"
                    "Pull request: https://github.com/kaamilbadami/yartchives/pull/163"
                )
            }
        ]

        self.assertEqual(
            mod.should_restore_review_ready(issue(), comments),
            (
                "9525680641951949874",
                "https://github.com/kaamilbadami/yartchives/pull/163",
            ),
        )

    def test_active_second_attempt_is_not_disturbed(self):
        comments = [
            {
                "body": (
                    "Jules completed session `first` and released this automation slot.\n\n"
                    "Pull request: https://github.com/kaamilbadami/yartchives/pull/163"
                )
            }
        ]

        self.assertIsNone(
            mod.should_restore_review_ready(
                issue(labels=("jules", "jules-session")),
                comments,
            )
        )

    def test_existing_terminal_or_blocking_states_are_left_alone(self):
        comments = [
            {
                "body": (
                    "Jules completed session `first`.\n\n"
                    "Pull request: https://github.com/kaamilbadami/yartchives/pull/163"
                )
            }
        ]
        for label in (
            "jules-review-ready",
            "jules-failed",
            "jules-needs-feedback",
            "blocked",
            "needs-product-decision",
        ):
            with self.subTest(label=label):
                self.assertIsNone(
                    mod.should_restore_review_ready(issue(labels=(label,)), comments)
                )

    def test_non_autonomous_or_closed_issue_is_not_guarded(self):
        comments = [
            {
                "body": (
                    "Jules completed session `first`.\n\n"
                    "Pull request: https://github.com/kaamilbadami/yartchives/pull/163"
                )
            }
        ]

        self.assertIsNone(
            mod.should_restore_review_ready(issue(autonomous=False), comments)
        )
        self.assertIsNone(
            mod.should_restore_review_ready(issue(state="closed"), comments)
        )

    def test_completion_without_pull_request_is_not_enough(self):
        comments = [{"body": "Jules completed session `first` and released this automation slot."}]
        self.assertIsNone(mod.should_restore_review_ready(issue(), comments))


if __name__ == "__main__":
    unittest.main()
