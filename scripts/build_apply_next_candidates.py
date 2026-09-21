#!/usr/bin/env python3
"""Build the browser-facing Apply Next candidate artifact.

The main listings feed carries source-health, provenance, and audit metadata needed
for browsing and operations. Apply Next only needs a bounded set of job fields for
candidate filtering, ranking, location enrichment, rendering, and inspection joins.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

JOB_FIELDS = (
    "id",
    "company",
    "title",
    "location",
    "url",
    "posted_at",
    "term",
    "profiles",
    "states",
    "opportunity_type",
    "education_level",
    "link_kind",
    "direct_employer",
    "function_primary",
    "section",
)


def project_job(job: Any) -> dict[str, Any] | None:
    if not isinstance(job, dict):
        return None
    projected = {key: job.get(key) for key in JOB_FIELDS if key in job}
    return projected if projected.get("id") else None


def build_candidate_artifact(feed: dict[str, Any]) -> dict[str, Any]:
    jobs = feed.get("jobs") if isinstance(feed.get("jobs"), list) else []
    compact = [projected for job in jobs if (projected := project_job(job)) is not None]
    return {
        "version": 1,
        "generated_at": feed.get("generated_at"),
        "content_hash": feed.get("content_hash"),
        "jobs": compact,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    feed = json.loads(args.input.read_text(encoding="utf-8"))
    artifact = build_candidate_artifact(feed if isinstance(feed, dict) else {})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
