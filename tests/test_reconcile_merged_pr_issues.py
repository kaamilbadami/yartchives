import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Tests(unittest.TestCase):
    def test_contract(self):
        workflow = (ROOT / ".github/workflows/repository-housekeeping.yml").read_text()
        self.assertIn("pull_request:", workflow)
        self.assertIn("- closed", workflow)
        self.assertIn("github.event.pull_request.merged == true", workflow)
        self.assertIn("issues: write", workflow)

        reference = re.compile(r"(?im)\b(?:updates?|refs?|references?|related\s+to)\s+#(\d+)\b")
        complete = re.compile(r"(?im)^\s*Completes acceptance criteria for #(\d+)\s*$")
        self.assertEqual(reference.findall("Updates #449"), ["449"])
        self.assertEqual(complete.findall("Updates #449"), [])
        self.assertEqual(
            complete.findall("Completes acceptance criteria for #449"),
            ["449"],
        )

    def test_supersede_regex(self):
        from scripts.reconcile_merged_pr_issues import SUPERSEDE_RE

        self.assertEqual(
            SUPERSEDE_RE.findall("<!-- supersedes-stale-pr: 123 -->"),
            [("123", "")]
        )
        self.assertEqual(
            SUPERSEDE_RE.findall("<!-- supersedes-stale-pr: 123 original-issue: 456 -->"),
            [("123", "456")]
        )
        self.assertEqual(
            SUPERSEDE_RE.findall("<!-- supersedes-stale-pr:123 original-issue:456 -->"),
            [("123", "456")]
        )
        self.assertEqual(
            SUPERSEDE_RE.findall("<!--\nsupersedes-stale-pr: 123\noriginal-issue: 456\n-->"),
            [("123", "456")]
        )

    def test_reproduction_lifecycle_793_802_recovered_by_812(self):
        import json
        from unittest import mock
        from scripts import reconcile_merged_pr_issues as mod

        # PR 812 merges, containing markers for 799 (from 793) and 805 (from 802).
        def mock_gh(*args):
            if args[:3] == ("pr", "view", "812"):
                return json.dumps({
                    "mergedAt": "2023-10-04T12:00:00Z",
                    "url": "https://github.com/repo/pull/812",
                    "body": "<!-- supersedes-stale-pr: 799 original-issue: 793 -->\n<!-- supersedes-stale-pr: 805 -->"
                })
            if args[:3] == ("pr", "view", "805"):
                return json.dumps({"body": "Closes #802"})
            if args[:3] == ("issue", "view", "793"):
                return json.dumps({"state": "OPEN", "labels": [{"name": "jules-review-ready"}]})
            if args[:3] == ("issue", "view", "802"):
                return json.dumps({"state": "OPEN", "labels": [{"name": "jules"}]})
            return ""

        calls = []
        def mock_gh_run(*args):
            calls.append(args)
            return mock_gh(*args)

        with mock.patch.object(mod, "PR_NUMBER", 812), \
             mock.patch.object(mod, "gh", side_effect=mock_gh_run):
            mod.main()

        # It should strip labels from both 793 and 802
        self.assertTrue(any(c[:3] == ("issue", "edit", "793") and "--remove-label" in c and "jules-review-ready" in c for c in calls))
        self.assertTrue(any(c[:3] == ("issue", "edit", "802") and "--remove-label" in c and "jules" in c for c in calls))

        # It should close both issues as completed (since PR fully completed them)
        self.assertTrue(any(c[:3] == ("issue", "close", "793") and "completed" in c for c in calls))
        self.assertTrue(any(c[:3] == ("issue", "close", "802") and "completed" in c for c in calls))


    def test_initiative_relabel_after_completion_comment_prevents_close(self):
        import json
        from unittest import mock
        from scripts import reconcile_merged_pr_issues as mod

        labels = []
        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:3] == ("pr", "view", "70"):
                return json.dumps({"mergedAt": "2026-11-02T00:00:00Z",
                                   "body": "Updates #42\nCompletes acceptance criteria for #42"})
            if args[:3] == ("issue", "view", "42"):
                return json.dumps({"state": "OPEN", "labels": [{"name": x} for x in labels], "body": ""})
            if args[:3] == ("issue", "comment", "42"):
                labels.append("initiative")
            return "{}"

        with mock.patch.object(mod, "PR_NUMBER", 70), mock.patch.object(mod, "gh", side_effect=fake_gh):
            mod.main()
        self.assertTrue(any(c[:3] == ("issue", "comment", "42") for c in calls))
        self.assertFalse(any(c[:3] == ("issue", "close", "42") for c in calls))

    def test_initiative_relabel_during_supersede_label_cleanup_blocks_followup(self):
        import json
        from unittest import mock
        from scripts import reconcile_merged_pr_issues as mod

        labels = ["jules-review-ready"]
        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:3] == ("pr", "view", "70"):
                return json.dumps({"mergedAt": "2026-11-02T00:00:00Z",
                    "body": "<!-- supersedes-stale-pr: 7 original-issue: 42 -->"})
            if args[:3] == ("issue", "view", "42"):
                return json.dumps({"state": "OPEN", "labels": [{"name": x} for x in labels], "body": ""})
            if args[:3] == ("issue", "edit", "42") and "--remove-label" in args:
                labels.append("initiative")
            return "{}"

        with mock.patch.object(mod, "PR_NUMBER", 70), mock.patch.object(mod, "gh", side_effect=fake_gh):
            mod.main()
        self.assertTrue(any(c[:3] == ("issue", "edit", "42") for c in calls))
        self.assertFalse(any(c[:3] in {("issue", "comment", "42"), ("issue", "close", "42")}
                             or (c[:3] == ("issue", "edit", "42") and "--body" in c)
                             for c in calls))

    def test_missing_live_issue_labels_blocks_reconciliation_writes(self):
        import json
        from unittest import mock
        from scripts import reconcile_merged_pr_issues as mod

        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:3] == ("pr", "view", "70"):
                return json.dumps({"mergedAt": "2026-11-02T00:00:00Z",
                                   "body": "Updates #42\nCompletes acceptance criteria for #42"})
            if args[:3] == ("issue", "view", "42"):
                return json.dumps({"state": "OPEN", "body": ""})
            return "{}"

        with mock.patch.object(mod, "PR_NUMBER", 70), mock.patch.object(mod, "gh", side_effect=fake_gh):
            mod.main()
        self.assertFalse(any(c[:3] in {("issue", "comment", "42"), ("issue", "close", "42")}
                             for c in calls))

    def test_concurrent_issue_closure_after_comment_does_not_close_twice(self):
        import json
        from unittest import mock
        from scripts import reconcile_merged_pr_issues as mod

        state = ["OPEN"]
        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:3] == ("pr", "view", "70"):
                return json.dumps({"mergedAt": "2026-11-02T00:00:00Z",
                                   "body": "Updates #42\nCompletes acceptance criteria for #42"})
            if args[:3] == ("issue", "view", "42"):
                return json.dumps({"state": state[0], "labels": [], "body": ""})
            if args[:3] == ("issue", "comment", "42"):
                state[0] = "CLOSED"
            return "{}"

        with mock.patch.object(mod, "PR_NUMBER", 70), mock.patch.object(mod, "gh", side_effect=fake_gh):
            mod.main()
        self.assertFalse(any(c[:3] == ("issue", "close", "42") for c in calls))



    def test_guarded_body_update_refuses_stale_snapshot(self):
        import json
        from unittest import mock
        from scripts import reconcile_merged_pr_issues as mod

        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:3] == ("issue", "view", "42"):
                return json.dumps({"state": "OPEN", "labels": [],
                                   "body": "New concurrent user edit"})
            return "{}"

        with mock.patch.object(mod, "gh", side_effect=fake_gh):
            updated = mod.guarded_issue_write(
                42, "issue", "edit", "42", "--body", "Old snapshot\\nmarker",
                expected_body="Old snapshot",
            )
        self.assertFalse(updated)
        self.assertFalse(any(c[:3] == ("issue", "edit", "42") for c in calls))

    def test_guarded_body_update_allows_matching_snapshot(self):
        import json
        from unittest import mock
        from scripts import reconcile_merged_pr_issues as mod

        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:3] == ("issue", "view", "42"):
                return json.dumps({"state": "OPEN", "labels": [],
                                   "body": "Original"})
            return "{}"

        with mock.patch.object(mod, "gh", side_effect=fake_gh):
            updated = mod.guarded_issue_write(
                42, "issue", "edit", "42", "--body", "Original\\nmarker",
                expected_body="Original",
            )
        self.assertTrue(updated)
        self.assertTrue(any(c[:3] == ("issue", "edit", "42") for c in calls))


if __name__ == "__main__":
    unittest.main()
