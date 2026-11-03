"""Behavioral safety tests for trusted Copilot draft-to-ready reconciliation."""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import yaml

from scripts import ready_copilot_prs as ready

REPO = "kaamilbadami/yartchives"
SHA = "a" * 40


def fixtures():
    pr = {
        "number": 77, "state": "open", "draft": True,
        "user": {"login": "Copilot"}, "body": "Fixes #76",
        "base": {"ref": "main", "sha": "e" * 40},
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

    def test_disconnected_issue_pr_link_invalidates_historical_connection(self):
        p, i, f, e, links = fixtures()
        disconnected = {"event": "disconnected", "actor": {"login": "kaamilbadami"},
                        "subject": {"number": 77,
                                    "repository": {"full_name": REPO}}}
        self.assertFalse(allowed((p, i, f, e, links + [disconnected])))
        # A disconnect for a different PR does not invalidate this link.
        other = dict(disconnected, subject={"number": 78,
                                            "repository": {"full_name": REPO}})
        self.assertTrue(allowed((p, i, f, e, links + [other])))
        # A subsequent Copilot reconnection restores the current provenance.
        self.assertTrue(allowed((p, i, f, e, links + [
            disconnected, dict(links[0])
        ])))

    def test_unfinished_or_resumed_work_never_transitions(self):
        p, i, f, e, links = fixtures()
        self.assertFalse(allowed((p, i, f, e[:1], links)))
        e.append({"event": "copilot_work_started", "created_at": "2026-11-01T01:03:00Z"})
        self.assertFalse(allowed((p, i, f, e, links)))

    def test_commits_or_force_push_after_completion_invalidate_readiness(self):
        for event in ("committed", "head_ref_force_pushed", "synchronize"):
            p, i, f, e, links = fixtures()
            e.append({"event": event, "sha": "b" * 40})
            with self.subTest(event=event):
                self.assertFalse(allowed((p, i, f, e, links)))

    def test_new_completion_after_commit_restores_eligibility(self):
        p, i, f, e, links = fixtures()
        e.extend([
            {"event": "committed", "sha": "b" * 40},
            {"event": "copilot_work_finished", "created_at": "2026-11-01T01:04:00Z",
             "performed_via_github_app": {"slug": "copilot-swe-agent"}},
            {"event": "review_requested", "created_at": "2026-11-01T01:04:00Z",
             "actor": {"login": "Copilot"}},
        ])
        self.assertTrue(allowed((p, i, f, e, links)))

    def test_review_request_is_required_after_completion(self):
        p, i, f, e, links = fixtures()
        self.assertFalse(allowed((p, i, f, e[:2], links)))

    def test_removed_review_request_blocks_ready_until_copilot_requests_again(self):
        p, i, f, e, links = fixtures()
        removed = {"event": "review_request_removed",
                   "actor": {"login": "kaamilbadami"},
                   "requested_reviewer": {"login": "kaamilbadami"}}
        self.assertFalse(allowed((p, i, f, e + [removed], links)))
        renewed = {"event": "review_requested", "actor": {"login": "Copilot"},
                   "requested_reviewer": {"login": "kaamilbadami"}}
        self.assertTrue(allowed((p, i, f, e + [removed, renewed], links)))
        # A later owner request alone is not proof that Copilot requested review.
        renewed["actor"] = {"login": "kaamilbadami"}
        self.assertFalse(allowed((p, i, f, e + [removed, renewed], links)))

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

    def test_newer_failed_or_pending_head_run_overrides_old_success(self):
        older = {"name": "Quality checks", "head_sha": SHA,
                 "status": "completed", "conclusion": "success",
                 "created_at": "2026-11-01T01:00:00Z", "id": 1}
        for status, conclusion in (("completed", "failure"), ("in_progress", None)):
            newer = dict(older, status=status, conclusion=conclusion,
                         created_at="2026-11-01T01:05:00Z", id=2)
            with self.subTest(status=status):
                self.assertFalse(ready.exact_head_quality_green([older, newer], SHA))
        self.assertTrue(ready.exact_head_quality_green([older], SHA))

    def test_newer_approval_gate_does_not_erase_executed_green_head_ci(self):
        # Live #1126 evidence: a successful workflow_dispatch for an exact
        # head was followed by a pull_request run blocked as action_required.
        # The latter never executed tests and must not erase the former.
        green = {"name": "Quality checks", "head_sha": SHA,
                 "event": "workflow_dispatch", "status": "completed",
                 "conclusion": "success", "created_at": "2026-11-02T01:23:38Z",
                 "id": 41372256098}
        gated = {"name": "Quality checks", "head_sha": SHA,
                 "event": "pull_request", "status": "completed",
                 "conclusion": "action_required",
                 "created_at": "2026-11-02T01:23:42Z", "id": 41372261951}
        self.assertTrue(ready.exact_head_quality_green([gated, green], SHA))
        self.assertFalse(ready.exact_head_quality_green([gated], SHA))
        self.assertFalse(ready.exact_head_quality_green([gated, green], "b" * 40))
        # A newer actual failing or pending execution still overrides green.
        for status, conclusion in (("completed", "failure"), ("in_progress", None)):
            real_failure = dict(green, status=status, conclusion=conclusion,
                                created_at="2026-11-02T01:24:00Z", id=41372262000)
            with self.subTest(status=status):
                self.assertFalse(ready.exact_head_quality_green(
                    [green, gated, real_failure], SHA))

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

    def test_exact_head_recovery_requires_trusted_bot_and_run_url(self):
        good = {"statuses": [{
            "context": "copilot-head-tests", "state": "success",
            "creator": {"login": "github-actions[bot]"},
            "target_url": f"https://github.com/{REPO}/actions/runs/123",
        }]}
        valid_run = {
            "name": "Quality checks", "event": "workflow_dispatch",
            "head_branch": "main", "status": "completed", "conclusion": "success",
            "path": ".github/workflows/quality.yml",
            "repository": {"full_name": REPO},
        }
        with mock.patch.object(ready, "gh_json", return_value=valid_run):
            self.assertTrue(ready.trusted_recovery_head_green(good, SHA, REPO))
        # Regression: an actual github.com Actions URL must match; a double-escaped
        # dot in the verifier regex silently rejected all legitimate runs.
        with mock.patch.object(ready, "gh_json", return_value=valid_run) as fetch:
            self.assertTrue(ready.trusted_recovery_head_green(good, SHA, REPO))
            fetch.assert_called_once_with(f"repos/{REPO}/actions/runs/123")
        for changes in (
            {"event": "pull_request"}, {"head_branch": "copilot/untrusted"},
            {"conclusion": "failure"}, {"status": "in_progress"},
            {"path": ".github/workflows/untrusted.yml"},
            {"repository": {"full_name": "attacker/repo"}},
        ):
            with self.subTest(run_changes=changes):
                with mock.patch.object(ready, "gh_json", return_value=dict(valid_run, **changes)):
                    self.assertFalse(ready.trusted_recovery_head_green(good, SHA, REPO))
        with mock.patch.object(ready, "gh_json", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                ready.trusted_recovery_head_green(good, SHA, REPO)
        for changes in (
            {"state": "pending"},
            {"creator": {"login": "attacker"}},
            {"target_url": "https://example.com/actions/runs/123"},
            {"target_url": "https://github.com/attacker/repo/actions/runs/123"},
        ):
            with self.subTest(changes=changes):
                forged = dict(good["statuses"][0], **changes)
                self.assertFalse(ready.trusted_recovery_head_green(
                    {"statuses": [forged]}, SHA, REPO))
        self.assertFalse(ready.trusted_recovery_head_green(good, "invalid", REPO))
        # A newer failure must override an old trusted success.
        failed = dict(good["statuses"][0], state="failure")
        self.assertFalse(ready.trusted_recovery_head_green(
            {"statuses": [failed, good["statuses"][0]]}, SHA, REPO))

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
                       merge_quality=False, stale_merge=False, failed_merge=False,
                       late_commit=False, missing_merge_status=False,
                       head_action_required=False, merge_drift_on_recheck=False,
                       late_disconnect=False, body_drift_on_recheck=False,
                       head_ref_drift_on_recheck=False, author_drift_on_recheck=False,
                       base_sha_drift_on_recheck=False, missing_base_sha_on_recheck=False,
                       trusted_head_recovery=False, head_failed=False):
        pr, issue, files, events, links = fixtures()
        current = dict(pr)
        if head_drift:
            current["head"] = dict(pr["head"], sha="b" * 40)
        if merge_quality:
            current["merge_commit_sha"] = "c" * 40
        green = [{"name": "Quality checks", "head_sha": SHA,
                  "status": "completed", "conclusion": "success"}] if quality else []
        if head_action_required:
            green = [{"name": "Quality checks", "head_sha": SHA,
                      "status": "completed", "conclusion": "action_required"}]
        if head_failed:
            green = [{"name": "Quality checks", "head_sha": SHA,
                      "status": "completed", "conclusion": "failure"}]
        timeline_reads = [0]
        issue_timeline_reads = [0]
        pr_reads = [0]
        def pages(endpoint):
            if "/pulls?state=open" in endpoint:
                return [pr]
            if "/files?" in endpoint:
                return files
            if "/issues/77/timeline?" in endpoint:
                timeline_reads[0] += 1
                if late_commit and timeline_reads[0] > 1:
                    return events + [{"event": "committed", "sha": "b" * 40}]
                return events
            if "/issues/76/timeline?" in endpoint:
                issue_timeline_reads[0] += 1
                if late_disconnect and issue_timeline_reads[0] > 1:
                    return links + [{
                        "event": "disconnected", "actor": {"login": "kaamilbadami"},
                        "subject": {"number": 77,
                                    "repository": {"full_name": REPO}},
                    }]
                return links
            if "/issues/77/comments?" in endpoint:
                return comments or []
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        def get(endpoint):
            if "/issues/76" in endpoint:
                return issue
            if endpoint == f"repos/{REPO}/actions/runs/123":
                return {
                    "name": "Quality checks", "event": "workflow_dispatch",
                    "head_branch": "main", "status": "completed",
                    "conclusion": "success", "path": ".github/workflows/quality.yml",
                    "repository": {"full_name": REPO},
                }
            if "/actions/runs?" in endpoint:
                return {"workflow_runs": green}
            if f"/commits/{SHA}/status" in endpoint:
                if trusted_head_recovery:
                    return {"statuses": [{
                        "context": "copilot-head-tests", "state": "success",
                        "creator": {"login": "github-actions[bot]"},
                        "target_url": f"https://github.com/{REPO}/actions/runs/123",
                    }]}
                return {"statuses": []}
            if "/commits/" in endpoint and "/status" in endpoint:
                return {"statuses": [] if missing_merge_status else [{
                    "context": "tests",
                    "state": "failure" if failed_merge else (
                        "pending" if stale_merge else "success")
                }]}
            if "/pulls/77" in endpoint:
                pr_reads[0] += 1
                if pr_reads[0] > 1:
                    if merge_drift_on_recheck:
                        return dict(current, merge_commit_sha="d" * 40)
                    if base_sha_drift_on_recheck:
                        return dict(current, base=dict(current["base"], sha="f" * 40))
                    if missing_base_sha_on_recheck:
                        return dict(current, base={"ref": "main"})
                    if body_drift_on_recheck:
                        return dict(current, body="Closes #1122")
                    if head_ref_drift_on_recheck:
                        return dict(current, head=dict(current["head"], ref="copilot/other"))
                    if author_drift_on_recheck:
                        return dict(current, user={"login": "untrusted-contributor"})
                return current
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        with mock.patch.dict("os.environ", {"REPOSITORY": REPO}), \
             mock.patch.object(ready, "gh_pages", side_effect=pages), \
             mock.patch.object(ready, "gh_json", side_effect=get), \
             mock.patch.object(ready, "gh_write") as write:
            self.assertEqual(ready.main(), 0)
        return write.call_args_list

    def test_green_head_and_current_merge_marks_ready_never_merges(self):
        calls = self.run_controller(merge_quality=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args, ("pr", "ready", "77", "--repo", REPO))

    def test_head_green_without_merge_sha_never_marks_ready(self):
        self.assertEqual(self.run_controller(quality=True), [])

    def test_head_green_missing_merge_status_dispatches_once_before_ready(self):
        calls = self.run_controller(
            quality=True, merge_quality=True, missing_merge_status=True
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[:4], (
            "api", "--method", "POST", f"repos/{REPO}/issues/77/comments"
        ))
        self.assertEqual(calls[1].args, (
            "workflow", "run", "quality.yml", "--repo", REPO,
            "--ref", "main", "-f", "pr_recovery=true", "-f", "pr_number=77",
            "-f", f"pr_head_sha={SHA}"
        ))
        marker = ready.RECOVERY_MARKER.format(head=SHA, merge="c" * 40)
        self.assertEqual(self.run_controller(
            quality=True, merge_quality=True, missing_merge_status=True,
            comments=[{"body": marker, "user": {"login": "github-actions[bot]"}}]
        ), [])

    def test_changed_merge_sha_allows_one_bounded_new_recovery(self):
        # A successful earlier dispatch cannot publish a stale merge status
        # after main moves. The new merge may be tested once without replaying
        # the old merge or allowing unbounded attempts for one head.
        old = ready.RECOVERY_MARKER.format(head=SHA, merge="d" * 40)
        comments = [{"body": old, "user": {"login": "github-actions[bot]"}}]
        calls = self.run_controller(
            quality=True, merge_quality=True, missing_merge_status=True,
            comments=comments,
        )
        self.assertEqual(len(calls), 2)
        self.assertIn(
            ready.RECOVERY_MARKER.format(head=SHA, merge="c" * 40),
            calls[0].args[-1],
        )
        new = ready.RECOVERY_MARKER.format(head=SHA, merge="c" * 40)
        self.assertEqual(self.run_controller(
            quality=True, merge_quality=True, missing_merge_status=True,
            comments=comments + [{"body": new, "user": {"login": "github-actions[bot]"}}],
        ), [])

    def test_recovery_budget_and_legacy_marker_fail_closed(self):
        old = ready.RECOVERY_MARKER.format(head=SHA, merge="d" * 40)
        other = ready.RECOVERY_MARKER.format(head=SHA, merge="e" * 40)
        bot = lambda body: {"body": body, "user": {"login": "github-actions[bot]"}}
        self.assertEqual(self.run_controller(
            quality=True, merge_quality=True, missing_merge_status=True,
            comments=[bot(old), bot(other)],
        ), [])
        legacy = f"<!-- copilot-draft-ci-recovery: head={SHA} -->"
        self.assertEqual(self.run_controller(
            quality=True, merge_quality=True, missing_merge_status=True,
            comments=[bot(legacy)],
        ), [])

    def test_settled_legacy_pilot_marker_allows_exactly_one_recovery(self):
        # Existing live pilot #1159 has a bot-authored head-only marker from
        # the pre-upgrade controller. It must not remain permanently stranded.
        legacy = f"<!-- copilot-draft-ci-recovery: head={SHA} -->"
        settled = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        bot = lambda body, created: {
            "body": body, "user": {"login": "github-actions[bot]"},
            "created_at": created,
        }
        first = bot(legacy, settled)
        calls = self.run_controller(
            quality=False, merge_quality=True, missing_merge_status=True,
            head_action_required=True, comments=[first],
        )
        self.assertEqual(len(calls), 2)
        new_marker = ready.RECOVERY_MARKER.format(head=SHA, merge="c" * 40)
        self.assertIn(new_marker, calls[0].args[-1])
        self.assertEqual(self.run_controller(
            quality=False, merge_quality=True, missing_merge_status=True,
            head_action_required=True,
            comments=[first, bot(new_marker, settled)],
        ), [])

    def test_unsettled_or_unverifiable_legacy_recovery_does_not_duplicate(self):
        legacy = f"<!-- copilot-draft-ci-recovery: head={SHA} -->"
        recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        for created in (recent, "invalid-date", None):
            with self.subTest(created=created):
                marker = {"body": legacy, "user": {"login": "github-actions[bot]"}}
                if created is not None:
                    marker["created_at"] = created
                self.assertEqual(self.run_controller(
                    quality=False, merge_quality=True, missing_merge_status=True,
                    head_action_required=True, comments=[marker],
                ), [])

    def test_legacy_plus_one_current_attempt_exhausts_recovery_budget(self):
        legacy = f"<!-- copilot-draft-ci-recovery: head={SHA} -->"
        old = ready.RECOVERY_MARKER.format(head=SHA, merge="d" * 40)
        settled = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        comments = [{
            "body": marker, "created_at": settled,
            "user": {"login": "github-actions[bot]"},
        } for marker in (legacy, old)]
        self.assertEqual(self.run_controller(
            quality=False, merge_quality=True, missing_merge_status=True,
            head_action_required=True, comments=comments,
        ), [])

    def test_untrusted_comment_cannot_exhaust_recovery_budget(self):
        marker = ready.RECOVERY_MARKER.format(head=SHA, merge="c" * 40)
        calls = self.run_controller(
            quality=True, merge_quality=True, missing_merge_status=True,
            comments=[{"body": marker, "user": {"login": "untrusted-contributor"}}],
        )
        self.assertEqual(len(calls), 2)

    def test_newer_head_failure_blocks_even_with_green_merge(self):
        pr, issue, files, events, links = fixtures()
        runs = [
            {"name": "Quality checks", "head_sha": SHA, "status": "completed",
             "conclusion": "failure"}
        ]
        self.assertFalse(ready.exact_head_quality_green(runs, SHA))
        self.assertFalse(ready.recovery_allowed(runs, SHA))
        # The controller requires both a trustworthy head outcome (or a
        # recovery-only approval gate) and current merge success.
        self.assertTrue(ready.exact_merge_tests_green(
            {"statuses": [{"context": "tests", "state": "success"}]}, "c" * 40
        ))

    def test_green_merge_status_without_executed_head_ci_stays_draft(self):
        # A green merge cannot authorize ready. Recover the exact head in an
        # isolated read-only job, without executing untrusted code with write.
        calls = self.run_controller(quality=False, merge_quality=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].args[-2:], ("-f", f"pr_head_sha={SHA}"))

    def test_approval_gated_head_ci_cannot_be_bypassed_by_green_merge(self):
        calls = self.run_controller(
            quality=False, merge_quality=True, head_action_required=True
        )
        self.assertEqual(len(calls), 2)
        self.assertNotIn(("pr", "ready"), [call.args[:2] for call in calls])
        # Only an actual trusted read-only exact-head success may authorize ready.
        calls = self.run_controller(
            quality=False, merge_quality=True, head_action_required=True,
            trusted_head_recovery=True,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[:2], ("pr", "ready"))

    def test_executed_head_failure_vetoes_trusted_recovery(self):
        # A real failed head run is not approval-gated and cannot be bypassed
        # by a previously green trusted recovery status.
        self.assertEqual(self.run_controller(
            quality=False, merge_quality=True, trusted_head_recovery=True,
            head_failed=True,
        ), [])

    def test_failed_merge_blocks_ready_even_when_head_ci_is_green(self):
        self.assertEqual(self.run_controller(
            quality=True, merge_quality=True, failed_merge=True
        ), [])

    def test_merge_sha_changes_during_final_recheck_blocks_ready(self):
        # A main-branch advancement changes refs/pull/N/merge without
        # changing the head. The original green status is now stale.
        self.assertEqual(self.run_controller(
            quality=True, merge_quality=True, merge_drift_on_recheck=True
        ), [])

    def test_base_sha_drift_or_missing_metadata_blocks_ready_even_if_merge_sha_stays_green(self):
        # GitHub can lag in regenerating refs/pull/N/merge after main moves.
        # A green status on the old synthetic merge must not authorize ready.
        for drift in ("base_sha_drift_on_recheck", "missing_base_sha_on_recheck"):
            with self.subTest(drift=drift):
                self.assertEqual(self.run_controller(
                    quality=True, merge_quality=True, **{drift: True}
                ), [])

    def test_authorization_metadata_drift_during_final_recheck_blocks_ready(self):
        # A late body edit can replace the verified child with an initiative
        # closing reference without changing either the head or merge SHA.
        for drift in ("body_drift_on_recheck", "head_ref_drift_on_recheck",
                      "author_drift_on_recheck"):
            with self.subTest(drift=drift):
                self.assertEqual(self.run_controller(
                    quality=True, merge_quality=True, **{drift: True}
                ), [])

    def test_issue_pr_disconnected_during_final_recheck_blocks_ready(self):
        # The issue was linked when the controller started, but its Copilot
        # connection was revoked before the last trusted readiness decision.
        self.assertEqual(self.run_controller(
            quality=True, merge_quality=True, late_disconnect=True
        ), [])

    def test_new_commit_between_validation_and_ready_blocks_transition(self):
        self.assertEqual(self.run_controller(late_commit=True, merge_quality=True), [])

    def test_pending_merge_status_does_not_mark_ready(self):
        calls = self.run_controller(quality=False, merge_quality=True, stale_merge=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].args[-2:], ("-f", f"pr_head_sha={SHA}"))

    def test_failed_current_merge_does_not_dispatch_again(self):
        self.assertEqual(self.run_controller(
            quality=False, merge_quality=True, failed_merge=True
        ), [])

    def test_head_drift_blocks_ready_and_recovery(self):
        self.assertEqual(self.run_controller(head_drift=True), [])

    def test_missing_ci_gets_one_durable_marked_dispatch(self):
        calls = self.run_controller(
            quality=False, merge_quality=True, missing_merge_status=True
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[:4], ("api", "--method", "POST", f"repos/{REPO}/issues/77/comments"))
        self.assertEqual(calls[1].args, (
            "workflow", "run", "quality.yml", "--repo", REPO,
            "--ref", "main", "-f", "pr_recovery=true", "-f", "pr_number=77",
            "-f", f"pr_head_sha={SHA}"
        ))
        marker = ready.RECOVERY_MARKER.format(head=SHA, merge="c" * 40)
        self.assertEqual(self.run_controller(
            quality=False, merge_quality=True, missing_merge_status=True,
            comments=[{"body": marker, "user": {"login": "github-actions[bot]"}}]
        ), [])


class CopilotRecoveryWorkflowSecurityTests(unittest.TestCase):
    def test_exact_head_recovery_keeps_untrusted_code_read_only(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/quality.yml"
        jobs = yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]
        head = jobs["head-tests"]
        publisher = jobs["publish-pr-recovery-status"]
        self.assertEqual(head["permissions"], {"contents": "read"})
        self.assertIn("workflow_dispatch", head["if"])
        self.assertIn("pr_head_sha", head["if"])
        self.assertEqual(
            head["steps"][0]["with"]["persist-credentials"], False
        )
        # No secret references or privileged token in any step that checks out
        # or executes untrusted Copilot code.
        untrusted_steps = yaml.safe_dump(head["steps"])
        self.assertNotIn("secrets.", untrusted_steps)
        self.assertNotIn("statuses: write", untrusted_steps)
        self.assertNotIn("actions: write", untrusted_steps)
        self.assertEqual(publisher["permissions"], {
            "contents": "read", "statuses": "write",
        })
        self.assertEqual(publisher["needs"], ["tests", "head-tests"])
        self.assertFalse(any("uses" in step for step in publisher["steps"]))


    def test_recovery_wake_requires_successful_trusted_status_publication(self):
        # A successful read-only tests job alone is not enough to wake the
        # controller: the required synthetic-merge status must be published
        # first, or the wake can race the publisher and redispatch recovery.
        path = Path(__file__).resolve().parents[1] / ".github/workflows/quality.yml"
        jobs = yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]
        wake = jobs["wake-automerge"]
        publisher = jobs["publish-pr-recovery-status"]
        self.assertEqual(wake["needs"], ["tests", "publish-pr-recovery-status"])
        self.assertIn("always()", wake["if"])
        self.assertIn("inputs.pr_recovery == true", wake["if"])
        self.assertIn(
            "needs.publish-pr-recovery-status.result == 'success'", wake["if"]
        )
        self.assertIn("needs.tests.result == 'success'", wake["if"])
        self.assertIn("statuses/$target", publisher["steps"][0]["run"])
        self.assertIn(
            "gh workflow run auto-merge-agent-prs.yml", wake["steps"][0]["run"]
        )



if __name__ == "__main__":
    unittest.main()
