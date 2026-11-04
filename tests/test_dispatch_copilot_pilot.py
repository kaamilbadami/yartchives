"""Safety and API-contract tests for the opt-in Copilot pilot dispatcher."""
import unittest
from unittest import mock

from scripts import dispatch_copilot_pilot as mod
from scripts import dispatch_autonomous_issues as jules

REPO = "kaamilbadami/yartchives"


def issue(number=900, *, extra=(), assignees=(), state="open", body=None):
    return {
        "number": number, "state": state, "title": "Test a real regression",
        "body": body or "priority: P2\narea: regression\nresources: test-pilot\nautonomous: true",
        "labels": [{"name": label} for label in (
            "agent-ready", "autonomous-backlog", mod.PILOT_LABEL, *extra)],
        "assignees": [{"login": name} for name in assignees],
    }


class CopilotPilotDispatcherTests(unittest.TestCase):
    def test_missing_user_token_never_calls_api(self):
        api = mock.Mock(side_effect=AssertionError("must not make calls"))
        self.assertIn("disabled", mod.run_cycle(REPO, "", api=api))
        api.assert_not_called()

    def test_pilot_is_excluded_from_jules_selection(self):
        self.assertEqual(jules.select_tasks([issue()]), [])

    def test_non_pilot_issue_never_assigned(self):
        item = issue()
        item["labels"] = [x for x in item["labels"] if x["name"] != mod.PILOT_LABEL]
        api = mock.Mock(side_effect=[[item], []])
        self.assertIn("no authorized", mod.run_cycle(REPO, "user-token", api=api))

    def test_one_authorized_issue_assigned_with_user_token(self):
        item = issue()
        posts = []
        def api(path, *, method="GET", payload=None, token=None):
            if method == "POST":
                posts.append((path, payload, token))
                if path.endswith("/assignees"):
                    return {"assignees": [{"login": "Copilot"}]}
                return {"id": 1}
            if path.endswith("/issues?state=open&per_page=100"):
                return [item]
            if path.endswith("/pulls?state=open&per_page=100"):
                return []
            if path.endswith("/comments?per_page=100"):
                return []
            if path.endswith("/issues/900"):
                return item
            raise AssertionError(path)
        self.assertIn("assigned Copilot", mod.run_cycle(REPO, "user-token", api=api))
        self.assertEqual(len(posts), 2)
        self.assertIn(mod.ATTEMPT_MARKER, posts[0][1]["body"])
        self.assertIsNone(posts[0][2])
        self.assertEqual(posts[1][2], "user-token")
        self.assertEqual(posts[1][1]["assignees"], ["copilot-swe-agent[bot]"])
        self.assertEqual(posts[1][1]["agent_assignment"]["base_branch"], "main")

    def test_durable_marker_prevents_retry_after_ambiguous_failure(self):
        item = issue()
        posts = []
        comments = []
        def api(path, *, method="GET", payload=None, token=None):
            if method == "POST" and path.endswith("/comments"):
                posts.append(path)
                comments.append({"body": payload["body"]})
                return {"id": 1}
            if method == "POST" and path.endswith("/assignees"):
                posts.append(path)
                raise RuntimeError("network timeout after request")
            if path.endswith("/issues?state=open&per_page=100"):
                return [item]
            if path.endswith("/pulls?state=open&per_page=100"):
                return []
            if path.endswith("/comments?per_page=100"):
                return comments
            if path.endswith("/issues/900"):
                return item
            raise AssertionError(path)
        with self.assertRaisesRegex(RuntimeError, "network timeout"):
            mod.run_cycle(REPO, "user-token", api=api)
        self.assertIn("already attempted", mod.run_cycle(REPO, "user-token", api=api))
        self.assertEqual(len(posts), 2)

    def test_prior_attempted_pilot_blocks_new_assignment(self):
        attempted = issue(900)
        candidate = issue(901)
        def api(path, *, method="GET", payload=None, token=None):
            if method == "POST":
                raise AssertionError("should not attempt new assignment")
            if path.endswith("/issues?state=open&per_page=100"):
                return [attempted, candidate]
            if path.endswith("/pulls?state=open&per_page=100"):
                return []
            if path.endswith("/issues/900/comments?per_page=100"):
                return [{"body": "note\n" + mod.ATTEMPT_MARKER}]
            raise AssertionError(path)
        self.assertIn("already attempted", mod.run_cycle(REPO, "user-token", api=api))

    def test_existing_pr_or_owner_assignee_blocks_assignment(self):
        item = issue()
        for option in ("pr", "assigned"):
            with self.subTest(option=option):
                candidate = issue(assignees=("kaamilbadami",)) if option == "assigned" else item
                def api(path, *, method="GET", payload=None, token=None):
                    if path.endswith("/issues?state=open&per_page=100"):
                        return [candidate]
                    if path.endswith("/pulls?state=open&per_page=100"):
                        return [{"body": "Closes #900"}] if option == "pr" else []
                    if path.endswith("/comments?per_page=100"):
                        return []
                    raise AssertionError("Unexpected read/write: " + path)
                self.assertIn("no authorized", mod.run_cycle(REPO, "user-token", api=api))

    def test_existing_jules_resource_lock_and_blocking_labels(self):
        active = issue(901, extra=(jules.JULES_ACTIVE_LABEL,))
        candidate = issue()
        def api(path, *, method="GET", payload=None, token=None):
            if path.endswith("/issues?state=open&per_page=100"):
                return [active, candidate]
            if path.endswith("/pulls?state=open&per_page=100"):
                return []
            if path.endswith("/comments?per_page=100"):
                return []
            raise AssertionError(path)
        self.assertIn("no authorized", mod.run_cycle(REPO, "user-token", api=api))
        self.assertFalse(mod.issue_is_eligible(
            issue(extra=("initiative",)), set(), set()))
        self.assertFalse(mod.issue_is_eligible(
            issue(extra=("blocked",)), set(), set()))

    def test_missing_dependencies_and_unexpected_response_fail_closed(self):
        item = issue(body="priority: P2\narea: regression\nresources: test-pilot\n"
                          "autonomous: true\ndepends_on: #901")
        self.assertFalse(mod.issue_is_eligible(item, {901}, set()))
        with self.assertRaises(ValueError):
            mod.run_cycle(REPO, "user-token", api=lambda *a, **k: {"error": "invalid"})


if __name__ == "__main__":
    unittest.main()
