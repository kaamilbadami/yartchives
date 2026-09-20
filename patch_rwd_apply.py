import re

with open("scripts/reconcile_workday_duplicates.py", "r") as f:
    content = f.read()

merge_posting_group_old = """    if workday_identity_key(canonical_url):
        if canonical_url.rstrip("/").casefold().endswith("/apply"):
            merged["link_kind"] = "direct"
        else:
            merged["link_kind"] = "employer_job"

    for field in LIST_FIELDS:"""

merge_posting_group_new = """    if workday_identity_key(canonical_url):
        if canonical_url.rstrip("/").casefold().endswith("/apply"):
            merged["link_kind"] = "direct"
        elif winner.get("link_kind") == "direct" and is_verified_workday_apply(winner):
            merged["link_kind"] = "direct"
        else:
            merged["link_kind"] = "employer_job"

    for field in LIST_FIELDS:"""

content = content.replace(merge_posting_group_old, merge_posting_group_new)

# Wait, `reconciled_posting_url(winner)` should have appended `/apply` if the winner was `is_verified_workday_apply(winner)`.
# Let's check why my test failed.
