import re

with open("scripts/triage_workflow_failures.py", "r") as f:
    content = f.read()

# Revert the overly broad stripping of labels inside handle_failure for stale issues
search_remove = """            for label in ("jules", "agent-ready", "autonomous-backlog", "jules-session", "jules-failed", "jules-review-ready", "jules-needs-feedback", "jules-retry-ready"):
                if label in labels:
                    edit_args += ["--remove-label", label]"""

replace_remove = """            for label in ("jules", "agent-ready", "autonomous-backlog"):
                if label in labels:
                    edit_args += ["--remove-label", label]"""

content = content.replace(search_remove, replace_remove)

with open("scripts/triage_workflow_failures.py", "w") as f:
    f.write(content)
