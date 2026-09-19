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


def task_body(priority, area, autonomous=True, resources=None, depends_on=None):
    resource_line = f"resources: {resources}\n" if resources else ""
    dependency_line = f"depends_on: {depends_on}\n" if depends_on else ""
    return (
        "<!-- autonomous-task -->\n"
        f"priority: {priority}\n"
        f"area: {area}\n"
        f"{resource_line}"
        f"{dependency_line}"
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

    def test_feedback_waiting_session_reserves_wip_and_overlap_locks(self):
        issues = [
            issue(
                1,
                "paused frontend",
                body=task_body("P1", "apply-next-ui"),
                labels=("jules", "jules-needs-feedback"),
            ),
            issue(2, "same frontend", body=task_body("P0", "apply-next-ui")),
            issue(3, "coverage", body=task_body("P1", "coverage")),
            issue(4, "performance", body=task_body("P1", "performance")),
        ]

        selected = mod.select_tasks(issues, max_active=2)

        self.assertEqual([task.number for task in selected], [3])

    def test_shared_resource_lock_blocks_cross_area_overlap(self):
        issues = [
            issue(
                1,
                "active feed",
                body=task_body("P1", "feed"),
                labels=("jules", "jules-session"),
            ),
            issue(2, "dedupe", body=task_body("P0", "dedupe")),
            issue(3, "coverage", body=task_body("P1", "coverage")),
        ]

        selected = mod.select_tasks(issues, max_active=3)

        self.assertEqual([task.number for task in selected], [3])

    def test_explicit_resource_metadata_blocks_unrelated_areas(self):
        issues = [
            issue(
                1,
                "active custom",
                body=task_body("P1", "alpha", resources="shared-hot-file"),
                labels=("jules", "jules-session"),
            ),
            issue(
                2,
                "other area same resource",
                body=task_body("P0", "beta", resources="shared-hot-file"),
            ),
            issue(3, "independent", body=task_body("P1", "gamma")),
        ]

        selected = mod.select_tasks(issues, max_active=3)

        self.assertEqual([task.number for task in selected], [3])

    def test_default_wip_allows_five_distinct_areas(self):
        issues = [
            issue(1, "feed", body=task_body("P1", "feed")),
            issue(2, "coverage", body=task_body("P1", "coverage")),
            issue(3, "performance", body=task_body("P1", "performance")),
            issue(4, "evidence", body=task_body("P1", "evidence")),
            issue(5, "automation", body=task_body("P1", "automation")),
            issue(6, "dedupe", body=task_body("P1", "dedupe")),
        ]

        selected = mod.select_tasks(issues)

        self.assertEqual(mod.MAX_ACTIVE, 5)
        self.assertEqual([task.number for task in selected], [1, 2, 3, 4, 5])

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

    def test_failed_session_surfaces_jules_failure_diagnostics(self):
        issues = [
            issue(
                176,
                "listing lifecycle",
                body=task_body("P1", "listing-lifecycle"),
                labels=("jules", "jules-session"),
            )
        ]
        gh_calls = []

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: [{"body": "<!-- jules-session-id: failed1 -->"}],
            get_session=lambda api_key, path: {
                "id": "failed1",
                "state": "FAILED",
                "failureReason": "Internal execution stopped after feedback.",
            },
            load_activities=lambda session_id: [
                {
                    "createTime": "2026-09-18T23:44:00Z",
                    "agentMessaged": {"agentMessage": "Applying the narrowed generic fix."},
                },
                {
                    "createTime": "2026-09-18T23:45:00Z",
                    "error": {"message": "Workspace became unavailable."},
                },
            ],
            run_gh=lambda *args: gh_calls.append(args),
        )

        comment = gh_calls[1][-1]
        self.assertIn("Failure diagnostics:", comment)
        self.assertIn("Internal execution stopped after feedback.", comment)
        self.assertIn("Workspace became unavailable.", comment)
        self.assertIn("jules-retry-ready", mod.label_names(issues[0]))
        self.assertNotIn("jules-failed", mod.label_names(issues[0]))
        self.assertIn("<!-- jules-retry-from: failed1 -->", comment)

    def test_failed_session_still_reconciles_when_diagnostics_cannot_be_loaded(self):
        issues = [
            issue(
                178,
                "frontend state",
                body=task_body("P1", "frontend-state"),
                labels=("jules", "jules-session"),
            )
        ]
        gh_calls = []

        def fail_activities(session_id):
            raise RuntimeError("Jules activities endpoint unavailable")

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: [{"body": "<!-- jules-session-id: failed2 -->"}],
            get_session=lambda api_key, path: {"id": "failed2", "state": "FAILED"},
            load_activities=fail_activities,
            run_gh=lambda *args: gh_calls.append(args),
        )

        self.assertIn("jules-failed", mod.label_names(issues[0]))
        self.assertIn(
            "Could not load Jules failure diagnostics: Jules activities endpoint unavailable",
            gh_calls[1][-1],
        )

    def test_feedback_waiting_session_releases_slot_and_surfaces_latest_question(self):
        issues = [
            issue(
                151,
                "freshness",
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
            load_comments=lambda number: [{"body": "<!-- jules-session-id: ask1 -->"}],
            get_session=lambda api_key, path: {
                "id": "ask1",
                "state": "AWAITING_USER_FEEDBACK",
                "url": "https://jules.google.com/session/ask1",
            },
            load_activities=lambda session_id: [
                {
                    "createTime": "2026-09-18T22:00:00Z",
                    "agentMessaged": {"agentMessage": "Older status."},
                },
                {
                    "createTime": "2026-09-18T22:01:00Z",
                    "agentMessaged": {
                        "agentMessage": "Should freshness use posted_at or discovered_at?"
                    },
                },
            ],
            run_gh=lambda *args: gh_calls.append(args),
        )

        labels = mod.label_names(issues[0])
        self.assertNotIn("jules-session", labels)
        self.assertIn("jules-needs-feedback", labels)
        self.assertIn("jules", labels)
        self.assertIn("jules-needs-feedback", gh_calls[0])
        self.assertIn(
            "Should freshness use posted_at or discovered_at?",
            gh_calls[1][-1],
        )
        self.assertEqual(
            [task.number for task in mod.select_tasks(issues, max_active=2)],
            [154],
        )

    def test_explicit_github_feedback_is_forwarded_to_waiting_session(self):
        issues = [
            issue(
                151,
                "freshness",
                body=task_body("P1", "apply-next-ui"),
                labels=("jules", "jules-needs-feedback", "agent-ready"),
            )
        ]
        gh_calls = []
        sent = []
        comments = [
            {"id": 1, "body": "<!-- jules-session-id: ask1 -->"},
            {
                "id": 22,
                "body": (
                    "<!-- jules-feedback: ask1 -->\n"
                    "Keep Recommended as default and make Newest transient UI state."
                ),
            },
        ]

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: comments,
            get_session=lambda api_key, path: {
                "id": "ask1",
                "state": "AWAITING_USER_FEEDBACK",
            },
            send_feedback=lambda session_id, prompt: sent.append((session_id, prompt)),
            run_gh=lambda *args: gh_calls.append(args),
        )

        self.assertEqual(
            sent,
            [("ask1", "Keep Recommended as default and make Newest transient UI state.")],
        )
        self.assertIn("<!-- jules-feedback-sent: 22 -->", gh_calls[0][-1])
        self.assertIn("jules-needs-feedback", mod.label_names(issues[0]))

    def test_forwarded_feedback_comment_is_not_sent_twice(self):
        issues = [
            issue(
                151,
                "freshness",
                body=task_body("P1", "apply-next-ui"),
                labels=("jules", "jules-needs-feedback", "agent-ready"),
            )
        ]
        sent = []
        comments = [
            {"id": 1, "body": "<!-- jules-session-id: ask1 -->"},
            {"id": 22, "body": "<!-- jules-feedback: ask1 -->\nUse transient state."},
            {"id": 23, "body": "<!-- jules-feedback-sent: 22 -->\nForwarded."},
        ]

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: comments,
            get_session=lambda api_key, path: {
                "id": "ask1",
                "state": "AWAITING_USER_FEEDBACK",
            },
            send_feedback=lambda session_id, prompt: sent.append((session_id, prompt)),
            run_gh=lambda *args: self.fail("already-forwarded feedback should be a no-op"),
        )

        self.assertEqual(sent, [])

    def test_feedback_marker_must_match_waiting_session(self):
        comments = [
            {"id": 22, "body": "<!-- jules-feedback: other-session -->\nWrong session."},
        ]
        self.assertIsNone(mod.pending_feedback_from_comments(comments, "ask1"))

    def test_feedback_waiting_reconciliation_is_idempotent(self):
        issues = [
            issue(
                151,
                "freshness",
                body=task_body("P1", "apply-next-ui"),
                labels=("jules", "jules-needs-feedback", "agent-ready"),
            )
        ]
        gh_calls = []

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: [{"body": "<!-- jules-session-id: ask1 -->"}],
            get_session=lambda api_key, path: {
                "id": "ask1",
                "state": "AWAITING_USER_FEEDBACK",
            },
            load_activities=lambda session_id: self.fail(
                "activities should not be loaded twice while feedback is still pending"
            ),
            run_gh=lambda *args: gh_calls.append(args),
        )

        self.assertEqual(gh_calls, [])
        self.assertIn("jules-needs-feedback", mod.label_names(issues[0]))

    def test_feedback_waiting_session_becomes_active_again_after_user_reply(self):
        issues = [
            issue(
                151,
                "freshness",
                body=task_body("P1", "apply-next-ui"),
                labels=("jules", "jules-needs-feedback", "agent-ready"),
            )
        ]
        gh_calls = []

        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: [{"body": "<!-- jules-session-id: ask1 -->"}],
            get_session=lambda api_key, path: {"id": "ask1", "state": "IN_PROGRESS"},
            run_gh=lambda *args: gh_calls.append(args),
        )

        labels = mod.label_names(issues[0])
        self.assertIn("jules-session", labels)
        self.assertNotIn("jules-needs-feedback", labels)
        self.assertIn("jules-session", gh_calls[0])
        self.assertEqual(mod.select_tasks(issues, max_active=2), [])

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

    def test_watch_loop_repolls_active_sessions_until_terminal(self):
        cycles = []
        sleeps = []
        responses = [
            (True, "source"),
            (True, "source"),
            (False, "source"),
        ]

        def fake_cycle(repo, api_key, source_name):
            cycles.append((repo, api_key, source_name))
            return responses[len(cycles) - 1]

        mod.watch_jules_backlog(
            "kaamilbadami/yartchives",
            "secret",
            poll_seconds=30,
            watch_seconds=780,
            run_cycle=fake_cycle,
            sleep_fn=lambda seconds: sleeps.append(seconds),
            monotonic_fn=lambda: 0,
        )

        self.assertEqual(len(cycles), 3)
        self.assertEqual([call[2] for call in cycles], [None, "source", "source"])
        self.assertEqual(sleeps, [30, 30])

    def test_watch_loop_stops_at_bound_and_leaves_recovery_to_next_run(self):
        cycles = []
        sleeps = []
        times = iter([0, 755])

        mod.watch_jules_backlog(
            "kaamilbadami/yartchives",
            "secret",
            poll_seconds=30,
            watch_seconds=780,
            run_cycle=lambda repo, api_key, source_name: (
                cycles.append((repo, api_key, source_name)) or True,
                "source",
            ),
            sleep_fn=lambda seconds: sleeps.append(seconds),
            monotonic_fn=lambda: next(times),
        )

        self.assertEqual(len(cycles), 1)
        self.assertEqual(sleeps, [])

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


    def test_session_prompt_does_not_pause_for_routine_execution_confirmation(self):
        task = mod.Task(
            155,
            "Benchmark Apply Next interaction and ranking performance",
            task_body("P2", "performance"),
            "P2",
            "performance",
            frozenset(),
        )
        prompt = mod.session_prompt("kaamilbadami/yartchives", task)
        self.assertIn("Do not ask for confirmation merely to continue", prompt)
        self.assertIn("run tests", prompt)
        self.assertIn("genuine product decision", prompt)

    def test_open_dependency_blocks_dispatch_until_dependency_closes(self):
        issues = [
            issue(177, "identity", body=task_body("P1", "identity")),
            issue(
                178,
                "frontend state",
                body=task_body("P1", "frontend-state", depends_on="#177"),
            ),
            issue(179, "dedupe", body=task_body("P1", "coverage")),
        ]
        self.assertEqual(
            [task.number for task in mod.select_tasks(issues, max_active=3)],
            [177, 179],
        )
        issues[0]["state"] = "closed"
        self.assertEqual(
            [task.number for task in mod.select_tasks(issues, max_active=3)],
            [178, 179],
        )

    def test_malformed_dependency_metadata_is_not_dispatchable(self):
        candidate = issue(
            178,
            "frontend state",
            body=task_body("P1", "frontend-state", depends_on="issue-177"),
        )
        self.assertIsNone(mod.task_from_issue(candidate))

    def test_retryable_platform_failure_gets_exactly_one_retry_candidate(self):
        issues = [
            issue(
                176,
                "listing lifecycle",
                body=task_body("P1", "listing-lifecycle"),
                labels=("jules", "jules-session"),
            )
        ]
        gh_calls = []
        comments = [
            {"id": 1, "body": "<!-- jules-session-id: failed1 -->"},
            {
                "id": 2,
                "body": "<!-- jules-feedback: failed1 -->\nKeep the fix provider-neutral.",
            },
        ]
        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: comments,
            get_session=lambda api_key, path: {
                "id": "failed1",
                "state": "FAILED",
            },
            load_activities=lambda session_id: [
                {
                    "createTime": "2026-09-18T23:45:00Z",
                    "error": {"message": "Workspace became unavailable."},
                },
                {
                    "createTime": "2026-09-18T23:44:00Z",
                    "agentMessaged": {"agentMessage": "Applying the provider-neutral fix."},
                },
            ],
            run_gh=lambda *args: gh_calls.append(args),
        )
        labels = mod.label_names(issues[0])
        self.assertIn("jules-retry-ready", labels)
        self.assertNotIn("jules-failed", labels)
        self.assertEqual([task.number for task in mod.select_tasks(issues)], [176])
        comment = gh_calls[1][-1]
        self.assertIn("<!-- jules-retry-from: failed1 -->", comment)
        self.assertIn("Keep the fix provider-neutral.", comment)
        self.assertIn("Applying the provider-neutral fix.", comment)

    def test_second_platform_failure_is_not_retried_again(self):
        issues = [
            issue(
                176,
                "listing lifecycle",
                body=task_body("P1", "listing-lifecycle"),
                labels=("jules", "jules-session"),
            )
        ]
        gh_calls = []
        comments = [
            {
                "id": 1,
                "body": "<!-- jules-retry-from: first-failure -->\nPrior retry context.",
            },
            {"id": 2, "body": "<!-- jules-session-id: second-failure -->"},
        ]
        mod.reconcile_jules_sessions(
            issues,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            load_comments=lambda number: comments,
            get_session=lambda api_key, path: {
                "id": "second-failure",
                "state": "FAILED",
            },
            load_activities=lambda session_id: [
                {"error": {"message": "Workspace became unavailable."}},
            ],
            run_gh=lambda *args: gh_calls.append(args),
        )
        self.assertIn("jules-failed", mod.label_names(issues[0]))
        self.assertNotIn("jules-retry-ready", mod.label_names(issues[0]))

    def test_code_failure_does_not_auto_retry(self):
        self.assertFalse(
            mod.retryable_jules_failure(
                ["Tests failed: expected 2 jobs but received 3."]
            )
        )

    def test_retry_dispatch_preserves_context_and_clears_retry_label(self):
        task = mod.Task(
            176,
            "listing lifecycle",
            task_body("P1", "listing-lifecycle"),
            "P1",
            "listing-lifecycle",
            frozenset(("jules-retry-ready",)),
        )
        captured = {}
        gh_calls = []

        def fake_create(api_key, source_name, repo, task, **kwargs):
            captured.update(kwargs)
            return {"id": "retry2", "url": "https://jules.google.com/session/retry2"}

        mod.dispatch_task(
            task,
            repo="kaamilbadami/yartchives",
            api_key="secret",
            source_name="source",
            comments=[
                {
                    "body": (
                        "<!-- jules-retry-from: failed1 -->\n"
                        "Failure diagnostics:\n\n> Workspace became unavailable.\n\n"
                        "Prior explicit GitHub feedback that must be preserved in the retry:\n\n"
                        "> Keep the fix provider-neutral."
                    )
                }
            ],
            create_session=fake_create,
            run_gh=lambda *args: gh_calls.append(args),
        )
        self.assertIn("Keep the fix provider-neutral.", captured["retry_context"])
        self.assertIn("--remove-label", gh_calls[0])
        self.assertIn("jules-retry-ready", gh_calls[0])


if __name__ == "__main__":
    unittest.main()
