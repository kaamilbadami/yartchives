#!/usr/bin/env python3
"""Fail CI when the generated Yartchives feed violates core invariants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

WORKDAY_HOST_RE = __import__("re").compile(r"^[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com$", __import__("re").I)

ALLOWED_EDUCATION = {"undergrad", "graduate-only", "unspecified"}
ALLOWED_TYPES = {"internship", "co-op", "fellowship", "research", "student", "other"}
ALLOWED_LINK_KINDS = {"direct", "listing", "source"}
NON_DIRECT_HOSTS = {
    "github.com", "www.github.com", "raw.githubusercontent.com",
    "simplify.jobs", "www.simplify.jobs",
    "zapply.jobs", "www.zapply.jobs",
    "jobright.ai", "www.jobright.ai",
    "applyguy.ai", "www.applyguy.ai", "applyguy.com", "www.applyguy.com",
    "fromcampustocareer.com", "www.fromcampustocareer.com",
}


def is_workday_url(value: str | None) -> bool:
    if not valid_http_url(value):
        return False
    return bool(WORKDAY_HOST_RE.fullmatch((urlparse(str(value)).hostname or "").lower()))


def workday_direct_contract_errors(job: dict, label: str) -> list[str]:
    if job.get("link_kind") != "direct" or not is_workday_url(job.get("url")):
        return []
    url = str(job.get("url") or "")
    errors: list[str] = []
    if not urlparse(url).path.rstrip("/").casefold().endswith("/apply"):
        errors.append(f"link-quality: {label} Workday direct URL is not an /apply destination: {url}")
    if job.get("link_status") != "ok":
        errors.append(
            f"link-quality: {label} Workday direct URL is not validated ok "
            f"(status={job.get('link_status')!r}): {url}"
        )
    if not str(job.get("link_checked_at") or "").strip():
        errors.append(f"link-quality: {label} Workday direct URL has no validation timestamp: {url}")
    workday_direct = [
        job for job in jobs
        if isinstance(job, dict) and job.get("link_kind") == "direct" and is_workday_url(job.get("url"))
    ]
    workday_violations = sum(
        bool(workday_direct_contract_errors(job, f"job {job.get('id') or i}"))
        for i, job in enumerate(workday_direct)
    )
    print(
        "Link-quality contract: "
        f"workday_direct={len(workday_direct)}, workday_violations={workday_violations}"
    )

    return errors


def valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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

        kind = job.get("link_kind")
        if kind not in ALLOWED_LINK_KINDS:
            errors.append(f"job {job_id or i} has invalid link_kind {kind!r}")

        url = job.get("url")
        listing_url = job.get("listing_url")
        if url and not valid_http_url(url):
            errors.append(f"job {job_id or i} has unsafe/invalid URL {url!r}")
        if listing_url and not valid_http_url(listing_url):
            errors.append(f"job {job_id or i} has unsafe/invalid listing_url {listing_url!r}")

        if kind == "direct":
            if not valid_http_url(url):
                errors.append(f"job {job_id or i} direct link_kind has no direct URL")
            elif urlparse(str(url)).netloc.lower() in NON_DIRECT_HOSTS:
                errors.append(f"job {job_id or i} labels non-direct host as Apply: {urlparse(str(url)).netloc}")
        elif kind == "listing" and not valid_http_url(listing_url):
            errors.append(f"job {job_id or i} listing link_kind has no listing_url")
        elif kind == "source" and url:
            errors.append(f"job {job_id or i} source-only link should not populate url")

        errors.extend(workday_direct_contract_errors(job, f"job {job_id or i}"))

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