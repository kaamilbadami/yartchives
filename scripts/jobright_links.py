#!/usr/bin/env python3
"""Recover official employer links from Jobright's public visitor search API.

The public-sector GitHub feed only exposes Jobright detail URLs, while Jobright's
unauthenticated visitor search response can expose the original employer/apply
URL. The current public detail page also exposes the canonical Jobright ID and
normalized job metadata, though it does not consistently expose an employer URL.
Prefer an exact Jobright ID match. Some public category-feed IDs are not the
same identifier returned by visitor search, so a second path accepts exactly one
result only when normalized title, company, and location all match.
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
DETAIL_SCRIPT_ID = "jobright-helper-job-detail-info"
TIMEOUT = 15
WORKERS = 12
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def clean_text(value: str | None) -> str:
    text = value or ""
    text = text.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", text).strip()


def clean_title(value: str | None) -> str:
    return clean_text(value)


def norm(value: str | None) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(value).lower())


def norm_location(value: str | None) -> str:
    text = norm(value)
    text = re.sub(r"\b(united states of america|united states|usa|us)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def locations_match(left: str | None, right: str | None) -> bool:
    a = norm_location(left)
    b = norm_location(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def jobright_id(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.netloc.lower() not in {"jobright.ai", "www.jobright.ai"}:
        return ""
    match = re.fullmatch(r"/jobs/info/([^/?#]+)", parsed.path.rstrip("/"))
    return match.group(1) if match else ""


def visitor_payload(title: str, position: int = 0, count: int = 40) -> dict[str, Any]:
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


def detail_data_from_html(text: str) -> dict[str, Any] | None:
    """Read the public detail-page JSON without treating the page as a candidate.

    Jobright's server-rendered detail page currently puts its job object in a
    script tagged ``jobright-helper-job-detail-info``.  The helper deliberately
    returns only that structured object; it does not mine arbitrary page links,
    which could associate a listing with an unrelated employer job.
    """
    match = re.search(
        rf'<script[^>]*\bid=["\']{DETAIL_SCRIPT_ID}["\'][^>]*>(.*?)</script>',
        text,
        flags=re.I | re.S,
    )
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def detail_row(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert the detail-page object into the same row shape as visitor search."""
    if not isinstance(value, dict):
        return None
    job = value.get("jobResult")
    if not isinstance(job, dict):
        return None
    row: dict[str, Any] = {"jobResult": job}
    company = value.get("companyResult")
    if isinstance(company, dict):
        row["companyResult"] = company
    return row


def row_job_result(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("jobResult")
    return value if isinstance(value, dict) else row


def row_company(row: dict[str, Any]) -> str:
    company_result = row.get("companyResult")
    if isinstance(company_result, dict) and company_result.get("companyName"):
        return str(company_result.get("companyName"))
    job = row_job_result(row)
    return str(job.get("companyName") or job.get("company") or "")


def direct_from_job(job: dict[str, Any]) -> str | None:
    for key in ("originalUrl", "applyLink"):
        value = job.get(key)
        if links.is_direct_application_url(value):
            return str(value)
    return None


def direct_from_exact_id(rows: list[dict[str, Any]], target_id: str) -> str | None:
    exact: list[dict[str, Any]] = []
    for row in rows:
        job = row_job_result(row)
        candidate_id = str(job.get("jobId") or job.get("id") or job.get("listingId") or "")
        if candidate_id == target_id:
            exact.append(job)
    if len(exact) != 1:
        return None
    return direct_from_job(exact[0])


def direct_from_exact_metadata(
    rows: list[dict[str, Any]], company: str, title: str, location: str
) -> str | None:
    """Return a direct link only for one exact title/company/location result."""
    target_title = norm(title)
    target_company = compact(company)
    matches: set[str] = set()
    for row in rows:
        job = row_job_result(row)
        if norm(job.get("jobTitle") or job.get("title")) != target_title:
            continue
        if compact(row_company(row)) != target_company:
            continue
        candidate_location = str(job.get("jobLocation") or job.get("location") or "")
        if not locations_match(location, candidate_location):
            continue
        if direct_from_job(job):
            matches.add(direct_from_job(job))
    if len(matches) != 1:
        return None
    return next(iter(matches))


def metadata_targets(
    job_record: dict[str, Any], detail: dict[str, Any] | None,
) -> list[tuple[str, str, str]]:
    """Return distinct exact-metadata targets, preferring Jobright's own page."""
    targets: list[tuple[str, str, str]] = []
    row = detail_row(detail)
    if row:
        job = row_job_result(row)
        targets.append((
            row_company(row),
            str(job.get("jobTitle") or job.get("title") or ""),
            str(job.get("jobLocation") or job.get("location") or ""),
        ))
    targets.append((
        str(job_record.get("company") or ""),
        str(job_record.get("title") or ""),
        str(job_record.get("location") or ""),
    ))
    unique: list[tuple[str, str, str]] = []
    for target in targets:
        if target[0] and target[1] and target[2] and target not in unique:
            unique.append(target)
    return unique


def search_titles(job_record: dict[str, Any], detail: dict[str, Any] | None) -> list[str]:
    """Use the source title plus Jobright's normalized title when available."""
    titles = [clean_title(job_record.get("title"))]
    row = detail_row(detail)
    if row:
        job = row_job_result(row)
        titles.extend([
            clean_title(job.get("jobNlpTitle")),
            clean_title(job.get("jobTitle") or job.get("title")),
        ])
    return list(dict.fromkeys(title for title in titles if title))


def fetch_detail(listing_url: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            listing_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return None
        return detail_data_from_html(response.text)
    except requests.RequestException:
        return None


def fetch_direct(job_record: dict[str, Any]) -> tuple[str | None, str]:
    listing_url = str(job_record.get("listing_url") or "")
    target_id = jobright_id(listing_url)
    if not target_id:
        return None, "none"

    detail = fetch_detail(listing_url)
    detail_candidate = direct_from_exact_id([detail_row(detail)] if detail_row(detail) else [], target_id)
    if detail_candidate:
        validated = links.validate_candidate_once(detail_candidate)
        return (validated, "jobright-detail-id") if validated else (None, "validation-failed")

    params = {
        "sortCondition": "0",
        "count": "40",
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
    rows: list[dict[str, Any]] = []
    for title in search_titles(job_record, detail):
        try:
            response = requests.post(
                API_URL,
                params=params,
                json=visitor_payload(title),
                headers=headers,
                timeout=TIMEOUT,
            )
            if response.status_code != 200:
                continue
            rows.extend(response_jobs(response.json()))
        except (requests.RequestException, ValueError):
            continue

    if not rows:
        return None, "no-match"

    direct = direct_from_exact_id(rows, target_id)
    origin = "jobright-id"
    if not direct:
        for company, title, location in metadata_targets(job_record, detail):
            direct = direct_from_exact_metadata(rows, company, title, location)
            if direct:
                origin = "jobright-metadata"
                break
    if not direct:
        return None, "no-match"

    validated = links.validate_candidate_once(direct)
    return (validated, origin) if validated else (None, "validation-failed")


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

    upgrades: list[tuple[dict[str, Any], str, str]] = []
    outcomes: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_direct, job): job for job in targets}
        for future in as_completed(futures):
            job = futures[future]
            try:
                direct, origin = future.result()
            except Exception as exc:
                print(f"warning: Jobright resolver failed for {job.get('company')}: {exc}", file=sys.stderr)
                direct, origin = None, "exception"
            outcomes[origin] = outcomes.get(origin, 0) + 1
            if direct:
                upgrades.append((job, direct, origin))

    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    committed = 0
    for job, direct, origin in upgrades:
        listing = job.get("listing_url") or ""
        status, final = links.validate_direct_url(direct)
        if status == "dead":
            continue
        job["resolved_from_url"] = listing
        job["url"] = final if links.is_direct_application_url(final) else direct
        job.pop("listing_url", None)
        job["link_kind"] = "direct"
        job["link_origin"] = origin
        job["link_status"] = status
        job["link_checked_at"] = checked_at
        committed += 1

    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    detail = ", ".join(f"{key}={value}" for key, value in sorted(outcomes.items()))
    print(f"Jobright direct-link recovery: {committed} of {len(targets)} listing(s) upgraded; {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
