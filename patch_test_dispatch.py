with open("tests/test_dispatch_autonomous_issues.py", "r") as f:
    content = f.read()

search = """    def test_non_backlog_jules_work_does_not_consume_backlog_wip(self):
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
        self.assertEqual([task.number for task in selected], [3])"""

# We updated dispatch_autonomous_issues to treat workflow-failures AS BACKLOG WIP if they are agent-ready.
# So they WILL consume backlog WIP now!
replace = """    def test_workflow_failures_are_now_dispatched_as_backlog_wip(self):
        issues = [
            issue(
                1,
                "[workflow failure] Update opportunity feed: Validate code",
                labels=("workflow-failure", "agent-ready", "autonomous-backlog"),
            ),
            issue(
                2,
                "[workflow failure] Update opportunity feed: Validate generated feed",
                labels=("workflow-failure", "agent-ready", "autonomous-backlog"),
            ),
            issue(3, "roadmap", body=task_body("P1", "frontend-state")),
        ]
        selected = mod.select_tasks(issues, max_active=2)
        self.assertEqual([task.number for task in selected], [1, 2])"""

content = content.replace(search, replace)

with open("tests/test_dispatch_autonomous_issues.py", "w") as f:
    f.write(content)
