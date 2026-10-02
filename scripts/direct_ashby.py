#!/usr/bin/env python3
"""Add US CS-relevant student roles from resolved Ashby Candidate Experience sites.

This is a provider-family gap filler. It enumerates Ashby career sites
whose employer-universe resolution already includes an explicit Candidate
Experience site identifier or is explicitly resolved to Ashby.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from employer_resolution_lifecycle import invalidate_resolution
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_feed as bf  # noqa: E402
from direct_ct_workday import (  # noqa: E402
    carry_failed_source,
    is_cs_relevant_title,
    is_student_opportunity,
    now_utc,
    stable_projection,
    upsert_direct_job,
)
class StructuralSourceError(RuntimeError):
    def __init__(self, message: str, statuses: list[int] | None = None):
        super().__init__(message)
        self.statuses = statuses or []

class EndpointRetiredError(RuntimeError):
    pass


DEFAULT_FEED = SCRIPT_DIR.parent / "data" / "listings.json"
NETWORK_WORKERS = 4
TIMEOUT = 30


def retry_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _clean(value: Any) -> str:
    if not value or not isinstance(value, str):
        return ""
    return value.strip()


def _looks_us(location: str) -> bool:
    if bf.extract_states(location):
        return True
    return bool(
        re.search(
            r"\b(?:United States|USA|U\.S\.|US Remote|Remote[- ]?US|Remote[- ]?USA)\b",
            location or "",
            flags=re.I,
        )
    )


def discover_sources(universe: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for employer in universe.get("employers", []):
        # Allow either a resolved Ashby provider OR explicit seed evidence of Ashby
        provider = employer.get("provider", {})
        has_ashby_provider = (provider.get("status") == "resolved" and provider.get("family") == "ashby")

        domain_hints = employer.get("domain_hints", [])
        ashby_board = None
        for hint in domain_hints:
            if "jobs.ashbyhq.com/" in hint:
                ashby_board = hint.split("jobs.ashbyhq.com/")[1].strip("/")
                break

        if not ashby_board:
            for seed_name, seed_data in employer.get("seed_metadata", {}).items():
                if seed_data.get("apply_host") == "jobs.ashbyhq.com" and seed_data.get("upstream_slug"):
                    ashby_board = seed_data["upstream_slug"]
                    break

        if not ashby_board:
            continue

        # If they don't have a resolved Ashby provider, AND they don't have explicit Ashby seed evidence
        # (e.g. they only accidentally had a domain hint jobs.ashbyhq.com/...), then we shouldn't force it.
        if not has_ashby_provider and not employer.get("seed_metadata"):
            continue

        if ashby_board in seen:
            continue

        seen.add(ashby_board)

        slug = re.sub(r"[^a-z0-9]+", "-", ashby_board.casefold()).strip("-")
        source = {
            "key": f"auto-ashby-{slug}",
            "name": f"{employer.get('name')} (auto-discovered Ashby)",
            "company": employer.get("name"),
            "employer_id": employer.get("id"),
            "kind": "ashby",
            "ashby_board": ashby_board,
            "api_url": f"https://api.ashbyhq.com/posting-api/job-board/{ashby_board}",
            "homepage": f"https://jobs.ashbyhq.com/{ashby_board}",
            "auto_discovered": True,
        }
        out.append(source)

    return out


def job_from_item(source: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    title = _clean(item.get("title"))
    if not title:
        return None

    location = _clean(item.get("location"))

    locations = [location]
    secondary = item.get("secondaryLocations")
    if isinstance(secondary, list):
        for sec in secondary:
            if isinstance(sec, dict):
                loc = _clean(sec.get("location"))
                if loc:
                    locations.append(loc)

    if not is_student_opportunity(title) or not is_cs_relevant_title(title):
        return None

    is_us = False
    for loc in locations:
        if _looks_us(loc):
            is_us = True
            location = loc # Prefer a US location for display
            break

    if not is_us:
        return None

    job_id = _clean(item.get("id"))
    if not job_id:
        return None

    url = _clean(item.get("jobUrl"))
    if not url:
        url = f"https://jobs.ashbyhq.com/{source['ashby_board']}/{job_id}"

    published_at = item.get("publishedAt")
    posted_at = None
    if published_at:
        try:
            # e.g. 2024-03-27T17:41:00.000Z
            parsed_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            posted_at = parsed_dt.astimezone(timezone.utc)
        except ValueError:
            pass

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
        location=location or "United States",
        url=url,
        posted_raw="",
        source=direct_source,
        section="Auto-discovered Ashby sibling role",
        function_primary="Computer Science / Technology",
        posted_at=posted_at,
    )
    if not job:
        return None
    job["direct_employer"] = True
    job["ashby_job_id"] = job_id
    return job


def fetch_source(client: requests.Session, source: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        response = client.get(
            source["api_url"],
            headers={"Accept": "application/json", "User-Agent": bf.USER_AGENT},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise StructuralSourceError(f"Network error: {e}")

    if response.status_code in (404, 410):
        raise EndpointRetiredError(f"Ashby board retired: {response.status_code}")

    if response.status_code >= 400:
        raise StructuralSourceError(f"Ashby board returned {response.status_code}")

    try:
        payload = response.json()
    except ValueError:
        raise StructuralSourceError("Invalid JSON response")

    if not isinstance(payload, dict):
        raise StructuralSourceError("Expected object in Ashby API response")

    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise StructuralSourceError("Expected jobs list in Ashby API response")

    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in jobs:
        if not isinstance(item, dict):
            continue
        job = job_from_item(source, item)
        if job:
            job_id = job.get("ashby_job_id")
            if job_id and job_id not in seen_ids:
                out.append(job)
                seen_ids.add(job_id)

    return out


def fetch_sources_concurrently(
    sources: list[dict[str, Any]],
    universe: dict[str, Any],
) -> dict[str, tuple[list[dict[str, Any]] | None, Exception | None]]:
    if not sources:
        return {}

    results: dict[str, tuple[list[dict[str, Any]] | None, Exception | None]] = {}
    workers = min(NETWORK_WORKERS, len(sources))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_source, retry_session(), source): source
            for source in sources
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                results[source["key"]] = (future.result(), None)
            except Exception as exc:
                if isinstance(exc, (StructuralSourceError, EndpointRetiredError)):
                    employer = next((e for e in universe.get("employers", []) if e.get("id") == source["employer_id"]), None)
                    if employer:
                        invalidate_resolution(employer, str(exc))
                results[source["key"]] = (None, exc)
    return results


def enrich(doc: dict[str, Any], old_doc: dict[str, Any], universe: dict[str, Any], reference: datetime) -> dict[str, Any]:
    jobs = doc.setdefault("jobs", [])
    health = doc.setdefault("sources", {})
    old_jobs = old_doc.get("jobs", []) if isinstance(old_doc, dict) else []
    old_jobs_by_id = {j.get("id"): j for j in old_jobs if isinstance(j, dict) and j.get("id")}

    sources = discover_sources(universe)
    fetched = fetch_sources_concurrently(sources, universe)

    # Sort sources to ensure deterministic output
    sources.sort(key=lambda s: s["key"])
    print(f"Ashby enumeration: {len(sources)} board(s), up to {min(NETWORK_WORKERS, len(sources)) if sources else 0} concurrent")

    for source in sources:
        direct_jobs, exc = fetched.get(source["key"], (None, RuntimeError("missing fetch result")))
        if exc is None and direct_jobs is not None:
            for job in direct_jobs:
                upsert_direct_job(jobs, job, old_jobs_by_id, reference)
            health[source["key"]] = {
                "status": "healthy",
                "count": len(direct_jobs),
                "name": source["name"],
                "direct": True,
                "auto_discovered": True,
            }
            print(f"{source['name']}: {len(direct_jobs)} direct US CS student listing(s)")
            continue

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

        if isinstance(exc, EndpointRetiredError):
            health[source["key"]]["status"] = "retired"

        print(f"{source['name']}: FAILED: {exc}", file=sys.stderr)

    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--old-feed", type=Path)
    parser.add_argument("--universe", type=Path, default=SCRIPT_DIR.parent / "employer_universe.json")
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

    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    reference = now_utc()
    enrich(doc, old_doc, universe, reference)

    if stable_projection(doc) == stable_projection(old_doc):
        print("Auto-discovered Ashby coverage unchanged.")
        return 0

    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged auto-discovered Ashby coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
