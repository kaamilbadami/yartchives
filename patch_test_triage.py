import re

with open("tests/test_triage_workflow_failures.py", "r") as f:
    content = f.read()

# Replace jules with autonomous-backlog everywhere in test
content = content.replace('"jules"', '"autonomous-backlog"')
content = content.replace('jules_labeled', 'autonomous_labeled')
content = content.replace('fresh_jules', 'fresh_autonomous')

with open("tests/test_triage_workflow_failures.py", "w") as f:
    f.write(content)
