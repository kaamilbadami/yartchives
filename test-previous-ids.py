from typing import Any, Hashable

import sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts").resolve()))

import stabilize_job_ids as mod

old = [{
    "id": "existing-applied-id",
    "company": "CACI",
    "title": "Cleared Software Engineer Intern - Summer 2027",
    "location": "Sterling, VA",
    "url": "https://caci.wd1.myworkdayjobs.com/external/job/437-DENVER-CO/Role_331999",
    "first_seen": "2026-09-01T00:00:00Z",
}]
refreshed = [{
    "id": "new-id",
    "company": "CACI, Inc.",
    "title": "Cleared Software Engineer Intern – Summer 2027",
    "location": "Denver, CO, US",
    "url": "https://caci.wd1.myworkdayjobs.com/External/job/Denver-CO-US/Updated-Role_331999",
}]

jobs, stats = mod.stabilize_jobs(refreshed, old)
print(jobs[0])
