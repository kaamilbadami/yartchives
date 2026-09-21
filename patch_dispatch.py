import re

with open("scripts/dispatch_autonomous_issues.py", "r") as f:
    content = f.read()

# Update autonomous_issue_authorized
search_auth = """    return (
        AUTONOMOUS_MARKER in body
        or {"agent-ready", "autonomous-backlog"} <= labels
    )"""

replace_auth = """    return (
        AUTONOMOUS_MARKER in body
        or {"agent-ready", "autonomous-backlog"} <= labels
        or {"agent-ready", "workflow-failure"} <= labels
    )"""

content = content.replace(search_auth, replace_auth)

# Update task_from_issue
search_task = """    if (
        safe != "true"
        or priority not in PRIORITY_ORDER
        or not area
        or dependencies is None
    ):
        return None"""

replace_task = """    if {"agent-ready", "workflow-failure"} <= label_names(issue):
        if not safe: safe = "true"
        if not priority: priority = "P1"
        if not area: area = "automation"
        if not resources: resources = frozenset({"automation"})
        if dependencies is None: dependencies = frozenset()

    if (
        safe != "true"
        or priority not in PRIORITY_ORDER
        or not area
        or dependencies is None
    ):
        return None"""

content = content.replace(search_task, replace_task)

with open("scripts/dispatch_autonomous_issues.py", "w") as f:
    f.write(content)
