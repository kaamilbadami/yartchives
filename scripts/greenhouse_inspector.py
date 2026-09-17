#!/usr/bin/env python3
"""Retrieve and conservatively normalize one public Greenhouse job posting.

Greenhouse-hosted job URLs identify a public board token and job-post ID. The
official, unauthenticated Job Board API exposes the published posting as JSON;
this adapter only handles retrieval/normalization and delegates all requirement
semantics to ``posting_requirements``.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urlparse, urlunparse

import requests

import posting_requirements

TIMEOUT = 25
INTERFACE = "greenhouse_job_board_api"
CANONICAL_HOST = "job-boards.greenhouse.io"
API_HOST = "boards-api.greenhouse.io"
GREENHOUSE_HOSTS = {CANONICAL_HOST, "boards.greenhouse.io"}
BOARD_TOKEN = re.compile(r"^[A-Za-z0-9._-]+$")


class UnsupportedGreenhouseUrl(ValueError):
    """Raised when a URL cannot identify a hosted public Greenhouse posting."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def derive_greenhouse_endpoint(job_url: str) -> dict[str, str]:
    """Return deterministic board/job identity and the public Job Board API URL."""

    parsed = urlparse(html.unescape(job_url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or host not in GREENHOUSE_HOSTS:
        raise UnsupportedGreenhouseUrl("expected an HTTPS Greenhouse-hosted job board URL")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) == 3 and parts[1].lower() == "jobs" and parts[2].isdigit():
        board_token = parts[0].strip().lower()
        job_id = parts[2]
    elif [part.lower() for part in parts] == ["embed", "job_app"]:
        query = parse_qs(parsed.query)
        board_token = (query.get("for") or [""])[0].strip().lower()
        job_id = (query.get("token") or [""])[0].strip()
        if not job_id.isdigit():
            raise UnsupportedGreenhouseUrl(
                "Greenhouse embedded application URL needs numeric token and board"
            )
    else:
        raise UnsupportedGreenhouseUrl(
            "Greenhouse URL must identify one hosted or embedded public job"
        )
    if (
        not board_token
        or board_token in {".", ".."}
        or not BOARD_TOKEN.fullmatch(board_token)
    ):
        raise UnsupportedGreenhouseUrl("Greenhouse URL contains an invalid board token")

    encoded_board = quote(board_token, safe="-._~")
    canonical_path = f"/{encoded_board}/jobs/{job_id}"
    canonical_url = urlunparse(("https", CANONICAL_HOST, canonical_path, "", "", ""))
    endpoint_path = f"/v1/boards/{encoded_board}/jobs/{job_id}"
    endpoint_url = urlunparse(("https", API_HOST, endpoint_path, "", "", ""))
    return {
        "board_token": board_token,
        "job_id": job_id,
        "canonical_job_url": canonical_url,
        "endpoint_url": endpoint_url,
    }


def _location_values(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []

    def append(value: Any) -> None:
        if not isinstance(value, str):
            return
        for part in value.split(";"):
            cleaned = posting_requirements.clean_line(part)
            if cleaned and cleaned.casefold() not in {item.casefold() for item in values}:
                values.append(cleaned)

    location = payload.get("location")
    if isinstance(location, dict):
        append(location.get("name"))
    elif isinstance(location, str):
        append(location)

    if not values:
        offices = payload.get("offices")
        if isinstance(offices, list):
            for office in offices:
                if not isinstance(office, dict):
                    continue
                append(office.get("location") or office.get("name"))
    return values


def normalize_payload(
    payload: Any,
    *,
    board_token: str,
    expected_job_id: str,
) -> dict[str, Any]:
    """Normalize one Greenhouse Job Board API response."""

    if not isinstance(payload, dict):
        raise ValueError("Greenhouse response was not a JSON object")
    response_id = str(payload.get("id") or "").strip()
    if not response_id or response_id != expected_job_id:
        raise ValueError("Greenhouse response did not match the requested job ID")
    if not any(payload.get(key) for key in ("title", "content", "location", "requisition_id")):
        raise ValueError("Greenhouse response did not contain recognizable job fields")

    description, lines = posting_requirements.normalize_description(payload.get("content"))
    locations = _location_values(payload)
    return {
        "posting": {
            "title": posting_requirements.clean_line(payload.get("title")) or None,
            "description": description or None,
            "requisition_id": posting_requirements.clean_line(payload.get("requisition_id")) or None,
            "posting_id": response_id,
            "internal_job_id": (
                str(payload["internal_job_id"]) if payload.get("internal_job_id") is not None else None
            ),
            "locations": {
                "status": "authoritative" if locations else "unknown",
                "values": locations,
            },
            "can_apply": True,
            "posted": True,
            "application_status": "available",
            "first_published": posting_requirements.clean_line(payload.get("first_published")) or None,
            "updated_at": posting_requirements.clean_line(payload.get("updated_at")) or None,
            "application_deadline": posting_requirements.clean_line(payload.get("application_deadline")) or None,
        },
        "schedule": posting_requirements.extract_posting_schedule(lines),
        "requirements": posting_requirements.extract_requirements(lines),
        "document_url": posting_requirements.clean_line(payload.get("absolute_url")) or None,
        "board_token": board_token,
    }


def _base_result(job_url: str, inspected_at: datetime) -> dict[str, Any]:
    return {
        "provider": "greenhouse",
        "status": "failed",
        "retrieval_confidence": "none",
        "error": None,
        "posting": None,
        "requirements": {
            key: posting_requirements.empty_requirement_field()
            for key in posting_requirements.REQUIREMENT_FIELDS
        },
        "provenance": {
            "provider": "greenhouse",
            "interface": INTERFACE,
            "source_url": job_url,
            "endpoint_url": None,
            "inspected_at": iso(inspected_at),
        },
    }


def inspect_greenhouse_url(
    job_url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    """Inspect a Greenhouse URL without raising; failures stay structured."""

    inspected_at = now()
    result = _base_result(job_url, inspected_at)
    try:
        endpoint = derive_greenhouse_endpoint(job_url)
    except UnsupportedGreenhouseUrl as exc:
        result["status"] = "unsupported_url"
        result["error"] = str(exc)
        return result

    result["provenance"].update(
        {
            "endpoint_url": endpoint["endpoint_url"],
            "canonical_job_url": endpoint["canonical_job_url"],
            "board_token": endpoint["board_token"],
            "job_id": endpoint["job_id"],
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
            result["error"] = f"Greenhouse returned HTTP {response.status_code}"
            return result
        response.raise_for_status()
        normalized = normalize_payload(
            response.json(),
            board_token=endpoint["board_token"],
            expected_job_id=endpoint["job_id"],
        )
    except requests.RequestException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    except (ValueError, json.JSONDecodeError) as exc:
        result["status"] = "changed_response"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    document_url = normalized.pop("document_url", None)
    normalized.pop("board_token", None)
    result.update(normalized)
    if document_url:
        result["provenance"]["document_url"] = document_url
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
    preserved = copy.deepcopy(listing)
    preserved["inspection"] = inspect_greenhouse_url(
        str(listing.get("url") or ""), session=session, timeout=timeout, now=now
    )
    return preserved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Authoritative public Greenhouse-hosted job URL")
    args = parser.parse_args()
    result = inspect_greenhouse_url(args.url)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "inspected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
