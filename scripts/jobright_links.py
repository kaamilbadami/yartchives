#!/usr/bin/env python3
"""Recover official employer links from Jobright's public visitor search API.

The public-sector GitHub feed only exposes Jobright detail URLs, but Jobright's
unauthenticated visitor search response includes the original employer/apply
URL. We query by title and only upgrade a row when the API returns the exact
Jobright job id from the listing URL. Ambiguous/search-only matches are ignored.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import repair_links as links  # noqa: E402

API_URL = "https://jobright.ai/swan/recommend/visitor-list/jobs"
TIMEOUT = 15
WORKERS = 12
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def clean_title(value: str | None) -> str:
    text = value or ""
    # Public-sector markdown titles can retain bold markers after upstream parsing.
    text = text.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", text).strip()


def jobright_id(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.netloc.lower() not in {"jobright.ai", "www.jobright.ai"}:
        return ""
    match = re.fullmatch(r"/jobs/info/([^/?#]+)", parsed.path.rstrip("/"))
    return match.group(1) if match else ""


def visitor_payload(title: str, position: int = 0, count: int = 30) -> dict[str, Any]:
    return {
        "value": clean_title(title),
        "country": "US",
        "jobTaxonomyList": [],
        "locations": [],
        "jobTypes": [],
        "seniority": [],
        "workModel": [],
        "searchType": "job_title",
        "companies": [],
        "isH1BOnly": False,
        "excludedCompanies": [],
        "position": position,
        "count": count,
    }


def response_jobs(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result")
    if isinstance(result, list):
        rows = result
    elif isinstance(result, dict):
        rows = result.get("jobList") or result.get("list") or result.get("jobs") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def row_job_result(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("jobResult")
    return value if isinstance(value, dict) else row


def direct_from_exact_id(rows: list[dict[str, Any]], target_id: str) -> str | None:
    exact: list[dict[str, Any]] = []
    for row in rows:
        job = row_job_result(row)
        candidate_id = str(job.get("jobId") or job.get("id") or job.get("listingId") or "")
        if candidate_id == target_id:
            exact.append(job)
    if len(exact) != 1:
        return None
    job = exact[0]
    for key in ("originalUrl", "applyLink"):
        value = job.get(key)
        if links.is_direct_application_url(value):
            return str(value)
    return None


def fetch_exact_direct(listing_url: str, title: str) -> str | None:
    target_id = jobright_id(listing_url)
    title = clean_title(title)
    if not target_id or not title:
        return None

    params = {
        "sortCondition": "0",
        "count": "30",
        "position": "0",
        "useLegacySearch": "true",
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://jobright.ai/",
        "Origin": "https://jobright.ai",
        "x-client-type": "web",
    }
    try:
        response = requests.post(
            API_URL,
            params=params,
            json=visitor_payload(title),
            headers=headers,
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return None
        direct = direct_from_exact_id(response_jobs(response.json()), target_id)
    except (requests.RequestException, ValueError):
        return None

    if not direct:
        return None
    # Validate before this URL can become an Apply button.
    return links.validate_candidate_once(direct)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/listings.json")
    args = parser.parse_args()

    path = Path(args.path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    targets = [
        job for job in doc.get("jobs", [])
        if isinstance(job, dict)
        and job.get("link_kind") == "listing"
        and jobright_id(job.get("listing_url"))
    ]

    upgrades: list[tuple[dict[str, Any], str]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(fetch_exact_direct, job.get("listing_url") or "", job.get("title") or ""): job
            for job in targets
        }
        for future in as_completed(futures):
            job = futures[future]
            try:
                direct = future.result()
            except Exception as exc:
                print(f"warning: Jobright resolver failed for {job.get('company')}: {exc}", file=sys.stderr)
                direct = None
            if direct:
                upgrades.append((job, direct))

    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for job, direct in upgrades:
        listing = job.get("listing_url") or ""
        status, final = links.validate_direct_url(direct)
        if status == "dead":
            continue
        job["resolved_from_url"] = listing
        job["url"] = final if links.is_direct_application_url(final) else direct
        job.pop("listing_url", None)
        job["link_kind"] = "direct"
        job["link_origin"] = "jobright-visitor-api"
        job["link_status"] = status
        job["link_checked_at"] = checked_at

    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Jobright direct-link recovery: {len(upgrades)} of {len(targets)} listing(s) upgraded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
