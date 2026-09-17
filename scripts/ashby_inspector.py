#!/usr/bin/env python3
"""Retrieve and conservatively normalize one public Ashby job posting.

Ashby-hosted job URLs identify a public job-board name and posting UUID. Ashby's
official unauthenticated Job Postings API exposes all currently published postings
for a board; this adapter selects the requested posting by its canonical job/apply
URL and delegates requirement semantics to ``posting_requirements``.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse, urlunparse

import requests

import posting_requirements

TIMEOUT = 25
INTERFACE = "ashby_public_job_postings_api"
JOBS_HOST = "jobs.ashbyhq.com"
API_HOST = "api.ashbyhq.com"
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
BOARD_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class UnsupportedAshbyUrl(ValueError):
    """Raised when a URL cannot identify one Ashby-hosted public posting."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def derive_ashby_endpoint(job_url: str) -> dict[str, str]:
    parsed = urlparse(html.unescape(job_url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or host != JOBS_HOST:
        raise UnsupportedAshbyUrl("expected an HTTPS jobs.ashbyhq.com URL")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[2:] in ([], ["application"], ["apply"]):
        board = parts[0].strip().lower()
        posting_id = parts[1].strip().lower()
    else:
        raise UnsupportedAshbyUrl("Ashby URL must identify one hosted public job")

    if not board or board in {".", ".."} or not BOARD_RE.fullmatch(board):
        raise UnsupportedAshbyUrl("Ashby URL contains an invalid board name")
    if not UUID_RE.fullmatch(posting_id):
        raise UnsupportedAshbyUrl("Ashby URL must contain a posting UUID")

    encoded_board = quote(board, safe="-._~")
    canonical_path = f"/{encoded_board}/{posting_id}"
    canonical_url = urlunparse(("https", JOBS_HOST, canonical_path, "", "", ""))
    endpoint_path = f"/posting-api/job-board/{encoded_board}"
    endpoint_url = urlunparse(("https", API_HOST, endpoint_path, "", "", ""))
    return {
        "board_name": board,
        "posting_id": posting_id,
        "canonical_job_url": canonical_url,
        "endpoint_url": endpoint_url,
    }


def _canonical_posting_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return derive_ashby_endpoint(value)["canonical_job_url"]
    except UnsupportedAshbyUrl:
        return None


def _location_values(job: dict[str, Any]) -> list[str]:
    values: list[str] = []

    def append(value: Any) -> None:
        if not isinstance(value, str):
            return
        cleaned = posting_requirements.clean_line(value)
        if cleaned and cleaned.casefold() not in {item.casefold() for item in values}:
            values.append(cleaned)

    append(job.get("location"))
    secondary = job.get("secondaryLocations")
    if isinstance(secondary, list):
        for item in secondary:
            if isinstance(item, dict):
                append(item.get("location"))
    return values


def find_posting(payload: Any, canonical_job_url: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        raise ValueError("Ashby response was not a JSON object")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Ashby response did not contain a jobs list")
    for job in jobs:
        if not isinstance(job, dict):
            continue
        candidates = {
            _canonical_posting_url(job.get("jobUrl")),
            _canonical_posting_url(job.get("applyUrl")),
        }
        if canonical_job_url in candidates:
            return job
    return None


def normalize_payload(job: Any, *, posting_id: str) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise ValueError("Ashby posting was not a JSON object")
    if not any(job.get(key) for key in ("title", "descriptionPlain", "descriptionHtml", "jobUrl")):
        raise ValueError("Ashby posting did not contain recognizable job fields")

    source_description = job.get("descriptionHtml") or job.get("descriptionPlain")
    description, lines = posting_requirements.normalize_description(source_description)
    locations = _location_values(job)
    listed = job.get("isListed")
    return {
        "posting": {
            "title": posting_requirements.clean_line(job.get("title")) or None,
            "description": description or None,
            "requisition_id": None,
            "posting_id": posting_id,
            "internal_job_id": None,
            "locations": {
                "status": "authoritative" if locations else "unknown",
                "values": locations,
            },
            "can_apply": True,
            "posted": True,
            "application_status": "available",
            "first_published": posting_requirements.clean_line(job.get("publishedAt")) or None,
            "updated_at": None,
            "application_deadline": None,
            "employment_type": posting_requirements.clean_line(job.get("employmentType")) or None,
            "workplace_type": posting_requirements.clean_line(job.get("workplaceType")) or None,
            "is_remote": job.get("isRemote") if isinstance(job.get("isRemote"), bool) else None,
            "is_listed": listed if isinstance(listed, bool) else None,
        },
        "requirements": posting_requirements.extract_requirements(lines),
        "document_url": posting_requirements.clean_line(job.get("jobUrl")) or None,
        "apply_url": posting_requirements.clean_line(job.get("applyUrl")) or None,
    }


def _base_result(job_url: str, inspected_at: datetime) -> dict[str, Any]:
    return {
        "provider": "ashby",
        "status": "failed",
        "retrieval_confidence": "none",
        "error": None,
        "posting": None,
        "requirements": {
            key: posting_requirements.empty_requirement_field()
            for key in posting_requirements.REQUIREMENT_FIELDS
        },
        "provenance": {
            "provider": "ashby",
            "interface": INTERFACE,
            "source_url": job_url,
            "endpoint_url": None,
            "inspected_at": iso(inspected_at),
        },
    }


def inspect_ashby_url(
    job_url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    inspected_at = now()
    result = _base_result(job_url, inspected_at)
    try:
        endpoint = derive_ashby_endpoint(job_url)
    except UnsupportedAshbyUrl as exc:
        result["status"] = "unsupported_url"
        result["error"] = str(exc)
        return result

    result["provenance"].update(
        {
            "endpoint_url": endpoint["endpoint_url"],
            "canonical_job_url": endpoint["canonical_job_url"],
            "board_name": endpoint["board_name"],
            "posting_id": endpoint["posting_id"],
        }
    )
    client = session or requests.Session()
    try:
        response = client.get(
            endpoint["endpoint_url"],
            headers={
                "Accept": "application/json",
                "User-Agent": "Yartchives/1.0 (+public job inspection)",
            },
            timeout=timeout,
        )
        if response.status_code in {404, 410}:
            result["status"] = "unavailable"
            result["error"] = f"Ashby returned HTTP {response.status_code}"
            return result
        response.raise_for_status()
        posting = find_posting(response.json(), endpoint["canonical_job_url"])
        if posting is None:
            result["status"] = "unavailable"
            result["error"] = "Ashby board no longer contains the requested published posting"
            return result
        normalized = normalize_payload(posting, posting_id=endpoint["posting_id"])
    except requests.RequestException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    except (ValueError, json.JSONDecodeError) as exc:
        result["status"] = "changed_response"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    document_url = normalized.pop("document_url", None)
    apply_url = normalized.pop("apply_url", None)
    result.update(normalized)
    if document_url:
        result["provenance"]["document_url"] = document_url
    if apply_url:
        result["provenance"]["apply_url"] = apply_url
    result["status"] = "inspected"
    result["retrieval_confidence"] = "high" if result["posting"].get("description") else "medium"
    result["error"] = None
    return result


def inspect_listing(
    listing: dict[str, Any],
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    preserved = copy.deepcopy(listing)
    preserved["inspection"] = inspect_ashby_url(
        str(listing.get("url") or ""), session=session, timeout=timeout, now=now
    )
    return preserved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Authoritative public Ashby-hosted job URL")
    args = parser.parse_args()
    result = inspect_ashby_url(args.url)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "inspected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
