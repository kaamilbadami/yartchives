#!/usr/bin/env python3
"""Add US CS-relevant student roles from resolved Lever Candidate Experience sites.

This is a provider-family gap filler. It enumerates Lever career sites
whose employer-universe resolution already includes an explicit Candidate
Experience site identifier or is explicitly resolved to Lever.
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

from domain_discovery import _domain_token
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


def _looks_us(location: str, country: str) -> bool:
    if country and country.upper() == "US":
        return True
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
        provider = employer.get("provider", {})
        is_resolved_lever = provider.get("status") == "resolved" and provider.get("family") == "lever"
        has_lever_hint = any("jobs.lever.co" in h or "lever.co" in h for h in employer.get("domain_hints", []))
        if not (is_resolved_lever or has_lever_hint):
            continue

        domain_hints = employer.get("domain_hints", [])
        lever_host = None
        for hint in domain_hints:
            if "jobs.lever.co/" in hint:
                lever_host = hint.split("jobs.lever.co/")[1].strip("/")
                break

        if not lever_host:
            # Fallback if domain_hint doesn't explicitly have it but it's a lever provider
            # Many times domain_hints has "jobs.lever.co/company"
            # Or seed_metadata has it
            for hint in domain_hints:
                if "lever.co/" in hint:
                    lever_host = hint.split("lever.co/")[1].strip("/")
                    break

        if not lever_host:
             # Try seed_metadata
             seed_meta = employer.get("seed_metadata", {})
             for seed_name, seed_data in seed_meta.items():
                 apply_host = seed_data.get("apply_host")
                 if apply_host and "jobs.lever.co/" in apply_host:
                     lever_host = apply_host.split("jobs.lever.co/")[1].strip("/")
                     break

        if not lever_host:
            # Guess slug from name and domains
            slugs = set()
            name = employer.get("name", "")
            slugs.add(re.sub(r"[^a-z0-9]+", "", name.lower()))
            slugs.add(re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))

            for hint in domain_hints:
                if "lever.co" not in hint:
                    token = _domain_token(hint)
                    if token:
                        slugs.add(token)
                        slugs.add(token.replace(" ", ""))
                        slugs.add(token.replace(" ", "-"))

            # probe slugs safely
            for slug in slugs:
                if not slug: continue
                url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
                try:
                    resp = requests.get(url, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list):
                            lever_host = slug
                            break
                except Exception:
                    pass

        if not lever_host:
            continue

        if lever_host in seen:
            continue

        seen.add(lever_host)

        slug = re.sub(r"[^a-z0-9]+", "-", lever_host.casefold()).strip("-")
        source = {
            "key": f"auto-lever-{slug}",
            "name": f"{employer.get('name')} (auto-discovered Lever)",
            "company": employer.get("name"),
            "employer_id": employer.get("id"),
            "kind": "lever",
            "lever_host": lever_host,
            "api_url": f"https://api.lever.co/v0/postings/{lever_host}?mode=json",
            "homepage": f"https://jobs.lever.co/{lever_host}",
            "auto_discovered": True,
        }
        out.append(source)

    return out


def job_from_item(source: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    title = _clean(item.get("text"))
    if not title:
        return None

    categories = item.get("categories", {})
    location = _clean(categories.get("location"))
    country = _clean(item.get("country"))

    if not is_student_opportunity(title) or not is_cs_relevant_title(title):
        return None
    if not _looks_us(location, country):
        return None

    job_id = _clean(item.get("id"))
    if not job_id:
        return None

    url = _clean(item.get("hostedUrl"))
    if not url:
        url = f"https://jobs.lever.co/{source['lever_host']}/{job_id}"

    created_at = item.get("createdAt")
    posted_at = None
    if created_at and isinstance(created_at, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(created_at / 1000.0, timezone.utc)
        except (ValueError, TypeError):
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
        section="Auto-discovered Lever sibling role",
        function_primary="Computer Science / Technology",
        posted_at=posted_at,
    )
    if not job:
        return None
    job["direct_employer"] = True
    job["lever_job_id"] = job_id
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
        raise EndpointRetiredError(f"Lever board retired: {response.status_code}")

    if response.status_code >= 400:
        raise StructuralSourceError(f"Lever board returned {response.status_code}")

    try:
        payload = response.json()
    except ValueError:
        raise StructuralSourceError("Invalid JSON response")

    if not isinstance(payload, list):
        raise StructuralSourceError("Expected list in Lever API response")

    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        job = job_from_item(source, item)
        if job:
            job_id = job.get("lever_job_id")
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
    print(f"Lever enumeration: {len(sources)} board(s), up to {min(NETWORK_WORKERS, len(sources)) if sources else 0} concurrent")

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
        print("Auto-discovered Lever coverage unchanged.")
        return 0

    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged auto-discovered Lever coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
