#!/usr/bin/env python3
"""Add CS-relevant student roles from Greenhouse boards already evidenced in-feed.

This is a provider-family gap filler, not a broad Greenhouse crawler. A public
board becomes eligible only when the normalized feed already contains a CS
listing with an authoritative Greenhouse-hosted job URL. We then enumerate that
same board through Greenhouse's public Job Board API and merge additional US
student roles with strong CS/technology title evidence.
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
from urllib.parse import quote

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
from greenhouse_inspector import UnsupportedGreenhouseUrl, derive_greenhouse_endpoint  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
TIMEOUT = 25
API_HOST = "https://boards-api.greenhouse.io"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any) -> str:
    return bf.clean_text(value).strip()


def _evidences_cs(job: dict[str, Any]) -> bool:
    return "cs" in {str(value).lower() for value in (job.get("profiles") or []) if value}


def source_from_job(job: dict[str, Any]) -> dict[str, Any] | None:
    if not _evidences_cs(job):
        return None
    if job.get("link_kind") not in {None, "direct"}:
        return None
    try:
        endpoint = derive_greenhouse_endpoint(_clean(job.get("url")))
    except UnsupportedGreenhouseUrl:
        return None
    board_token = endpoint["board_token"]
    company = _clean(job.get("company")) or board_token
    slug = re.sub(r"[^a-z0-9]+", "-", board_token.casefold()).strip("-")
    return {
        "key": f"auto-greenhouse-{slug}",
        "name": f"{company} (auto-discovered Greenhouse)",
        "company": company,
        "kind": "greenhouse",
        "board_token": board_token,
        "homepage": f"https://job-boards.greenhouse.io/{quote(board_token, safe='-._~')}",
        "api_url": f"{API_HOST}/v1/boards/{quote(board_token, safe='-._~')}/jobs",
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
        if not source or source["board_token"] in seen:
            continue
        out.append(source)
        seen.add(source["board_token"])
    return out


def _location(item: dict[str, Any]) -> str:
    location = item.get("location")
    if isinstance(location, dict):
        return _clean(location.get("name")) or "Location not listed"
    return _clean(location) or "Location not listed"


def _board_token_company(company: str, board_token: str) -> bool:
    return re.sub(r"[^a-z0-9]+", "", company.casefold()) == re.sub(r"[^a-z0-9]+", "", board_token.casefold())


def company_from_board_html(html: str, fallback: str) -> str:
    text = html or ""
    patterns = (
        r"<title>\s*Jobs at\s+(.+?)\s*</title>",
        r"<h1[^>]*>\s*Current openings at\s+(.+?)\s*</h1>",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if not match:
            continue
        value = re.sub(r"<[^>]+>", " ", unescape(match.group(1)))
        value = _clean(re.sub(r"\s+", " ", value))
        if value:
            return value
    return fallback


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


def job_from_item(source: dict[str, Any], item: dict[str, Any], reference: datetime) -> dict[str, Any] | None:
    title = _clean(item.get("title"))
    location = _location(item)
    if not is_student_opportunity(title) or not is_cs_relevant_title(title):
        return None
    if not _looks_us(location):
        return None

    job_id = str(item.get("id") or "").strip()
    if not job_id.isdigit():
        return None
    url = _clean(item.get("absolute_url")) or f"{source['homepage']}/jobs/{job_id}"
    try:
        endpoint = derive_greenhouse_endpoint(url)
        if endpoint["board_token"] != source["board_token"] or endpoint["job_id"] != job_id:
            return None
        url = endpoint["canonical_job_url"]
    except UnsupportedGreenhouseUrl:
        url = f"https://job-boards.greenhouse.io/{quote(source['board_token'], safe='-._~')}/jobs/{job_id}"

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
        posted_raw="",
        source=direct_source,
        section="Auto-discovered Greenhouse sibling role",
        function_primary="Computer Science / Technology",
        posted_at=None,
    )
    if not job:
        return None
    job["direct_employer"] = True
    job["greenhouse_board_token"] = source["board_token"]
    job["greenhouse_job_id"] = job_id
    return job


def fetch_source(client: requests.Session, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    source = dict(source)
    if _board_token_company(_clean(source.get("company")), _clean(source.get("board_token"))):
        try:
            board_response = client.get(
                source["homepage"],
                headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": bf.USER_AGENT},
                timeout=TIMEOUT,
            )
            if getattr(board_response, "status_code", 200) < 400:
                source["company"] = company_from_board_html(getattr(board_response, "text", ""), source["company"])
                source["name"] = f"{source['company']} (auto-discovered Greenhouse)"
        except requests.RequestException:
            pass

    response = client.get(
        source["api_url"],
        headers={"Accept": "application/json", "User-Agent": bf.USER_AGENT},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("Greenhouse board response did not contain a jobs list")

    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
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
    return out


def enrich(doc: dict[str, Any], old_doc: dict[str, Any], client: requests.Session, reference: datetime) -> dict[str, Any]:
    jobs = doc.setdefault("jobs", [])
    health = doc.setdefault("sources", {})
    old_jobs = old_doc.get("jobs", []) if isinstance(old_doc, dict) else []
    old_jobs_by_id = {j.get("id"): j for j in old_jobs if isinstance(j, dict) and j.get("id")}

    for source in discover_sources(doc):
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
            print(f"{source['name']}: {len(direct_jobs)} direct US CS student listing(s)")
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
        print("Auto-discovered Greenhouse coverage unchanged.")
        return 0
    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged auto-discovered Greenhouse coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
