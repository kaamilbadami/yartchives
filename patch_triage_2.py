import re

with open("scripts/triage_workflow_failures.py", "r") as f:
    content = f.read()

# handle_success: strip all Jules lifecycle labels (was missed in my first patch for handle_success, although search pattern matched, it didn't update handle_success)
search_remove_success = """        for label in ("jules", "agent-ready"):"""
replace_remove_success = """        for label in ("jules", "agent-ready", "autonomous-backlog", "jules-session", "jules-failed", "jules-review-ready", "jules-needs-feedback", "jules-retry-ready"):"""

content = content.replace(search_remove_success, replace_remove_success)

with open("scripts/triage_workflow_failures.py", "w") as f:
    f.write(content)
