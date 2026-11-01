"""Behavioral safety tests for trusted Copilot draft-to-ready reconciliation."""
import unittest
from unittest import mock

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

    def test_renamed_sensitive_source_cannot_be_laundered_into_tests(self):
        p, i, f, e, links = fixtures()
        self.assertFalse(allowed((p, i, [{
            "filename": "tests/test_quality.py", "status": "renamed",
            "previous_filename": ".github/workflows/quality.yml"
        }], e, links)))
        self.assertFalse(allowed((p, i, [{
            "filename": "tests/test_quality.py",
            "previous_filename": "scripts/auto_merge_agent_prs.py"
        }], e, links)))

    def test_exact_head_ci_must_be_green(self):
        green = [{"name": "Quality checks", "head_sha": SHA,
                  "status": "completed", "conclusion": "success"}]
        self.assertTrue(ready.exact_head_quality_green(green, SHA))
        self.assertFalse(ready.exact_head_quality_green(green, "b" * 40))
        self.assertFalse(ready.exact_head_quality_green(
            [dict(green[0], conclusion="failure")], SHA))

    def test_merge_status_requires_current_merge_sha_and_successful_tests(self):
        merge_sha = "c" * 40
        green = {"statuses": [{"context": "tests", "state": "success"}]}
        self.assertTrue(ready.exact_merge_tests_green(green, merge_sha))
        self.assertFalse(ready.exact_merge_tests_green(
            {"statuses": [{"context": "tests", "state": "pending"}]}, merge_sha))
        self.assertFalse(ready.exact_merge_tests_green(
            {"statuses": [{"context": "other", "state": "success"}]}, merge_sha))
        self.assertFalse(ready.exact_merge_tests_green(green, "not-a-sha"))
        self.assertFalse(ready.exact_merge_tests_green(
            {"statuses": [{"context": "tests", "state": "failure"},
                          {"context": "tests", "state": "success"}]}, merge_sha))

    def test_recovery_only_for_missing_or_approval_gated_ci(self):
        self.assertTrue(ready.recovery_allowed([], SHA))
        action = [{"name": "Quality checks", "head_sha": SHA,
                   "status": "completed", "conclusion": "action_required"}]
        self.assertTrue(ready.recovery_allowed(action, SHA))
        for status, conclusion in (("in_progress", None), ("completed", "failure"),
                                   ("completed", "success")):
            self.assertFalse(ready.recovery_allowed(
                [dict(action[0], status=status, conclusion=conclusion)], SHA))


class CopilotReadyReconciliationTests(unittest.TestCase):
    def run_controller(self, *, quality=True, head_drift=False, comments=None,
                       merge_quality=False, stale_merge=False, failed_merge=False):
        pr, issue, files, events, links = fixtures()
        current = dict(pr)
        if head_drift:
            current["head"] = dict(pr["head"], sha="b" * 40)
        if merge_quality:
            current["merge_commit_sha"] = "c" * 40
        green = [{"name": "Quality checks", "head_sha": SHA,
                  "status": "completed", "conclusion": "success"}] if quality else []
        def pages(endpoint):
            if "/pulls?state=open" in endpoint:
                return [pr]
            if "/files?" in endpoint:
                return files
            if "/issues/77/timeline?" in endpoint:
                return events
            if "/issues/76/timeline?" in endpoint:
                return links
            if "/issues/77/comments?" in endpoint:
                return comments or []
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        def get(endpoint):
            if "/issues/76" in endpoint:
                return issue
            if "/actions/runs?" in endpoint:
                return {"workflow_runs": green}
            if "/commits/" in endpoint and "/status" in endpoint:
                return {"statuses": [{"context": "tests",
                                      "state": "failure" if failed_merge else (
                                          "pending" if stale_merge else "success")}]}
            if "/pulls/77" in endpoint:
                return current
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        with mock.patch.dict("os.environ", {"REPOSITORY": REPO}), \
             mock.patch.object(ready, "gh_pages", side_effect=pages), \
             mock.patch.object(ready, "gh_json", side_effect=get), \
             mock.patch.object(ready, "gh_write") as write:
            self.assertEqual(ready.main(), 0)
        return write.call_args_list

    def test_green_exact_head_only_marks_ready_never_merges(self):
        calls = self.run_controller()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args, ("pr", "ready", "77", "--repo", REPO))

    def test_green_current_merge_status_marks_ready_without_head_run(self):
        calls = self.run_controller(quality=False, merge_quality=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args, ("pr", "ready", "77", "--repo", REPO))

    def test_pending_merge_status_does_not_mark_ready(self):
        calls = self.run_controller(quality=False, merge_quality=True, stale_merge=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].args[-2:], ("-f", "pr_number=77"))

    def test_failed_current_merge_does_not_dispatch_again(self):
        self.assertEqual(self.run_controller(
            quality=False, merge_quality=True, failed_merge=True
        ), [])

    def test_head_drift_blocks_ready_and_recovery(self):
        self.assertEqual(self.run_controller(head_drift=True), [])

    def test_missing_ci_gets_one_durable_marked_dispatch(self):
        calls = self.run_controller(quality=False)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[:4], ("api", "--method", "POST", f"repos/{REPO}/issues/77/comments"))
        self.assertEqual(calls[1].args, (
            "workflow", "run", "quality.yml", "--repo", REPO,
            "--ref", "main", "-f", "pr_recovery=true", "-f", "pr_number=77"
        ))
        marker = ready.RECOVERY_MARKER.format(head=SHA)
        self.assertEqual(self.run_controller(
            quality=False, comments=[{"body": marker}]
        ), [])


if __name__ == "__main__":
    unittest.main()
