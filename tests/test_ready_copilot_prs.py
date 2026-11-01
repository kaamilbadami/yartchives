"""Behavioral safety tests for trusted Copilot draft-to-ready reconciliation."""
import unittest

from scripts import ready_copilot_prs as ready

REPO = "kaamilbadami/yartchives"
SHA = "a" * 40


def fixtures():
    pr = {
        "number": 77, "state": "open", "draft": True,
        "user": {"login": "Copilot"}, "body": "Fixes #76",
        "base": {"ref": "main"},
        "head": {"repo": {"full_name": REPO}, "ref": "copilot/issue-76", "sha": SHA},
    }
    issue = {"number": 76, "state": "open", "labels": [],
             "assignees": [{"login": "Copilot"}]}
    files = [{"filename": "tests/test_example.py"}]
    events = [
        {"event": "copilot_work_started", "created_at": "2026-11-01T01:00:00Z"},
        {"event": "copilot_work_finished", "created_at": "2026-11-01T01:02:00Z",
         "performed_via_github_app": {"slug": "copilot-swe-agent"}},
        {"event": "review_requested", "created_at": "2026-11-01T01:02:00Z",
         "actor": {"login": "Copilot"}},
    ]
    links = [{"event": "connected", "actor": {"login": "Copilot"},
              "subject": {"number": 77, "repository": {"full_name": REPO}}}]
    return pr, issue, files, events, links


def allowed(values):
    return ready.provenance_verified(*values, REPO)[0]


class CopilotReadyPolicyTests(unittest.TestCase):
    def test_finished_connected_review_requested_low_risk_is_eligible(self):
        self.assertTrue(allowed(fixtures()))

    def test_draft_to_ready_is_not_a_merge_approval(self):
        self.assertFalse(allowed((dict(fixtures()[0], draft=False), *fixtures()[1:])))

    def test_wrong_author_or_foreign_branch_is_rejected(self):
        p, i, f, e, links = fixtures()
        p["user"]["login"] = "kaamilbadami"
        self.assertFalse(allowed((p, i, f, e, links)))
        p, i, f, e, links = fixtures()
        p["head"]["repo"]["full_name"] = "attacker/repo"
        self.assertFalse(allowed((p, i, f, e, links)))

    def test_multiple_or_external_closing_references_are_rejected(self):
        p, i, f, e, links = fixtures()
        p["body"] = "Fixes #76\nCloses #1122"
        self.assertFalse(allowed((p, i, f, e, links)))
        p["body"] = "Fixes attacker/repo#76"
        self.assertFalse(allowed((p, i, f, e, links)))

    def test_missing_connection_or_copilot_assignment_fails_closed(self):
        p, i, f, e, links = fixtures()
        self.assertFalse(allowed((p, i, f, e, [])))
        i["assignees"] = []
        self.assertFalse(allowed((p, i, f, e, links)))

    def test_initiative_and_missing_metadata_fail_closed(self):
        p, i, f, e, links = fixtures()
        i["labels"] = [{"name": "initiative"}]
        self.assertFalse(allowed((p, i, f, e, links)))
        i.pop("labels")
        self.assertFalse(allowed((p, i, f, e, links)))

    def test_unfinished_or_resumed_work_never_transitions(self):
        p, i, f, e, links = fixtures()
        self.assertFalse(allowed((p, i, f, e[:1], links)))
        e.append({"event": "copilot_work_started", "created_at": "2026-11-01T01:03:00Z"})
        self.assertFalse(allowed((p, i, f, e, links)))

    def test_review_request_is_required_after_completion(self):
        p, i, f, e, links = fixtures()
        self.assertFalse(allowed((p, i, f, e[:2], links)))

    def test_privileged_paths_and_unknown_paths_are_rejected(self):
        p, i, f, e, links = fixtures()
        for path in (".github/workflows/quality.yml", "scripts/auto_merge_agent_prs.py",
                     "scripts/ready_copilot_prs.py", "requirements.txt",
                     "scripts/deploy_secrets.py"):
            with self.subTest(path=path):
                self.assertFalse(allowed((p, i, [{"filename": path}], e, links)))

    def test_exact_head_ci_must_be_green(self):
        green = [{"name": "Quality checks", "head_sha": SHA,
                  "status": "completed", "conclusion": "success"}]
        self.assertTrue(ready.exact_head_quality_green(green, SHA))
        self.assertFalse(ready.exact_head_quality_green(green, "b" * 40))
        self.assertFalse(ready.exact_head_quality_green(
            [dict(green[0], conclusion="failure")], SHA))

    def test_recovery_only_for_missing_or_approval_gated_ci(self):
        self.assertTrue(ready.recovery_allowed([], SHA))
        action = [{"name": "Quality checks", "head_sha": SHA,
                   "status": "completed", "conclusion": "action_required"}]
        self.assertTrue(ready.recovery_allowed(action, SHA))
        for status, conclusion in (("in_progress", None), ("completed", "failure"),
                                   ("completed", "success")):
            self.assertFalse(ready.recovery_allowed(
                [dict(action[0], status=status, conclusion=conclusion)], SHA))


if __name__ == "__main__":
    unittest.main()
