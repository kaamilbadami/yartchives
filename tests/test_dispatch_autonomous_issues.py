import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "dispatch_autonomous_issues.py"
SPEC = importlib.util.spec_from_file_location("dispatch_autonomous_issues", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


def issue(number, title, *, body="", labels=(), state="open"):
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": state,
        "labels": [{"name": label} for label in labels],
    }


def task_body(priority, area, autonomous=True):
    return (
        "<!-- autonomous-task -->\n"
        f"priority: {priority}\n"
        f"area: {area}\n"
        f"autonomous: {'true' if autonomous else 'false'}\n"
    )


class AutonomousDispatcherTests(unittest.TestCase):
    def test_selects_highest_priority_safe_tasks_without_area_overlap(self):
        issues = [
            issue(10, "P2 frontend", body=task_body("P2", "frontend-state")),
            issue(11, "P1 frontend", body=task_body("P1", "frontend-state")),
            issue(12, "P1 coverage", body=task_body("P1", "coverage")),
        ]
        selected = mod.select_tasks(issues, max_active=2)
        self.assertEqual([task.number for task in selected], [11, 12])

    def test_real_jules_sessions_count_against_wip_limit(self):
        issues = [
            issue(1, "active feed", body=task_body("P1", "feed"), labels=("jules", "jules-session")),
            issue(2, "active quality", body=task_body("P1", "quality"), labels=("jules", "jules-session")),
            issue(3, "roadmap", body=task_body("P1", "frontend-state")),
        ]
        self.assertEqual(mod.select_tasks(issues, max_active=2), [])

    def test_legacy_jules_labels_without_session_do_not_consume_wip_or_block_retry(self):
        issues = [
            issue(
                1,
                "stale dispatch",
                body=task_body("P1", "frontend-state"),
                labels=("jules", "agent-ready", "autonomous-backlog"),
            ),
            issue(2, "coverage", body=task_body("P1", "coverage")),
        ]
        selected = mod.select_tasks(issues, max_active=2)
        self.assertEqual([task.number for task in selected], [1, 2])

    def test_codex_reservation_blocks_jules_without_consuming_jules_wip(self):
        issues = [
            issue(
                1,
                "reserved evidence",
                body=task_body("P1", "evidence"),
                labels=("codex", "codex-worker-1"),
            ),
            issue(2, "same evidence", body=task_body("P0", "evidence")),
            issue(3, "frontend", body=task_body("P1", "frontend-state")),
            issue(4, "feed quality", body=task_body("P1", "feed-quality")),
        ]

        selected = mod.select_tasks(issues, max_active=2)

        self.assertEqual([task.number for task in selected], [3, 4])

    def test_worker_specific_codex_label_reserves_task_without_general_label(self):
        issues = [
            issue(
                1,
                "reserved worker two",
                body=task_body("P1", "evidence"),
                labels=("codex-worker-2",),
            ),
            issue(2, "same evidence", body=task_body("P0", "evidence")),
            issue(3, "different area", body=task_body("P1", "performance")),
        ]

        selected = mod.select_tasks(issues, max_active=2)

        self.assertEqual([task.number for task in selected], [3])

    def test_non_backlog_jules_work_does_not_consume_backlog_wip(self):
        issues = [
            issue(
                1,
                "[workflow failure] Update opportunity feed: Validate code",
                labels=("workflow-failure", "agent-ready", "jules"),
            ),
            issue(
                2,
                "[workflow failure] Update opportunity feed: Validate generated feed",
                labels=("workflow-failure", "agent-ready", "jules"),
            ),
            issue(3, "roadmap", body=task_body("P1", "frontend-state")),
        ]
        selected = mod.select_tasks(issues, max_active=2)
        self.assertEqual([task.number for task in selected], [3])

    def test_active_area_blocks_overlapping_task_but_allows_other_area(self):
        issues = [
            issue(
                1,
                "active frontend",
                body=task_body("P1", "frontend-state"),
                labels=("jules", "jules-session"),
            ),
            issue(2, "another frontend", body=task_body("P0", "frontend-state")),
            issue(3, "coverage", body=task_body("P1", "coverage")),
        ]
        selected = mod.select_tasks(issues, max_active=2)
        self.assertEqual([task.number for task in selected], [3])

    def test_blocked_or_product_decision_tasks_are_not_dispatched(self):
        issues = [
            issue(1, "blocked", body=task_body("P0", "feed"), labels=("blocked",)),
            issue(2, "decision", body=task_body("P0", "ranking"), labels=("needs-product-decision",)),
            issue(3, "safe", body=task_body("P1", "coverage")),
        ]
        selected = mod.select_tasks(issues, max_active=2)
        self.assertEqual([task.number for task in selected], [3])

    def test_finds_connected_jules_source_by_github_repo(self):
        calls = []

        def fake_get(api_key, path):
            calls.append((api_key, path))
            return {
                "sources": [
                    {
                        "name": "sources/github/kaamilbadami/yartchives",
                        "githubRepo": {"owner": "kaamilbadami", "repo": "yartchives"},
                    }
                ]
            }

        source = mod.find_jules_source("secret", "kaamilbadami/yartchives", fake_get)
        self.assertEqual(source, "sources/github/kaamilbadami/yartchives")
        self.assertEqual(calls[0][0], "secret")
        self.assertIn("/sources?pageSize=100", calls[0][1])

    def test_create_session_uses_main_auto_pr_and_full_issue_context(self):
        task = mod.Task(
            149,
            "Make Mark Applied update Apply Next immediately",
            task_body("P1", "apply-next-ui") + "\nFix the interaction.",
            "P1",
            "apply-next-ui",
            frozenset(),
        )
        captured = {}

        def fake_post(api_key, path, *, method="GET", payload=None):
            captured.update(api_key=api_key, path=path, method=method, payload=payload)
            return {"id": "abc123", "url": "https://jules.google.com/session/abc123"}

        session = mod.create_jules_session(
            "secret",
            "sources/github/kaamilbadami/yartchives",
            "kaamilbadami/yartchives",
            task,
            fake_post,
        )
        self.assertEqual(session["id"], "abc123")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/sessions")
        self.assertEqual(captured["payload"]["automationMode"], "AUTO_CREATE_PR")
        self.assertFalse(captured["payload"]["requirePlanApproval"])
        self.assertEqual(
            captured["payload"]["sourceContext"]["githubRepoContext"]["startingBranch"],
            "main",
        )
        self.assertIn("Fix the interaction.", captured["payload"]["prompt"])
        self.assertIn("Closes #149", captured["payload"]["prompt"])

    def test_failed_session_creation_does_not_mark_issue_active(self):
        task = mod.Task(149, "Task", task_body("P1", "frontend"), "P1", "frontend", frozenset())
        gh_calls = []

        def fail_create(*args, **kwargs):
            raise RuntimeError("quota exceeded")

        with self.assertRaisesRegex(RuntimeError, "quota exceeded"):
            mod.dispatch_task(
                task,
                repo="kaamilbadami/yartchives",
                api_key="secret",
                source_name="source",
                create_session=fail_create,
                run_gh=lambda *args: gh_calls.append(args),
            )
        self.assertEqual(gh_calls, [])

    def test_successful_session_creation_marks_issue_active_and_links_session(self):
        task = mod.Task(149, "Task", task_body("P1", "frontend"), "P1", "frontend", frozenset())
        gh_calls = []
        session = mod.dispatch_task(
            task,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            source_name="source",
            create_session=lambda *args, **kwargs: {
                "id": "abc123",
                "url": "https://jules.google.com/session/abc123",
            },
            run_gh=lambda *args: gh_calls.append(args),
        )
        self.assertEqual(session["id"], "abc123")
        self.assertIn("jules-session", gh_calls[0])
        self.assertIn("jules", gh_calls[0])
        self.assertIn("agent-ready", gh_calls[0])
        self.assertIn("autonomous-backlog", gh_calls[0])
        self.assertIn("https://jules.google.com/session/abc123", gh_calls[1][-1])
        self.assertIn("<!-- jules-session-id: abc123 -->", gh_calls[1][-1])

    def test_session_id_parser_supports_new_marker_and_legacy_comment(self):
        self.assertEqual(
            mod.session_id_from_comments(
                [{"body": "<!-- jules-session-id: abc123 -->\nCreated."}]
            ),
            "abc123",
        )
        self.assertEqual(
            mod.session_id_from_comments(
                [{"body": "Autonomous dispatcher created Jules session 'legacy456' for this task."}]
            ),
            "legacy456",
        )

    def test_completed_session_releases_slot_and_surfaces_pull_request(self):
        issues = [
            issue(
                149,
                "active frontend",
                body=task_body("P1", "apply-next-ui"),
                labels=("jules", "jules-session", "agent-ready"),
            ),
            issue(154, "feed quality", body=task_body("P1", "feed-quality")),
        ]
        gh_calls = []

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: [
                {"body": "Autonomous dispatcher created Jules session 'abc123' for this task."}
            ],
            get_session=lambda api_key, path: {
                "id": "abc123",
                "state": "COMPLETED",
                "outputs": [
                    {
                        "pullRequest": {
                            "url": "https://github.com/kaamilbadami/yartchives/pull/999"
                        }
                    }
                ],
            },
            run_gh=lambda *args: gh_calls.append(args),
        )

        labels = mod.label_names(issues[0])
        self.assertNotIn("jules-session", labels)
        self.assertNotIn("jules", labels)
        self.assertIn("jules-review-ready", labels)
        self.assertIn("jules-review-ready", gh_calls[0])
        self.assertIn("https://github.com/kaamilbadami/yartchives/pull/999", gh_calls[1][-1])
        self.assertEqual(
            [task.number for task in mod.select_tasks(issues, max_active=2)],
            [154],
        )

    def test_failed_session_releases_slot_without_becoming_retry_candidate(self):
        issues = [
            issue(
                152,
                "active feed",
                body=task_body("P1", "feed"),
                labels=("jules", "jules-session"),
            ),
            issue(154, "feed quality", body=task_body("P1", "feed-quality")),
        ]
        gh_calls = []

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: [{"body": "<!-- jules-session-id: failed1 -->"}],
            get_session=lambda api_key, path: {"id": "failed1", "state": "FAILED"},
            run_gh=lambda *args: gh_calls.append(args),
        )

        labels = mod.label_names(issues[0])
        self.assertIn("jules-failed", labels)
        self.assertNotIn("jules-session", labels)
        selected = mod.select_tasks(issues, max_active=2)
        self.assertEqual([task.number for task in selected], [154])

    def test_nonterminal_session_remains_active(self):
        issues = [
            issue(
                149,
                "active frontend",
                body=task_body("P1", "apply-next-ui"),
                labels=("jules", "jules-session"),
            ),
            issue(154, "feed quality", body=task_body("P1", "feed-quality")),
        ]
        gh_calls = []

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: [{"body": "<!-- jules-session-id: abc123 -->"}],
            get_session=lambda api_key, path: {"id": "abc123", "state": "IN_PROGRESS"},
            run_gh=lambda *args: gh_calls.append(args),
        )

        self.assertEqual(gh_calls, [])
        self.assertIn("jules-session", mod.label_names(issues[0]))

    def test_missing_session_id_keeps_slot_occupied_to_avoid_duplicate_dispatch(self):
        issues = [
            issue(
                149,
                "active frontend",
                body=task_body("P1", "apply-next-ui"),
                labels=("jules", "jules-session"),
            )
        ]
        gh_calls = []

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: [],
            get_session=lambda *args: self.fail("session API should not be called"),
            run_gh=lambda *args: gh_calls.append(args),
        )

        self.assertEqual(gh_calls, [])
        self.assertIn("jules-session", mod.label_names(issues[0]))

    def test_paginated_issue_pages_are_flattened_without_json_stream_assumptions(self):
        pages = [[{"number": 1}, {"number": 2}], [{"number": 3}]]
        self.assertEqual(
            mod.flatten_paginated_pages(pages),
            [{"number": 1}, {"number": 2}, {"number": 3}],
        )

    def test_paginated_issue_pages_reject_non_array_pages(self):
        with self.assertRaises(TypeError):
            mod.flatten_paginated_pages([[{"number": 1}], {"number": 2}])

    def test_non_autonomous_or_unstructured_issues_are_ignored(self):
        issues = [
            issue(1, "ordinary issue"),
            issue(2, "not approved", body=task_body("P0", "feed", autonomous=False)),
            issue(3, "safe", body=task_body("P2", "coverage")),
        ]
        selected = mod.select_tasks(issues, max_active=2)
        self.assertEqual([task.number for task in selected], [3])


if __name__ == "__main__":
    unittest.main()
