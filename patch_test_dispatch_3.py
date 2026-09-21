with open("tests/test_dispatch_autonomous_issues.py", "r") as f:
    content = f.read()

search = """    def test_legacy_jules_labels_without_session_do_not_consume_wip_or_block_retry(self):
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
        self.assertEqual([task.number for task in selected], [1, 3])"""

replace = """    def test_legacy_jules_labels_without_session_do_not_consume_wip_or_block_retry(self):
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
        self.assertEqual([task.number for task in selected], [1, 2])"""

content = content.replace(search, replace)

with open("tests/test_dispatch_autonomous_issues.py", "w") as f:
    f.write(content)
