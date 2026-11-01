"""Behavioral regressions for parent-initiative isolation (issue #1135)."""
import json
import unittest
from unittest import mock

from scripts import auto_merge_agent_prs as merger
from scripts import dispatch_autonomous_issues as dispatch
from scripts import guard_jules_redispatch as guard
from scripts import reconcile_merged_pr_issues as reconciler


def issue(number=42, labels=("initiative", "agent-ready", "autonomous-backlog"), *, state="open"):
    return {
        "number": number,
        "title": "Parent initiative",
        "body": "<!-- autonomous-task -->\npriority: P0\narea: automation\nautonomous: true",
        "state": state,
        "labels": [{"name": name} for name in labels],
    }


class InitiativeLifecycleTests(unittest.TestCase):
    def test_initiative_never_dispatches_or_reserves_capacity(self):
        parent = issue(labels=("initiative", "agent-ready", "autonomous-backlog", "jules-session"))
        child = issue(43, labels=("agent-ready", "autonomous-backlog"))
        self.assertIsNone(dispatch.task_from_issue(parent))
        self.assertIsNone(dispatch.active_jules_task(parent))
        self.assertEqual([task.number for task in dispatch.select_tasks([parent, child], max_active=1)], [43])

    def test_label_reconciliation_removes_parent_dispatch_authorization(self):
        parent = issue(labels=("initiative", "agent-ready", "autonomous-backlog", "jules-session"))
        calls = []
        dispatch.reconcile_autonomous_labels([parent], repo="test/repo", run_gh=lambda *args: calls.append(args))
        self.assertEqual(len(calls), 1)
        self.assertIn("agent-ready", calls[0])
        self.assertIn("autonomous-backlog", calls[0])
        self.assertNotIn("jules-session", calls[0])
        self.assertEqual(dispatch.label_names(parent), {"initiative", "jules-session"})
        dispatch.reconcile_autonomous_labels([parent], repo="test/repo", run_gh=lambda *args: calls.append(args))
        self.assertEqual(len(calls), 1)  # Idempotent; no relabel churn.

    def test_legacy_guard_does_not_relabel_initiatives(self):
        parent = issue(labels=("initiative", "agent-ready"))
        comments = [{"body": "Jules completed session `abc`. Pull request: https://github.com/test/repo/pull/2"}]
        self.assertIsNone(guard.should_restore_review_ready(parent, comments))

    def test_exhausted_parent_never_creates_rework_or_closes(self):
        parent = issue(labels=("initiative", "jules-failed", "autonomous-backlog"))
        calls = []
        result = dispatch.supersede_exhausted_jules_failure(
            parent, issues=[parent], repo="test/repo", comments=[],
            run_gh_json=lambda *args: calls.append(args),
            run_gh=lambda *args: calls.append(args),
        )
        self.assertIsNone(result)
        self.assertEqual(calls, [])
        self.assertEqual(parent["state"], "open")

    def test_historical_merged_jules_reconciliation_skips_parent(self):
        calls = []
        dispatch.reconcile_historical_merged_jules_issues(
            "test/repo", load_open_autonomous=lambda: [issue()],
            load_comments=lambda n: self.fail("parent comments should not be loaded"),
            get_pr=lambda n: self.fail("parent PR should not be loaded"),
            run_gh=lambda *args: calls.append(args),
        )
        self.assertEqual(calls, [])

    def test_explicit_post_merge_closure_skips_parent(self):
        with mock.patch.object(merger, "gh_json", return_value=issue()), \
             mock.patch.object(merger.subprocess, "run") as run:
            merger.close_linked_issue_after_merge("test/repo", 42)
        run.assert_not_called()

    def test_closing_keywords_guard_every_reference_not_just_first(self):
        seen = []
        def load(number):
            seen.append(number)
            return issue(number, labels=("initiative",) if number == 42 else ())
        self.assertEqual(
            merger.initiative_closing_references("Fixes #41\nCloses #42\nCloses #41", load_issue=load),
            [42],
        )
        self.assertEqual(seen, [41, 42])
        with self.assertRaises(RuntimeError):
            merger.initiative_closing_references("Closes #42", load_issue=lambda _: (_ for _ in ()).throw(RuntimeError("unavailable")))

    def test_missing_issue_labels_fail_closed(self):
        with self.assertRaises(ValueError):
            merger.initiative_closing_references("Closes #42", load_issue=lambda _: {})
        with mock.patch.object(merger, "gh_json", return_value={"state": "open"}), \
             mock.patch.object(merger.subprocess, "run") as run:
            merger.close_linked_issue_after_merge("test/repo", 42)
        run.assert_not_called()

    def test_automerge_eligibility_rejects_parent_even_when_green(self):
        candidate = {
            "state": "open", "draft": False,
            "body": "Closes #42",
            "head": {"repo": {"full_name": "test/repo"}, "sha": "a" * 40},
        }
        ok, reason = merger.eligible_pr(
            candidate, repo="test/repo", issue=issue(),
            changed_paths=["README.md"], quality_runs=[],
        )
        self.assertFalse(ok)
        self.assertIn("initiative", reason)

    def test_housekeeping_never_closes_parent_on_completion_marker(self):
        calls = []
        def gh(*args):
            calls.append(args)
            if args[:3] == ("pr", "view", "70"):
                return json.dumps({"mergedAt": "2026-11-01T00:00:00Z", "body": "Updates #42\nCompletes acceptance criteria for #42"})
            if args[:3] == ("issue", "view", "42"):
                return json.dumps({"state": "OPEN", "labels": [{"name": "initiative"}], "body": ""})
            return "{}"
        with mock.patch.object(reconciler, "PR_NUMBER", 70), mock.patch.object(reconciler, "gh", side_effect=gh):
            reconciler.main()
        self.assertFalse(any(args[:2] == ("issue", "close") for args in calls))


if __name__ == "__main__":
    unittest.main()
