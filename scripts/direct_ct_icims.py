#!/usr/bin/env python3
"""Add CT CS-relevant sibling jobs from iCIMS career sites already evidenced in-feed.

This is a targeted gap-filler, not a broad iCIMS crawler. A site becomes eligible
only when the normalized feed already contains a Connecticut CS listing with an
authoritative public iCIMS URL. We then search that same public career site for
student roles and merge matching CT CS opportunities using the existing direct
source upsert semantics.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_feed as bf  # noqa: E402
from direct_ct_workday import (  # noqa: E402
    carry_failed_source,
    is_cs_relevant_title,
    is_student_opportunity,
    is_target_state,
    session as retry_session,
    stable_projection,
    upsert_direct_job,
)
from icims_inspector import UnsupportedIcimsUrl, derive_icims_endpoint, inspect_icims_url  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_STATE = "CT"
TIMEOUT = 25
MAX_SEARCH_PAGES = 5
JOB_LINK = re.compile(r"^/jobs/(\d+)(?:/[^?#]+)?/job/?$", re.I)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _job_in_scope(job: dict[str, Any], state: str) -> bool:
    states = {str(value).upper() for value in (job.get("states") or []) if value}
    profiles = {str(value).lower() for value in (job.get("profiles") or []) if value}
    return state.upper() in states and "cs" in profiles


def source_from_job(job: dict[str, Any], state: str = DEFAULT_STATE) -> dict[str, Any] | None:
    if not _job_in_scope(job, state):
        return None
    try:
        endpoint = derive_icims_endpoint(_clean(job.get("url")))
    except UnsupportedIcimsUrl:
        return None
    host = endpoint["host"]
    company = _clean(job.get("company")) or host.split(".", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", host.casefold()).strip("-")
    return {
        "key": f"{state.casefold()}-auto-icims-{slug}",
        "name": f"{company} (auto-discovered iCIMS)",
        "company": company,
        "kind": "icims",
        "host": host,
        "homepage": f"https://{host}/jobs/intro",
        "search_url": f"https://{host}/jobs/search",
        "state": state.upper(),
        "profile_hint": ["cs"],
        "auto_discovered": True,
    }


def discover_sources(feed: dict[str, Any], state: str = DEFAULT_STATE) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    jobs = [job for job in (feed.get("jobs") or []) if isinstance(job, dict)]
    jobs.sort(key=lambda job: (_clean(job.get("company")).casefold(), _clean(job.get("url")).casefold()))
    for job in jobs:
        source = source_from_job(job, state)
        if not source or source["host"] in seen:
            continue
        out.append(source)
        seen.add(source["host"])
    return out


def extract_job_links(raw_html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    links: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        parsed = urlparse(urljoin(base_url, href))
        if not JOB_LINK.fullmatch(parsed.path):
            continue
        canonical = urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
        try:
            info = derive_icims_endpoint(canonical)
        except UnsupportedIcimsUrl:
            continue
        links[info["job_id"]] = info["canonical_job_url"]
    return [links[key] for key in sorted(links, key=lambda value: int(value))]


def search_site(client: requests.Session, source: dict[str, Any]) -> list[str]:
    seen: dict[str, str] = {}
    for page in range(MAX_SEARCH_PAGES):
        response = client.get(
            source["search_url"],
            params={"ss": "1", "searchKeyword": "intern", "pr": page},
            headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": bf.USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        links = extract_job_links(response.text, source["search_url"])
        before = len(seen)
        for link in links:
            job_id = derive_icims_endpoint(link)["job_id"]
            seen.setdefault(job_id, link)
        if not links or len(seen) == before:
            break
    return list(seen.values())


def job_from_inspection(source: dict[str, Any], url: str, inspection: dict[str, Any], reference: datetime) -> dict[str, Any] | None:
    if inspection.get("status") != "inspected":
        return None
    posting = inspection.get("posting") or {}
    title = _clean(posting.get("title"))
    locations = ((posting.get("locations") or {}).get("values") or [])
    location = " ".join(_clean(value) for value in locations if _clean(value)) or "Location not listed"
    if not is_student_opportunity(title) or not is_cs_relevant_title(title):
        return None
    if not is_target_state(location, source["state"]):
        return None

    posted_at = bf.parse_date(posting.get("date_posted"), reference) if posting.get("date_posted") else None
    direct_source = {
        "key": source["key"],
        "name": source["name"],
        "url": source["homepage"],
        "profile_hint": ["cs"],
    }
    job = bf.base_job(
        company=source["company"],
        title=title,
        location=location,
        url=url,
        posted_raw=_clean(posting.get("date_posted")),
        source=direct_source,
        section="Auto-discovered iCIMS sibling role",
        function_primary="Computer Science / Technology",
        posted_at=posted_at,
    )
    if not job:
        return None
    job["direct_employer"] = True
    if source["state"] not in job.get("states", []):
        job["states"] = sorted(set(job.get("states", [])) | {source["state"]})
    return job


def fetch_source(client: requests.Session, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for url in search_site(client, source):
        inspection = inspect_icims_url(url, session=client)
        job = job_from_inspection(source, url, inspection, reference)
        if job:
            out.append(job)
    return out


def enrich(doc: dict[str, Any], old_doc: dict[str, Any], client: requests.Session, reference: datetime) -> dict[str, Any]:
    jobs = doc.setdefault("jobs", [])
    health = doc.setdefault("sources", {})
    old_jobs = old_doc.get("jobs", []) if isinstance(old_doc, dict) else []
    old_jobs_by_id = {j.get("id"): j for j in old_jobs if isinstance(j, dict) and j.get("id")}
    sources = discover_sources(doc)

    for source in sources:
        try:
            direct_jobs = fetch_source(client, source, reference)
            for job in direct_jobs:
                upsert_direct_job(jobs, job, old_jobs_by_id, reference)
            health[source["key"]] = {
                "ok": True,
                "configured": True,
                "count": len(direct_jobs),
                "name": source["name"],
                "direct": True,
                "auto_discovered": True,
            }
            print(f"{source['name']}: {len(direct_jobs)} direct CT CS-relevant listing(s)")
        except Exception as exc:
            health[source["key"]] = {
                "ok": False,
                "configured": True,
                "count": 0,
                "name": source["name"],
                "direct": True,
                "auto_discovered": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
            carry_failed_source(jobs, old_jobs, source["key"])
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
        print("Auto-discovered iCIMS coverage unchanged.")
        return 0
    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged auto-discovered iCIMS coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
