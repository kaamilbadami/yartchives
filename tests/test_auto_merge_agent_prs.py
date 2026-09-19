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

    def test_update_branch_merge_conflict_isolated_as_nonfatal(self):
        result = mock.Mock(
            returncode=1,
            stdout='{"message":"merge conflict between base and head","status":422}',
            stderr="gh: merge conflict between base and head (HTTP 422)",
            args=["gh", "api"],
        )
        with mock.patch.object(mod.subprocess, "run", return_value=result):
            updated, detail = mod.update_pull_request_branch(
                "kaamilbadami/yartchives", 196, "abc"
            )
        self.assertFalse(updated)
        self.assertIn("merge conflict between base and head", detail)

    def test_update_branch_non_conflict_error_still_fails_loudly(self):
        result = mock.Mock(
            returncode=1,
            stdout="",
            stderr="gh: authentication failed (HTTP 401)",
            args=["gh", "api"],
        )
        with mock.patch.object(mod.subprocess, "run", return_value=result):
            with self.assertRaises(subprocess.CalledProcessError):
                mod.update_pull_request_branch(
                    "kaamilbadami/yartchives", 196, "abc"
                )

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
            '"Quality checks on the updated branch."\n            )\n            continue',
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

    def test_codex_review_ready_is_also_terminal(self):
        self.assertTrue(
            mod.autonomous_issue_ready(
                issue(labels=("autonomous-backlog", "codex-review-ready"))
            )
        )


if __name__ == "__main__":
    unittest.main()
