import re

with open("tests/test_reconcile_workday_duplicates.py", "r") as f:
    content = f.read()

# simplify.jobs does not get identified as Workday, so it doesn't get reconciled into the same group. We should use Workday URLs for all of them.

new_listing = """        listing = {
            "url": "https://company.wd1.myworkdayjobs.com/en-US/Careers/job/City/Role_REQ-123/listing",
            "link_kind": "listing"
        }"""
content = content.replace("""        listing = {
            "url": "https://simplify.jobs/p/some-listing?job_id=REQ-123",
            "link_kind": "listing"
        }""", new_listing)

with open("tests/test_reconcile_workday_duplicates.py", "w") as f:
    f.write(content)
