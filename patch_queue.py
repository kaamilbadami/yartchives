with open("scripts/queue_coverage_gap.py", "r") as f:
    content = f.read()

search = """        if task and ("jules-session" in labels or JULES_FEEDBACK_LABEL in labels or "jules" in labels):"""
replace = """        if task and ("jules-session" in labels or JULES_FEEDBACK_LABEL in labels):"""

content = content.replace(search, replace)

with open("scripts/queue_coverage_gap.py", "w") as f:
    f.write(content)
