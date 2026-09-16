#!/usr/bin/env python3
"""Fail CI when the generated Yartchives feed violates core invariants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_EDUCATION = {"undergrad", "graduate-only", "unspecified"}
ALLOWED_TYPES = {"internship", "co-op", "fellowship", "research", "student", "other"}


def validate(path: Path, minimum_jobs: int, minimum_healthy_sources: int, strict_sources: bool) -> list[str]:
    errors: list[str] = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"could not parse {path}: {exc}"]

    jobs = doc.get("jobs")
    sources = doc.get("sources")
    if not isinstance(jobs, list):
        return ["jobs must be a list"]
    if not isinstance(sources, dict):
        return ["sources must be an object"]
    if len(jobs) < minimum_jobs:
        errors.append(f"job count {len(jobs)} is below minimum {minimum_jobs}")

    ids: set[str] = set()
    for i, job in enumerate(jobs):
        if not isinstance(job, dict):
            errors.append(f"job[{i}] is not an object")
            continue
        for field in ("id", "company", "title", "location"):
            if not str(job.get(field) or "").strip():
                errors.append(f"job[{i}] missing {field}")
        job_id = str(job.get("id") or "")
        if job_id in ids:
            errors.append(f"duplicate job id {job_id}")
        ids.add(job_id)

        if not isinstance(job.get("source_names"), list) or not job.get("source_names"):
            errors.append(f"job {job_id or i} missing source_names")
        if not isinstance(job.get("profiles"), list) or not job.get("profiles"):
            errors.append(f"job {job_id or i} missing profiles")
        if job.get("education_level") not in ALLOWED_EDUCATION:
            errors.append(f"job {job_id or i} has invalid education_level {job.get('education_level')!r}")
        if job.get("opportunity_type") not in ALLOWED_TYPES:
            errors.append(f"job {job_id or i} has invalid opportunity_type {job.get('opportunity_type')!r}")

        url = job.get("url")
        if url:
            parsed = urlparse(str(url))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"job {job_id or i} has unsafe/invalid URL {url!r}")

    healthy = 0
    for key, source in sources.items():
        if not isinstance(source, dict):
            errors.append(f"source {key} metadata is malformed")
            continue
        configured = source.get("configured", True)
        if configured is not False and source.get("ok"):
            healthy += 1
        if strict_sources and configured is not False and not source.get("ok"):
            errors.append(f"source {source.get('name', key)} failed: {source.get('error', 'unknown error')}")
    if healthy < minimum_healthy_sources:
        errors.append(f"healthy source count {healthy} is below minimum {minimum_healthy_sources}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/listings.json")
    parser.add_argument("--minimum-jobs", type=int, default=500)
    parser.add_argument("--minimum-healthy-sources", type=int, default=8)
    parser.add_argument("--strict-sources", action="store_true")
    args = parser.parse_args()

    errors = validate(Path(args.path), args.minimum_jobs, args.minimum_healthy_sources, args.strict_sources)
    if errors:
        print("Feed validation failed:", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        if len(errors) > 100:
            print(f"- ... and {len(errors) - 100} more", file=sys.stderr)
        return 1
    print(f"Feed validation passed for {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
