from typing import Any, Hashable

import sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts").resolve()))

import stabilize_job_ids as mod

# Test case where a job receives a new ID because of duplicate old IDs
old = [{
    "id": "existing-point72-id",
    "company": "Point72",
    "title": "Quantitative Developer Intern",
    "location": "New York, NY",
    "url": "https://job-boards.greenhouse.io/point72/jobs/1234567",
    "first_seen": "2026-09-01T00:00:00Z",
}]
duplicate = {
    "company": "Point72",
    "title": "Quantitative Developer Intern",
    "location": "New York, NY",
    "url": "https://job-boards.greenhouse.io/point72/jobs/1234567",
}
refreshed = [dict(duplicate), dict(duplicate), dict(duplicate)]

jobs, stats = mod.stabilize_jobs(refreshed, old)
print(jobs)
