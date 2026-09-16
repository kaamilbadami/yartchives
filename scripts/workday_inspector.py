#!/usr/bin/env python3
"""Retrieve and conservatively normalize one public Workday job posting.

Workday career sites expose job details through a public CXS JSON endpoint. This
module derives that endpoint from an authoritative ``myworkdayjobs.com`` job URL,
then delegates provider-neutral description/requirement semantics to
``posting_requirements``.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse, urlunparse

import requests

from posting_requirements import (
    REQUIREMENT_FIELDS,
    clean_line,
    empty_requirement_field,
    extract_requirements,
    normalize_description,
)

# Backwards-compatible private alias for callers that predate the shared module.
_empty_field = empty_requirement_field

TIMEOUT = 25
INTERFACE = "workday_cxs_json"
WORKDAY_HOST = re.compile(r"^[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com$", re.I)
LOCALE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")


class UnsupportedWorkdayUrl(ValueError):
    """Raised when a URL cannot identify a public Workday CXS job endpoint."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def derive_cxs_endpoint(job_url: str) -> dict[str, str]:
    """Return tenant/site/job metadata derived from a public Workday URL."""

    parsed = urlparse(job_url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not WORKDAY_HOST.fullmatch(host):
        raise UnsupportedWorkdayUrl("expected an HTTPS *.wdN.myworkdayjobs.com job URL")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if parts and parts[0].lower() == "wday":
        if len(parts) < 7 or parts[1].lower() != "cxs" or parts[4].lower() != "job":
            raise UnsupportedWorkdayUrl("Workday CXS URL does not contain a job path")
        tenant, site = parts[2], parts[3]
        job_parts = parts[4:]
    else:
        if parts and LOCALE.fullmatch(parts[0]):
            parts = parts[1:]
        try:
            job_index = next(i for i, part in enumerate(parts) if part.lower() == "job")
        except StopIteration as exc:
            raise UnsupportedWorkdayUrl("Workday URL does not contain a /job/ path") from exc
        if job_index != 1 or len(parts) < 4:
            raise UnsupportedWorkdayUrl("Workday job URL must identify one career site and job")
        tenant = host.split(".", 1)[0]
        site = parts[0]
        job_parts = parts[job_index:]

    encoded = [quote(part, safe="-._~") for part in (tenant, site, *job_parts)]
    endpoint_path = "/wday/cxs/" + "/".join(encoded)
    endpoint = urlunparse(("https", host, endpoint_path, "", "", ""))
    canonical_job_path = "/" + "/".join(quote(part, safe="-._~") for part in (site, *job_parts))
    canonical_job_url = urlunparse(("https", host, canonical_job_path, "", "", ""))
    return {
        "tenant": tenant,
        "site": site,
        "job_path": "/" + "/".join(job_parts),
        "endpoint_url": endpoint,
        "canonical_job_url": canonical_job_url,
    }


def extract_locations(info: dict[str, Any]) -> dict[str, Any]:
    values: list[str] = []

    def append(value: Any) -> None:
        if isinstance(value, dict):
            value = value.get("descriptor") or value.get("name")
        if not isinstance(value, str):
            return
        cleaned = clean_line(value)
        if cleaned and cleaned.casefold() not in {item.casefold() for item in values}:
            values.append(cleaned)

    append(info.get("location"))
    append(info.get("jobRequisitionLocation"))
    additional = info.get("additionalLocations") or info.get("locations") or []
    if isinstance(additional, (str, dict)):
        additional = [additional]
    if isinstance(additional, list):
        for location in additional:
            append(location)
    return {
        "status": "authoritative" if values else "unknown",
        "values": values,
    }


def normalize_payload(payload: Any) -> dict[str, Any]:
    """Normalize one Workday CXS response or raise on a changed response shape."""

    if not isinstance(payload, dict) or not isinstance(payload.get("jobPostingInfo"), dict):
        raise ValueError("Workday response did not contain jobPostingInfo")
    info = payload["jobPostingInfo"]
    if not any(info.get(key) for key in ("title", "jobDescription", "jobReqId", "location")):
        raise ValueError("Workday jobPostingInfo did not contain recognizable job fields")

    description, lines = normalize_description(info.get("jobDescription"))
    requisition_id = clean_line(info.get("jobReqId")) or None
    posting_id = clean_line(info.get("jobPostingId")) or None
    can_apply = info.get("canApply") if isinstance(info.get("canApply"), bool) else None
    posted = info.get("posted") if isinstance(info.get("posted"), bool) else None
    if can_apply is False or posted is False:
        application_status = "unavailable"
    elif can_apply is True and posted is True:
        application_status = "available"
    else:
        application_status = "unknown"
    return {
        "posting": {
            "title": clean_line(info.get("title")) or None,
            "description": description or None,
            "requisition_id": requisition_id,
            "posting_id": posting_id,
            "locations": extract_locations(info),
            "can_apply": can_apply,
            "posted": posted,
            "application_status": application_status,
        },
        "requirements": extract_requirements(lines),
    }


def _base_result(job_url: str, inspected_at: datetime) -> dict[str, Any]:
    return {
        "provider": "workday",
        "status": "failed",
        "retrieval_confidence": "none",
        "error": None,
        "posting": None,
        "requirements": {key: empty_requirement_field() for key in REQUIREMENT_FIELDS},
        "provenance": {
            "provider": "workday",
            "interface": INTERFACE,
            "source_url": job_url,
            "endpoint_url": None,
            "inspected_at": iso(inspected_at),
        },
    }


def inspect_workday_url(
    job_url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    """Inspect a URL without raising; failures remain explicit structured data."""

    inspected_at = now()
    result = _base_result(job_url, inspected_at)
    try:
        endpoint = derive_cxs_endpoint(job_url)
    except UnsupportedWorkdayUrl as exc:
        result["status"] = "unsupported_url"
        result["error"] = str(exc)
        return result

    result["provenance"].update(
        {
            "endpoint_url": endpoint["endpoint_url"],
            "tenant": endpoint["tenant"],
            "site": endpoint["site"],
            "canonical_job_url": endpoint["canonical_job_url"],
        }
    )
    client = session or requests.Session()
    try:
        response = client.get(
            endpoint["endpoint_url"],
            headers={"Accept": "application/json", "User-Agent": "Yartchives/1.0 (+public job inspection)"},
            timeout=timeout,
        )
        if response.status_code in {404, 410}:
            result["status"] = "unavailable"
            result["error"] = f"Workday returned HTTP {response.status_code}"
            return result
        response.raise_for_status()
        normalized = normalize_payload(response.json())
    except requests.RequestException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    except (ValueError, json.JSONDecodeError) as exc:
        result["status"] = "changed_response"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result.update(normalized)
    result["status"] = "inspected"
    result["retrieval_confidence"] = (
        "high" if normalized["posting"].get("description") else "medium"
    )
    result["error"] = None
    return result


def inspect_listing(
    listing: dict[str, Any],
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    """Return a copied listing with inspection attached, even when it fails."""

    preserved = copy.deepcopy(listing)
    preserved["inspection"] = inspect_workday_url(
        str(listing.get("url") or ""), session=session, timeout=timeout, now=now
    )
    return preserved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Authoritative public Workday job URL")
    args = parser.parse_args()
    result = inspect_workday_url(args.url)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "inspected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
