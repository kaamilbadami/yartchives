import re

with open("scripts/triage_workflow_failures.py", "r") as f:
    content = f.read()

# _ensure_labels: replace jules with autonomous-backlog
search_labels = """    labels = (
        ("workflow-failure", "D73A4A", "Created automatically from a failed GitHub Actions workflow"),
        ("agent-ready", "0E8A16", "Bounded task suitable for an automated coding agent"),
        ("jules", "715CD7", "Dispatch this issue to Google Jules"),
    )"""

replace_labels = """    labels = (
        ("workflow-failure", "D73A4A", "Created automatically from a failed GitHub Actions workflow"),
        ("agent-ready", "0E8A16", "Bounded task suitable for an automated coding agent"),
        ("autonomous-backlog", "1D76DB", "Approved backlog item eligible for autonomous dispatch"),
    )"""

content = content.replace(search_labels, replace_labels)

# handle_failure: Inject metadata into body
search_body = """    body = f\"\"\"{marker}
An automated Yartchives workflow failed."""

replace_body = """    body = f\"\"\"{marker}
<!-- autonomous-task -->
priority: P1
area: automation
resources: automation
autonomous: true

An automated Yartchives workflow failed."""

content = content.replace(search_body, replace_body)

# handle_failure/handle_success: strip all Jules lifecycle labels
search_remove = """            for label in ("jules", "agent-ready"):"""
replace_remove = """            for label in ("jules", "agent-ready", "autonomous-backlog", "jules-session", "jules-failed", "jules-review-ready", "jules-needs-feedback", "jules-retry-ready"):"""

content = content.replace(search_remove, replace_remove)

# handle_failure: recurring issue
search_add_labels = """        if "agent-ready" not in labels:
            edit_args += ["--add-label", "agent-ready"]
        if "jules" not in labels:
            edit_args += ["--add-label", "jules"]"""

replace_add_labels = """        if "agent-ready" not in labels:
            edit_args += ["--add-label", "agent-ready"]
        if "autonomous-backlog" not in labels:
            edit_args += ["--add-label", "autonomous-backlog"]"""

content = content.replace(search_add_labels, replace_add_labels)

# handle_failure: create issue
search_create = """        "--label",
        "workflow-failure",
        "--label",
        "agent-ready",
        "--label",
        "jules",
    )"""

replace_create = """        "--label",
        "workflow-failure",
        "--label",
        "agent-ready",
        "--label",
        "autonomous-backlog",
    )"""

content = content.replace(search_create, replace_create)

# handle_success: body message edit (triage will create a fresh issue with the `jules` label so Jules starts a fresh task.)
search_triage_msg = """                "triage will create a fresh issue with the `jules` label so Jules starts a fresh task."
            ),"""
replace_triage_msg = """                "triage will create a fresh issue with the `autonomous-backlog` label so Jules starts a fresh task."
            ),"""

content = content.replace(search_triage_msg, replace_triage_msg)

with open("scripts/triage_workflow_failures.py", "w") as f:
    f.write(content)
