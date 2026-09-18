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

    def test_active_autonomous_jules_work_counts_against_wip_limit(self):
        issues = [
            issue(
                1,
                "active feed",
                body=task_body("P1", "feed"),
                labels=("jules",),
            ),
            issue(
                2,
                "active quality",
                body=task_body("P1", "quality"),
                labels=("jules",),
            ),
            issue(3, "roadmap", body=task_body("P1", "frontend-state")),
        ]

        self.assertEqual(mod.select_tasks(issues, max_active=2), [])

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
                labels=("jules",),
            ),
            issue(2, "another frontend", body=task_body("P0", "frontend-state")),
            issue(3, "coverage", body=task_body("P1", "coverage")),
        ]

        selected = mod.select_tasks(issues, max_active=2)

        self.assertEqual([task.number for task in selected], [3])

    def test_blocked_or_product_decision_tasks_are_not_dispatched(self):
        issues = [
            issue(1, "blocked", body=task_body("P0", "feed"), labels=("blocked",)),
            issue(
                2,
                "decision",
                body=task_body("P0", "ranking"),
                labels=("needs-product-decision",),
            ),
            issue(3, "safe", body=task_body("P1", "coverage")),
        ]

        selected = mod.select_tasks(issues, max_active=2)

        self.assertEqual([task.number for task in selected], [3])

    def test_paginated_issue_pages_are_flattened_without_json_stream_assumptions(self):
        pages = [
            [{"number": 1}, {"number": 2}],
            [{"number": 3}],
        ]

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
