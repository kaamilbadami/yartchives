import importlib.util
import subprocess
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "auto_merge_agent_prs.py"
SPEC = importlib.util.spec_from_file_location("auto_merge_agent_prs", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


def pr(*, body="Closes #10", files=(), head_sha="abc", draft=False, repo="kaamilbadami/yartchives"):
    return {
        "number": 20,
        "state": "open",
        "draft": draft,
        "body": body,
        "head": {"sha": head_sha, "repo": {"full_name": repo}},
        "base": {"ref": "main"},
        "_files": list(files),
    }


def issue(*, labels=("autonomous-backlog", "jules-review-ready"), state="open"):
    return {
        "number": 10,
        "state": state,
        "labels": [{"name": label} for label in labels],
    }


def runs(sha="abc", conclusion="success"):
    return [
        {
            "name": "Quality checks",
            "head_sha": sha,
            "status": "completed",
            "conclusion": conclusion,
        }
    ]


class AutoMergeAgentPrTests(unittest.TestCase):
    def test_quality_dispatch_wakes_automerge_with_run_id(self):
        workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text()
        self.assertIn("actions: write", workflow)
        self.assertIn("wake-automerge:", workflow)
        self.assertIn("gh workflow run auto-merge-agent-prs.yml", workflow)
        self.assertIn('-f wait_for_quality_run_id="$GITHUB_RUN_ID"', workflow)

    def test_automerge_waits_for_dispatched_quality_run_before_scan(self):
        workflow = (ROOT / ".github" / "workflows" / "auto-merge-agent-prs.yml").read_text()
        self.assertIn("wait_for_quality_run_id:", workflow)
        self.assertIn('gh run watch "${{ inputs.wait_for_quality_run_id }}"', workflow)
        self.assertIn("--exit-status", workflow)

    def test_automerge_workflow_can_create_and_close_supersession_issues(self):
        workflow = (ROOT / ".github" / "workflows" / "auto-merge-agent-prs.yml").read_text()
        self.assertIn("  issues: write", workflow)
        self.assertNotIn("  issues: read", workflow)

    def test_automerge_workflow_has_periodic_recovery_schedule(self):
        workflow = (ROOT / ".github" / "workflows" / "auto-merge-agent-prs.yml").read_text()
        self.assertIn('cron: "*/5 * * * *"', workflow)

    def test_automerge_workflow_fetches_full_history_for_branch_merges(self):
        workflow = (ROOT / ".github" / "workflows" / "auto-merge-agent-prs.yml").read_text()
        checkout_block = workflow.split("- name: Check out merge policy", 1)[1].split("- name: Merge one safe autonomous pull request", 1)[0]
        self.assertIn("fetch-depth: 0", checkout_block)

    def test_quality_run_query_includes_manual_dispatch_runs(self):
        path = mod.quality_runs_api_path("kaamilbadami/yartchives", "abc123")
        self.assertEqual(
            path,
            "repos/kaamilbadami/yartchives/actions/runs?head_sha=abc123&per_page=100",
        )
        self.assertNotIn("event=", path)

    def test_accepts_green_terminal_autonomous_agent_pr(self):
        candidate = pr(files=("app.js", "tests/apply-next-ui.test.cjs"))
        ok, reason = mod.eligible_pr(
            candidate,
            repo="kaamilbadami/yartchives",
            issue=issue(),
            changed_paths=candidate["_files"],
            quality_runs=runs(),
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "eligible")

    def test_exact_head_quality_presence_detects_missing_run(self):
        self.assertTrue(mod.exact_head_quality_present(runs(), "abc"))
        self.assertFalse(mod.exact_head_quality_present([], "abc"))
        self.assertFalse(mod.exact_head_quality_present(runs(sha="older"), "abc"))

    def test_superseded_action_required_runs_require_exact_head_manual_replacement(self):
        approval = {
            "id": 10,
            "name": "Quality checks",
            "head_sha": "abc",
            "event": "pull_request",
            "status": "completed",
            "conclusion": "action_required",
        }
        manual = {
            "id": 11,
            "name": "Quality checks",
            "head_sha": "abc",
            "event": "workflow_dispatch",
            "status": "in_progress",
            "conclusion": None,
        }
        other_head = {
            "id": 12,
            "name": "Quality checks",
            "head_sha": "other",
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
        }

        self.assertEqual(
            mod.superseded_action_required_run_ids([approval, manual], "abc"),
            [10],
        )
        self.assertEqual(
            mod.superseded_action_required_run_ids([approval, other_head], "abc"),
            [],
        )

    def test_delete_superseded_action_required_runs_deletes_only_obsolete_pr_runs(self):
        runs = [
            {
                "id": 10,
                "name": "Quality checks",
                "head_sha": "abc",
                "event": "pull_request",
                "status": "completed",
                "conclusion": "action_required",
            },
            {
                "id": 11,
                "name": "Quality checks",
                "head_sha": "abc",
                "event": "workflow_dispatch",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 12,
                "name": "Quality checks",
                "head_sha": "abc",
                "event": "pull_request",
                "status": "completed",
                "conclusion": "failure",
            },
        ]
        with mock.patch.object(mod, "gh_run") as gh_run:
            deleted = mod.delete_superseded_action_required_runs(
                "kaamilbadami/yartchives",
                runs,
                "abc",
            )

        self.assertEqual(deleted, [10])
        gh_run.assert_called_once_with(
            "api",
            "--method", "DELETE",
            "repos/kaamilbadami/yartchives/actions/runs/10",
        )

    def test_action_required_quality_run_is_detected_for_manual_redispatch(self):
        self.assertTrue(
            mod.exact_head_quality_action_required(
                runs(conclusion="action_required"),
                "abc",
            )
        )
        self.assertFalse(
            mod.exact_head_quality_action_required(
                runs(conclusion="success"),
                "abc",
            )
        )

    def test_exact_head_quality_in_flight_detects_active_manual_run(self):
        active = [
            {
                "name": "Quality checks",
                "head_sha": "abc",
                "status": "in_progress",
                "conclusion": None,
            }
        ]
        self.assertTrue(mod.exact_head_quality_in_flight(active, "abc"))
        self.assertFalse(mod.exact_head_quality_in_flight(active, "other"))

    def test_pre_ci_policy_can_validate_non_ci_guards_before_redispatch(self):
        candidate = pr()
        ok, reason = mod.eligible_pr(
            candidate,
            repo="kaamilbadami/yartchives",
            issue=issue(),
            changed_paths=["app.js"],
            quality_runs=[],
            require_quality=False,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "eligible")

    def test_requires_exact_head_quality_success(self):
        candidate = pr()
        ok, _ = mod.eligible_pr(
            candidate,
            repo="kaamilbadami/yartchives",
            issue=issue(),
            changed_paths=["app.js"],
            quality_runs=runs(sha="older"),
        )
        self.assertFalse(ok)

    def test_behind_state_is_mergeable_after_nonoverlap_safety_check(self):
        self.assertTrue(
            mod.github_reports_safe_mergeability(
                {"mergeable": True, "mergeable_state": "behind"}
            )
        )
        self.assertFalse(
            mod.github_reports_safe_mergeability(
                {"mergeable": False, "mergeable_state": "dirty"}
            )
        )

    def test_stale_green_pr_skips_refresh_when_main_changed_unrelated_paths(self):
        comparison = {"behind_by": 3}
        self.assertFalse(
            mod.branch_refresh_required(
                comparison=comparison,
                pr_changed_paths=["apply-next-ui.js", "tests/apply-next-ui.test.cjs"],
                base_changed_paths=["scripts/build_feed.py", "tests/test_build_feed.py"],
            )
        )

    def test_stale_green_pr_refreshes_when_main_changed_overlapping_paths(self):
        comparison = {"behind_by": 1}
        self.assertTrue(
            mod.branch_refresh_required(
                comparison=comparison,
                pr_changed_paths=["apply-next-ui.js", "tests/apply-next-ui.test.cjs"],
                base_changed_paths=["apply-next-ui.js", "README.md"],
            )
        )

    def test_up_to_date_pr_never_requires_refresh(self):
        self.assertFalse(
            mod.branch_refresh_required(
                comparison={"behind_by": 0},
                pr_changed_paths=["app.js"],
                base_changed_paths=["app.js"],
            )
        )

    def test_comparison_changed_paths_filters_empty_filenames(self):
        self.assertEqual(
            mod.comparison_changed_paths(
                {
                    "files": [
                        {"filename": "app.js"},
                        {"filename": ""},
                        {},
                        {"filename": "tests/app.test.cjs"},
                    ]
                }
            ),
            {"app.js", "tests/app.test.cjs"},
        )

    def test_prioritizes_lifecycle_then_ci_then_normal_prs(self):
        pull_requests = [
            {"number": 10},
            {"number": 20},
            {"number": 30},
            {"number": 40},
        ]
        changed_paths = {
            10: ["app.js"],
            20: [".github/workflows/quality.yml"],
            30: ["scripts/dispatch_autonomous_issues.py"],
            40: [".github/workflows/autonomous-dispatch.yml"],
        }

        ordered = mod.prioritize_pull_requests(pull_requests, changed_paths)

        self.assertEqual([pr["number"] for pr in ordered], [30, 40, 20, 10])
        self.assertEqual(
            mod.pull_request_queue_priority(["scripts/auto_merge_agent_prs.py"]),
            0,
        )
        self.assertEqual(
            mod.pull_request_queue_priority([".github/workflows/update-feed.yml"]),
            1,
        )
        self.assertEqual(mod.pull_request_queue_priority(["app.js"]), 2)

    def test_maintenance_lane_accepts_small_dispatcher_fix_with_paired_test(self):
        candidate = pr(files=("scripts/dispatch_autonomous_issues.py", "tests/test_dispatch_autonomous_issues.py"))
        files = [
            {"filename": "scripts/dispatch_autonomous_issues.py", "changes": 12},
            {"filename": "tests/test_dispatch_autonomous_issues.py", "changes": 20},
        ]
        ok, reason = mod.maintenance_pr_eligible(
            candidate,
            repo="kaamilbadami/yartchives",
            files=files,
            quality_runs=runs(),
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "maintenance-eligible")

    def test_maintenance_lane_rejects_missing_test_mixed_and_large_changes(self):
        candidate = pr(files=("scripts/dispatch_autonomous_issues.py",))
        cases = (
            ([{"filename": "scripts/dispatch_autonomous_issues.py", "changes": 12}], "paired regression test"),
            ([
                {"filename": "scripts/dispatch_autonomous_issues.py", "changes": 12},
                {"filename": "tests/test_dispatch_autonomous_issues.py", "changes": 20},
                {"filename": "app.js", "changes": 1},
            ], "non-maintenance path"),
            ([
                {"filename": "scripts/dispatch_autonomous_issues.py", "changes": 200},
                {"filename": "tests/test_dispatch_autonomous_issues.py", "changes": 100},
            ], "diff is too large"),
        )
        for files, expected in cases:
            with self.subTest(expected=expected):
                ok, reason = mod.maintenance_pr_eligible(
                    candidate,
                    repo="kaamilbadami/yartchives",
                    files=files,
                    quality_runs=runs(),
                )
                self.assertFalse(ok)
                self.assertIn(expected, reason)

    def test_main_does_not_require_issue_link_for_maintenance_lane(self):
        source = MODULE_PATH.read_text()
        self.assertIn(
            "if issue_number is None and not maintenance_pre_ci:",
            source,
        )
        self.assertIn(
            "if issue is None and not maintenance_pre_ci:",
            source,
        )

    def test_control_plane_lane_accepts_small_workflow_change_with_contract_test(self):
        candidate = pr()
        files = [
            {"filename": ".github/workflows/coverage-automation.yml", "changes": 40},
            {"filename": "scripts/queue_coverage_gap.py", "changes": 120},
            {"filename": "tests/deploy-assets.test.cjs", "changes": 20},
            {"filename": "tests/test_queue_coverage_gap.py", "changes": 80},
        ]
        ok, reason = mod.control_plane_pr_eligible(
            candidate,
            repo="kaamilbadami/yartchives",
            files=files,
            quality_runs=runs(),
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "control-plane-eligible")

    def test_control_plane_lane_rejects_unpaired_or_non_allowlisted_changes(self):
        candidate = pr()
        cases = (
            (
                [{"filename": ".github/workflows/coverage-automation.yml", "changes": 40}],
                "paired regression test",
            ),
            (
                [
                    {"filename": ".github/workflows/coverage-automation.yml", "changes": 40},
                    {"filename": "tests/deploy-assets.test.cjs", "changes": 20},
                    {"filename": "app.js", "changes": 1},
                ],
                "non-allowlisted path",
            ),
        )
        for files, expected in cases:
            with self.subTest(expected=expected):
                ok, reason = mod.control_plane_pr_eligible(
                    candidate,
                    repo="kaamilbadami/yartchives",
                    files=files,
                    quality_runs=runs(),
                )
                self.assertFalse(ok)
                self.assertIn(expected, reason)

    def test_generated_artifacts_are_identified_for_repair(self):
        self.assertEqual(
            mod.generated_artifact_paths(
                [
                    "scripts/__pycache__/dispatch_autonomous_issues.cpython-312.pyc",
                    "__pycache__/test_issue_exists.cpython-312.pyc",
                    "app.js",
                ]
            ),
            [
                "scripts/__pycache__/dispatch_autonomous_issues.cpython-312.pyc",
                "__pycache__/test_issue_exists.cpython-312.pyc",
            ],
        )

    def test_maintenance_lane_never_authorizes_automerger_or_workflow_changes(self):
        candidate = pr()
        for path in (
            "scripts/auto_merge_agent_prs.py",
            ".github/workflows/auto-merge-agent-prs.yml",
            ".github/workflows/autonomous-dispatch.yml",
            "requirements.txt",
        ):
            with self.subTest(path=path):
                ok, _ = mod.maintenance_pr_eligible(
                    candidate,
                    repo="kaamilbadami/yartchives",
                    files=[{"filename": path, "changes": 1}],
                    quality_runs=runs(),
                )
                self.assertFalse(ok)

    def test_conflicted_pr_supersedes_only_with_trusted_autonomous_issue(self):
        self.assertTrue(mod.conflicted_pr_can_supersede(issue()))
        self.assertFalse(mod.conflicted_pr_can_supersede(None))
        self.assertFalse(
            mod.conflicted_pr_can_supersede(
                issue(labels=("autonomous-backlog",))
            )
        )
        self.assertFalse(
            mod.conflicted_pr_can_supersede(
                issue(
                    labels=(
                        "autonomous-backlog",
                        "jules-review-ready",
                        "needs-product-decision",
                    )
                )
            )
        )

    def test_broad_protected_pr_is_supersession_candidate(self):
        candidate = pr()
        original_issue = issue()
        files = [
            {"filename": "app.js", "changes": 700},
            {"filename": ".github/workflows/quality.yml", "changes": 400},
        ]
        ok, reason = mod.supersession_candidate(
            candidate,
            repo="kaamilbadami/yartchives",
            issue=original_issue,
            files=files,
        )
        self.assertTrue(ok)
        self.assertIn("superseded", reason)

    def test_bounded_protected_pr_is_not_superseded(self):
        candidate = pr()
        ok, reason = mod.supersession_candidate(
            candidate,
            repo="kaamilbadami/yartchives",
            issue=issue(),
            files=[
                {"filename": "scripts/dispatch_autonomous_issues.py", "changes": 20},
                {"filename": "tests/test_dispatch_autonomous_issues.py", "changes": 20},
            ],
        )
        self.assertFalse(ok)
        self.assertIn("bounded", reason)

    def test_replacement_issue_preserves_original_acceptance_criteria(self):
        original = {
            "title": "Benchmark Apply Next interaction and ranking performance",
            "body": "<!-- autonomous-task -->\npriority: P2\narea: performance\nautonomous: true\n\n## Acceptance criteria\n- Measure ranking.",
        }
        body = mod.replacement_issue_body(original, 232)
        self.assertIn("## Acceptance criteria\n- Measure ranking.", body)
        self.assertIn("<!-- supersedes-stale-pr: 232 -->", body)
        self.assertIn("Do not port the stale branch wholesale", body)

    def test_conflict_replacement_preserves_acceptance_criteria_and_is_idempotent(self):
        original = {
            "title": "Add clear Apply Next states",
            "body": "## Acceptance criteria\n- Preserve saved state.",
        }
        body = mod.conflict_replacement_issue_body(original, 235, "main")
        self.assertIn("## Acceptance criteria\n- Preserve saved state.", body)
        self.assertIn("<!-- supersedes-stale-pr: 235 -->", body)
        self.assertIn("could not be updated onto current main without conflicts", body)
        self.assertIn("Do not port or resolve the stale branch wholesale", body)

        existing = {"number": 301, "body": "<!-- supersedes-stale-pr: 235 -->"}
        with mock.patch.object(mod, "find_existing_replacement_issue", return_value=existing), mock.patch.object(mod, "gh_json") as gh_json:
            found = mod.create_or_find_conflict_replacement_issue(
                "kaamilbadami/yartchives", original, 235, "main"
            )
        self.assertIs(found, existing)
        gh_json.assert_not_called()

    def test_supersede_conflicted_pr_closes_stale_pr_and_original_issue(self):
        original = {"number": 225, "title": "Empty states", "body": "criteria"}
        candidate = {"number": 235}
        calls = []
        with mock.patch.object(
            mod,
            "create_or_find_conflict_replacement_issue",
            return_value={"number": 301},
        ), mock.patch.object(mod, "gh_run", side_effect=lambda *args: calls.append(args)):
            replacement = mod.supersede_conflicted_pull_request(
                "kaamilbadami/yartchives", candidate, original, "main"
            )
        self.assertEqual(replacement, 301)
        self.assertTrue(any(call[:4] == ("api", "--method", "PATCH", "repos/kaamilbadami/yartchives/pulls/235") for call in calls))
        self.assertTrue(any(call[:4] == ("api", "--method", "PATCH", "repos/kaamilbadami/yartchives/issues/225") for call in calls))

    def test_existing_replacement_marker_prevents_duplicate_issue_creation(self):
        existing = {
            "number": 300,
            "body": "<!-- supersedes-stale-pr: 232 -->",
        }
        with mock.patch.object(mod, "gh_paginated_json", return_value=[existing]):
            found = mod.find_existing_replacement_issue("kaamilbadami/yartchives", 232)
        self.assertIs(found, existing)

    def test_supersede_closes_pr_and_original_issue_after_replacement_exists(self):
        original = {"number": 155, "title": "Performance", "body": "<!-- autonomous-task -->"}
        candidate = {"number": 232}
        calls = []
        with mock.patch.object(
            mod,
            "create_or_find_replacement_issue",
            return_value={"number": 300},
        ), mock.patch.object(mod, "gh_run", side_effect=lambda *args: calls.append(args)):
            replacement = mod.supersede_pull_request(
                "kaamilbadami/yartchives", candidate, original
            )
        self.assertEqual(replacement, 300)
        self.assertTrue(any(call[:4] == ("api", "--method", "PATCH", "repos/kaamilbadami/yartchives/pulls/232") for call in calls))
        self.assertTrue(any(call[:4] == ("api", "--method", "PATCH", "repos/kaamilbadami/yartchives/issues/155") for call in calls))

    def test_priority_does_not_bypass_protected_path_guard(self):
        candidate = pr()
        ok, reason = mod.eligible_pr(
            candidate,
            repo="kaamilbadami/yartchives",
            issue=issue(),
            changed_paths=["scripts/dispatch_autonomous_issues.py"],
            quality_runs=runs(),
        )
        self.assertFalse(ok)
        self.assertIn("protected path changed", reason)

    def test_blocks_control_plane_and_benchmark_changes(self):
        for path in (
            ".github/workflows/quality.yml",
            "scripts/dispatch_autonomous_issues.py",
            "scripts/triage_workflow_failures.py",
            "scripts/auto_merge_agent_prs.py",
            "requirements.txt",
            "audit/samples/northeast-midatlantic-cs-2026-09-17.json",
        ):
            with self.subTest(path=path):
                self.assertEqual(mod.blocked_changed_paths([path]), [path])

    def test_requires_terminal_agent_label_and_rejects_product_decisions(self):
        candidate = pr()
        for labels in (
            ("autonomous-backlog",),
            ("autonomous-backlog", "jules-review-ready", "needs-product-decision"),
            ("jules-review-ready",),
        ):
            with self.subTest(labels=labels):
                ok, _ = mod.eligible_pr(
                    candidate,
                    repo="kaamilbadami/yartchives",
                    issue=issue(labels=labels),
                    changed_paths=["app.js"],
                    quality_runs=runs(),
                )
                self.assertFalse(ok)

    def test_rejects_forks_drafts_and_unlinked_prs(self):
        cases = (
            pr(repo="someone/fork"),
            pr(draft=True),
            pr(body="Related to #10"),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                ok, _ = mod.eligible_pr(
                    candidate,
                    repo="kaamilbadami/yartchives",
                    issue=issue(),
                    changed_paths=["app.js"],
                    quality_runs=runs(),
                )
                self.assertFalse(ok)

    def test_recovers_missing_closing_link_from_trusted_jules_completion(self):
        review_issue = issue()
        comments = {
            10: [
                {
                    "user": {"login": "github-actions[bot]"},
                    "body": (
                        "Jules completed session `session-1` and released this automation slot.\n\n"
                        "Pull request: https://github.com/kaamilbadami/yartchives/pull/235"
                    ),
                }
            ]
        }
        mapping = mod.review_ready_issue_by_pr(
            [review_issue],
            repo="kaamilbadami/yartchives",
            load_comments=lambda number: comments[number],
        )

        self.assertIs(mapping[235], review_issue)
        normalized = mod.ensure_closing_link(
            {"body": "Jules generated this pull request."},
            10,
        )
        self.assertEqual(
            normalized,
            "Jules generated this pull request.\n\nCloses #10",
        )
        self.assertEqual(mod.linked_issue_number(normalized), 10)

    def test_untrusted_completion_comment_cannot_authorize_pr(self):
        review_issue = issue()
        mapping = mod.review_ready_issue_by_pr(
            [review_issue],
            repo="kaamilbadami/yartchives",
            load_comments=lambda number: [
                {
                    "user": {"login": "someone-else"},
                    "body": (
                        "Jules completed session `fake` and released this automation slot.\n\n"
                        "Pull request: https://github.com/kaamilbadami/yartchives/pull/235"
                    ),
                }
            ],
        )
        self.assertEqual(mapping, {})

    def test_completion_link_requires_exact_repository(self):
        comments = [
            {
                "user": {"login": "github-actions[bot]"},
                "body": (
                    "Jules completed session `session-1` and released this automation slot.\n\n"
                    "Pull request: https://github.com/other/repo/pull/235"
                ),
            }
        ]
        self.assertIsNone(
            mod.completed_jules_pr_number(comments, "kaamilbadami/yartchives")
        )

    def test_update_branch_uses_token_push_not_update_branch_api(self):
        ok = mock.Mock(returncode=0, stdout="", stderr="", args=["git"])
        rev_parse = mock.Mock(
            returncode=0,
            stdout="abc\n",
            stderr="",
            args=["git", "rev-parse"],
        )
        with mock.patch.object(
            mod.subprocess,
            "run",
            side_effect=[ok, rev_parse, ok, ok, ok],
        ) as run:
            updated, detail = mod.update_pull_request_branch(
                "kaamilbadami/yartchives",
                196,
                "abc",
                "feature/issue-196",
                "main",
            )

        self.assertTrue(updated)
        self.assertEqual(detail, "")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertFalse(
            any(
                command[:4] == ["gh", "api", "--method", "PUT"]
                for command in commands
            )
        )
        self.assertIn(
            [
                "git",
                "push",
                "origin",
                "HEAD:refs/heads/feature/issue-196",
                "--force-with-lease=refs/heads/feature/issue-196:abc",
            ],
            commands,
        )

    def test_update_branch_merge_conflict_isolated_as_nonfatal(self):
        ok = mock.Mock(returncode=0, stdout="", stderr="", args=["git"])
        rev_parse = mock.Mock(
            returncode=0,
            stdout="abc\n",
            stderr="",
            args=["git", "rev-parse"],
        )
        conflict = mock.Mock(
            returncode=1,
            stdout="CONFLICT (content): Merge conflict in app.js",
            stderr="Automatic merge failed; fix conflicts and then commit the result.",
            args=["git", "merge"],
        )
        with mock.patch.object(
            mod.subprocess,
            "run",
            side_effect=[ok, rev_parse, ok, conflict, ok],
        ):
            updated, detail = mod.update_pull_request_branch(
                "kaamilbadami/yartchives",
                196,
                "abc",
                "feature/issue-196",
                "main",
            )
        self.assertFalse(updated)
        self.assertIn("Merge conflict", detail)

    def test_update_branch_non_conflict_error_still_fails_loudly(self):
        fetch_error = mock.Mock(
            returncode=1,
            stdout="",
            stderr="fatal: authentication failed",
            args=["git", "fetch"],
        )
        with mock.patch.object(mod.subprocess, "run", return_value=fetch_error):
            with self.assertRaises(subprocess.CalledProcessError):
                mod.update_pull_request_branch(
                    "kaamilbadami/yartchives",
                    196,
                    "abc",
                    "feature/issue-196",
                    "main",
                )

    def test_update_branch_rejects_head_movement_before_push(self):
        ok = mock.Mock(returncode=0, stdout="", stderr="", args=["git"])
        moved = mock.Mock(
            returncode=0,
            stdout="new-head\n",
            stderr="",
            args=["git", "rev-parse"],
        )
        with mock.patch.object(
            mod.subprocess,
            "run",
            side_effect=[ok, moved],
        ):
            with self.assertRaises(RuntimeError):
                mod.update_pull_request_branch(
                    "kaamilbadami/yartchives",
                    196,
                    "abc",
                    "feature/issue-196",
                    "main",
                )

    def test_guarded_squash_merge_uses_expected_head_sha(self):
        ok = mock.Mock(returncode=0, stdout='{"merged":true}', stderr="", args=["gh"])
        with mock.patch.object(mod.subprocess, "run", return_value=ok) as run:
            merged, detail = mod.try_guarded_squash_merge(
                "kaamilbadami/yartchives",
                400,
                "abc123",
            )
        self.assertTrue(merged)
        self.assertEqual(detail, '{"merged":true}')
        self.assertEqual(
            run.call_args.args[0],
            [
                "gh", "api", "--method", "PUT",
                "repos/kaamilbadami/yartchives/pulls/400/merge",
                "-f", "merge_method=squash",
                "-f", "sha=abc123",
            ],
        )

    def test_guarded_squash_merge_returns_rejection_without_crashing(self):
        rejected = mock.Mock(
            returncode=1,
            stdout="",
            stderr="HTTP 409: Head branch was modified",
            args=["gh"],
        )
        with mock.patch.object(mod.subprocess, "run", return_value=rejected):
            merged, detail = mod.try_guarded_squash_merge(
                "kaamilbadami/yartchives",
                400,
                "abc123",
            )
        self.assertFalse(merged)
        self.assertIn("409", detail)

    def test_main_supersedes_autonomous_pr_when_branch_refresh_conflicts(self):
        source = MODULE_PATH.read_text()
        self.assertIn(
            "replacement_number = supersede_conflicted_pull_request(",
            source,
        )
        self.assertIn(
            'f"Superseded conflicted PR #{number} with fresh current-main "',
            source,
        )
        self.assertIn(
            'f"BLOCKED_REQUIRES_DECISION PR #{number}: branch conflicts with "',
            source,
        )
        self.assertNotIn(
            'f"Skipping PR #{number}: maintenance branch cannot be updated "',
            source,
        )

    def test_main_repairs_generated_artifacts_before_lane_classification(self):
        source = MODULE_PATH.read_text()
        repair_index = source.index("remove_generated_artifacts(")
        maintenance_index = source.index("maintenance_pre_ci, maintenance_reason")
        self.assertLess(repair_index, maintenance_index)
        self.assertIn("Repaired PR #{number} by removing generated artifacts", source)

    def test_main_uses_explicit_blocked_disposition_instead_of_silent_skip(self):
        source = MODULE_PATH.read_text()
        self.assertIn("BLOCKED_REQUIRES_DECISION PR #{number}", source)

    def test_main_continues_past_in_flight_and_redispatched_ci(self):
        source = MODULE_PATH.read_text()
        self.assertIn(
            'print(f"PR #{number} already has exact-head Quality checks in flight.")\n                continue',
            source,
        )
        self.assertIn(
            '"exact-head run was missing or required manual approval."\n                )\n                continue',
            source,
        )
        self.assertIn(
            '"Quality checks because main changed overlapping paths."\n                )\n                continue',
            source,
        )

    def test_transient_unknown_mergeability_uses_guarded_merge_after_nonoverlap_proof(self):
        source = MODULE_PATH.read_text()
        self.assertIn("stale_nonoverlap_safe = True", source)
        self.assertIn(
            "if stale_nonoverlap_safe:\n                    merged, detail = try_guarded_squash_merge(",
            source,
        )
        self.assertIn(
            "through guarded merge fallback while GitHub mergeability was recomputing.",
            source,
        )
        self.assertIn(
            'BLOCKED_REQUIRES_DECISION PR #{number}: GitHub reports mergeable={mergeable}',
            source,
        )
        self.assertNotIn(
            'Skipping PR #{number}: GitHub does not currently report it as safely mergeable.',
            source,
        )

    def test_main_drains_all_eligible_prs_instead_of_returning_after_first_merge(self):
        source = MODULE_PATH.read_text()
        merge_log = 'print(f"Squash-merged eligible autonomous PR #{number}.")'
        merge_index = source.index(merge_log)
        post_merge = source[merge_index:merge_index + 220]

        self.assertIn("merged_count += 1", post_merge)
        self.assertNotIn("return 0", post_merge)
        self.assertIn(
            'print(f"Squash-merged {merged_count} eligible autonomous pull request(s).")',
            source,
        )

    def test_successful_merge_queues_one_followup_scan(self):
        source = MODULE_PATH.read_text()
        self.assertIn(
            '"workflow", "run", "auto-merge-agent-prs.yml",\n'
            '            "--repo", repo,',
            source,
        )
        self.assertIn(
            '"Queued one follow-up auto-merge scan because this run advanced main; "',
            source,
        )
        followup_index = source.index('"workflow", "run", "auto-merge-agent-prs.yml"')
        merged_guard_index = source.index("if merged_count:")
        no_merge_index = source.index(
            'print("No autonomous pull request is currently eligible for automatic merge.")'
        )
        self.assertGreater(followup_index, merged_guard_index)
        self.assertLess(followup_index, no_merge_index)

    def test_codex_review_ready_is_also_terminal(self):
        self.assertTrue(
            mod.autonomous_issue_ready(
                issue(labels=("autonomous-backlog", "codex-review-ready"))
            )
        )


if __name__ == "__main__":
    unittest.main()
