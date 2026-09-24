#!/usr/bin/env python3
"""Add CS-relevant student roles from SmartRecruiters boards already evidenced in-feed.

This is a provider-family gap filler, not a broad SmartRecruiters crawler. A public
board becomes eligible only when the normalized feed already contains a CS
listing with an authoritative SmartRecruiters-hosted job URL. We then enumerate that
same board through SmartRecruiters' public API and merge additional US
student roles with strong CS/technology title evidence.
"""
from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_feed as bf  # noqa: E402
from direct_ct_workday import (  # noqa: E402
    carry_failed_source,
    is_cs_relevant_title,
    is_student_opportunity,
    session as retry_session,
    stable_projection,
    upsert_direct_job,
)
from direct_oracle import StructuralSourceError  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
TIMEOUT = 12
NETWORK_WORKERS = 12
API_HOST = "https://api.smartrecruiters.com"
STRUCTURAL_SOURCE_STATUSES = frozenset({401, 403, 404, 406, 410, 422})


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any) -> str:
    return bf.clean_text(value).strip()


def _evidences_cs(job: dict[str, Any]) -> bool:
    return "cs" in {str(value).lower() for value in (job.get("profiles") or []) if value}


def derive_smartrecruiters_endpoint(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in {"jobs.smartrecruiters.com", "careers.smartrecruiters.com"}:
        raise ValueError("Not a SmartRecruiters job board URL")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("URL path does not contain enough parts for SmartRecruiters company and job ID")

    # E.g. https://jobs.smartrecruiters.com/ServiceNow/744000150270254-senior-staff-product-manager-conversational-ai
    company = parts[0]
    job_id_part = parts[1]
    job_id = job_id_part.split("-")[0]
    if not job_id.isdigit():
        raise ValueError("Could not extract a numeric job ID from the URL")

    return {
        "company_identifier": company,
        "job_id": job_id,
        "canonical_job_url": f"https://jobs.smartrecruiters.com/{company}/{job_id}",
    }


def source_from_job(job: dict[str, Any]) -> dict[str, Any] | None:
    if not _evidences_cs(job):
        return None
    if job.get("link_kind") not in {None, "direct"}:
        return None
    try:
        endpoint = derive_smartrecruiters_endpoint(_clean(job.get("url")))
    except ValueError:
        return None
    company_identifier = endpoint["company_identifier"]
    company = _clean(job.get("company")) or company_identifier
    slug = re.sub(r"[^a-z0-9]+", "-", company_identifier.casefold()).strip("-")
    return {
        "key": f"auto-smartrecruiters-{slug}",
        "name": f"{company} (auto-discovered SmartRecruiters)",
        "company": company,
        "kind": "smartrecruiters",
        "company_identifier": company_identifier,
        "homepage": f"https://jobs.smartrecruiters.com/{company_identifier}",
        "api_url": f"{API_HOST}/v1/companies/{company_identifier}/postings",
        "profile_hint": ["cs"],
        "auto_discovered": True,
    }


def discover_sources(feed: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    jobs = [job for job in (feed.get("jobs") or []) if isinstance(job, dict)]
    jobs.sort(key=lambda job: (_clean(job.get("company")).casefold(), _clean(job.get("url")).casefold()))
    for job in jobs:
        source = source_from_job(job)
        if not source or source["company_identifier"] in seen:
            continue
        out.append(source)
        seen.add(source["company_identifier"])
    return out


def _location(item: dict[str, Any]) -> str:
    location = item.get("location")
    if isinstance(location, dict):
        city = _clean(location.get("city"))
        region = _clean(location.get("region"))
        country = _clean(location.get("country"))
        remote = location.get("remote")
        parts = [p for p in (city, region, country) if p]
        loc_str = ", ".join(parts)
        if remote and "remote" not in loc_str.lower():
            loc_str = f"{loc_str} (Remote)" if loc_str else "Remote"
        return loc_str or "Location not listed"
    return _clean(location) or "Location not listed"


def _looks_us(location: str) -> bool:
    if bf.extract_states(location):
        return True
    return bool(
        re.search(
            r"\b(?:United States|USA|U\.S\.|US Remote|Remote[- ]?US|Remote[- ]?USA|us)\b",
            location or "",
            flags=re.I,
        )
    )


def job_from_item(source: dict[str, Any], item: dict[str, Any], reference: datetime) -> dict[str, Any] | None:
    title = _clean(item.get("name"))
    location = _location(item)
    if not is_student_opportunity(title) or not is_cs_relevant_title(title):
        return None
    if not _looks_us(location):
        return None

    job_id = str(item.get("id") or "").strip()
    if not job_id.isdigit():
        return None

    url = f"https://jobs.smartrecruiters.com/{source['company_identifier']}/{job_id}"

    posted_raw = _clean(item.get("releasedDate"))
    posted_at = bf.parse_relative_date(posted_raw, reference) if posted_raw else None

    direct_source = {
        "key": source["key"],
        "name": source["name"],
        "url": source["homepage"],
        "profile_hint": ["cs"],
        "posted_date_provenance": "authoritative_employer",
    }
    job = bf.base_job(
        company=source["company"],
        title=title,
        location=location,
        url=url,
        posted_raw=posted_raw,
        source=direct_source,
        section="Auto-discovered SmartRecruiters sibling role",
        function_primary="Computer Science / Technology",
        posted_at=posted_at,
    )
    if not job:
        return None
    job["direct_employer"] = True
    job["smartrecruiters_company_identifier"] = source["company_identifier"]
    job["smartrecruiters_job_id"] = job_id
    return job


def fetch_source(client: requests.Session, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    limit = 100
    offset = 0
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    while True:
        try:
            response = client.get(
                source["api_url"],
                params={"limit": limit, "offset": offset},
                headers={"Accept": "application/json", "User-Agent": bf.USER_AGENT},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in STRUCTURAL_SOURCE_STATUSES:
                raise StructuralSourceError(f"SmartRecruiters structural error {status}: {exc}", [status]) from exc
            raise

        items = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError("SmartRecruiters API response did not contain a content list")

        for item in items:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "").strip()
            if not job_id or job_id in seen_ids:
                continue
            job = job_from_item(source, item, reference)
            if job:
                out.append(job)
                seen_ids.add(job_id)

        offset += limit
        total_found = payload.get("totalFound", 0)
        if offset >= total_found or not items:
            break

    return out


def fetch_sources_concurrently(
    sources: list[dict[str, Any]],
    reference: datetime,
) -> dict[str, tuple[list[dict[str, Any]] | None, Exception | None]]:
    if not sources:
        return {}

    results: dict[str, tuple[list[dict[str, Any]] | None, Exception | None]] = {}
    workers = min(NETWORK_WORKERS, len(sources))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_source, retry_session(), source, reference): source
            for source in sources
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                results[source["key"]] = (future.result(), None)
            except Exception as exc:
                results[source["key"]] = (None, exc)
    return results


def apply_authoritative_board_brand(
    jobs: list[dict[str, Any]],
    incoming: dict[str, Any],
    company_identifier: str,
) -> None:
    incoming_company = _clean(incoming.get("company"))
    if not incoming_company:
        return
    incoming_url = bf.canonical_url(incoming.get("url"))
    if not incoming_url:
        return
    for target in jobs:
        if bf.canonical_url(target.get("url")) != incoming_url:
            continue
        if _clean(target.get("company")).casefold() == company_identifier.casefold():
            target["company"] = incoming_company
        return


def enrich(doc: dict[str, Any], old_doc: dict[str, Any], client: requests.Session, reference: datetime) -> dict[str, Any]:
    jobs = doc.setdefault("jobs", [])
    health = doc.setdefault("sources", {})
    old_jobs = old_doc.get("jobs", []) if isinstance(old_doc, dict) else []
    old_jobs_by_id = {j.get("id"): j for j in old_jobs if isinstance(j, dict) and j.get("id")}

    sources = discover_sources(doc)
    fetched = fetch_sources_concurrently(sources, reference)
    print(f"SmartRecruiters enumeration: {len(sources)} board(s), up to {min(NETWORK_WORKERS, len(sources)) if sources else 0} concurrent")

    for source in sources:
        direct_jobs, exc = fetched.get(source["key"], (None, RuntimeError("missing fetch result")))
        if exc is None and direct_jobs is not None:
            for job in direct_jobs:
                upsert_direct_job(jobs, job, old_jobs_by_id, reference)
                apply_authoritative_board_brand(jobs, job, source["company_identifier"])
            health[source["key"]] = {
                "status": "healthy",
                "count": len(direct_jobs),
                "name": source["name"],
                "direct": True,
                "auto_discovered": True,
            }
            print(f"{source['name']}: {len(direct_jobs)} direct US CS student listing(s)")
            continue

        if isinstance(exc, StructuralSourceError):
            health[source["key"]] = {
                "status": "quarantined",
                "count": 0,
                "name": source["name"],
                "direct": True,
                "auto_discovered": True,
                "error": f"StructuralSourceError: {exc}",
            }
            print(f"{source['name']}: QUARANTINED (structural source error): {exc}", file=sys.stderr)
        else:
            health[source["key"]] = {
                "status": "failed",
                "count": 0,
                "name": source["name"],
                "direct": True,
                "auto_discovered": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
            if carry_failed_source(jobs, old_jobs, source["key"]):
                health[source["key"]]["status"] = "degraded"
            print(f"{source['name']}: FAILED: {exc}", file=sys.stderr)
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--old-feed", type=Path)
    args = parser.parse_args()

    doc = json.loads(args.feed.read_text(encoding="utf-8"))
    old_doc: dict[str, Any] = {}
    if args.old_feed and args.old_feed.exists():
        try:
            old_doc = json.loads(args.old_feed.read_text(encoding="utf-8"))
        except Exception:
            old_doc = {}
    if not old_doc:
        old_doc = copy.deepcopy(doc)

    reference = now_utc()
    enrich(doc, old_doc, retry_session(), reference)
    if stable_projection(doc) == stable_projection(old_doc):
        print("Auto-discovered SmartRecruiters coverage unchanged.")
        return 0
    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged auto-discovered SmartRecruiters coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
