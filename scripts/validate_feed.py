#!/usr/bin/env python3
"""Fail CI when the generated Yartchives feed violates core invariants."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

WORKDAY_HOST_RE = re.compile(r"^[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com$", re.I)

ALLOWED_EDUCATION = {"undergrad", "graduate-only", "unspecified"}
ALLOWED_TYPES = {"internship", "co-op", "fellowship", "research", "student", "other"}
ALLOWED_LINK_KINDS = {"direct", "employer_job", "listing", "source"}
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
    return errors


def valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def source_status(source: dict) -> str | None:
    """Normalize source health across the legacy and explicit status schemas."""
    status = source.get("status")
    if isinstance(status, str) and status:
        return status
    if source.get("configured") is False:
        return "quarantined"
    if source.get("ok") is True:
        return "healthy"
    if source.get("ok") is False:
        return "failed"
    return None


def validate(
    path: Path,
    minimum_jobs: int,
    minimum_healthy_sources: int,
    strict_sources: bool,
    enforce_link_contract: bool = False,
) -> list[str]:
    fatal_errors: list[str] = []
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

    valid_jobs = []
    quarantined = 0
    downgraded = 0
    ids: set[str] = set()

    for i, job in enumerate(jobs):
        if not isinstance(job, dict):
            quarantined += 1
            continue

        job_id = str(job.get("id") or "")
        if job_id in ids:
            fatal_errors.append(f"duplicate job id {job_id}")
            continue
        if job_id:
            ids.add(job_id)

        structural_errors = []
        for field in ("id", "company", "title", "location"):
            if not str(job.get(field) or "").strip():
                structural_errors.append(field)
        if not isinstance(job.get("source_names"), list) or not job.get("source_names"):
            structural_errors.append("source_names")
        if not isinstance(job.get("profiles"), list) or not job.get("profiles"):
            structural_errors.append("profiles")
        if job.get("education_level") not in ALLOWED_EDUCATION:
            structural_errors.append("education_level")
        if job.get("opportunity_type") not in ALLOWED_TYPES:
            structural_errors.append("opportunity_type")

        if structural_errors:
            quarantined += 1
            continue

        link_errors = []
        kind = job.get("link_kind")
        if kind not in ALLOWED_LINK_KINDS:
            link_errors.append("link_kind")

        url = job.get("url")
        listing_url = job.get("listing_url")
        if url and not valid_http_url(url):
            link_errors.append("url")
        if listing_url and not valid_http_url(listing_url):
            link_errors.append("listing_url")

        if kind == "direct":
            if not valid_http_url(url) or urlparse(str(url)).netloc.lower() in NON_DIRECT_HOSTS:
                link_errors.append("direct contract")
        elif kind == "employer_job":
            if not valid_http_url(url) or urlparse(str(url)).netloc.lower() in NON_DIRECT_HOSTS:
                link_errors.append("employer_job contract")
        elif kind == "listing" and not valid_http_url(listing_url):
            link_errors.append("listing contract")
        elif kind == "source" and url:
            link_errors.append("source contract")

        if enforce_link_contract and workday_direct_contract_errors(job, f"job {job_id or i}"):
            link_errors.append("workday contract")

        if link_errors:
            job["link_kind"] = "source"
            job.pop("url", None)
            job.pop("listing_url", None)
            downgraded += 1

        valid_jobs.append(job)

    if len(valid_jobs) < minimum_jobs:
        fatal_errors.append(f"job count {len(valid_jobs)} is below minimum {minimum_jobs}")

    healthy = 0
    for key, source in sources.items():
        if not isinstance(source, dict):
            fatal_errors.append(f"source {key} metadata is malformed")
            continue
        status = source_status(source)
        if status in {"healthy", "degraded"}:
            healthy += 1
        if strict_sources and status == "failed":
            fatal_errors.append(f"source {source.get('name', key)} failed: {source.get('error', 'unknown error')}")
    if healthy < minimum_healthy_sources:
        fatal_errors.append(f"healthy source count {healthy} is below minimum {minimum_healthy_sources}")

    if (quarantined > 0 or downgraded > 0) and not fatal_errors:
        doc["jobs"] = valid_jobs
        try:
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:
            fatal_errors.append(f"failed to write quarantined feed: {exc}")

    if quarantined > 0 or downgraded > 0:
        print(f"Record-level containment: quarantined={quarantined}, downgraded={downgraded}")

    workday_direct = [
        job for job in jobs
        if isinstance(job, dict) and job.get("link_kind") == "direct" and is_workday_url(job.get("url"))
    ]
    # For metrics, we run the workday contract errors regardless of enforce_link_contract.
    workday_violations = sum(
        bool(workday_direct_contract_errors(job, f"job {job.get('id') or i}"))
        for i, job in enumerate(workday_direct)
    )
    print(
        "Link-quality contract: "
        f"workday_direct={len(workday_direct)}, workday_violations={workday_violations}, "
        f"enforced={str(enforce_link_contract).lower()}"
    )

    return fatal_errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/listings.json")
    parser.add_argument("--minimum-jobs", type=int, default=500)
    parser.add_argument("--minimum-healthy-sources", type=int, default=8)
    parser.add_argument("--strict-sources", action="store_true")
    parser.add_argument(
        "--enforce-link-contract",
        action="store_true",
        help="fail when a Workday link presented as direct Apply is not an /apply destination",
    )
    args = parser.parse_args()

    errors = validate(
        Path(args.path),
        args.minimum_jobs,
        args.minimum_healthy_sources,
        args.strict_sources,
        args.enforce_link_contract,
    )
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