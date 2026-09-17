#!/usr/bin/env python3
"""Retrieve and conservatively normalize one public iCIMS job posting.

Classic public iCIMS career portals expose the actual posting in an iframe view.
That view normally contains Schema.org ``JobPosting`` JSON-LD, which is preferred
over presentation HTML. Generic iCIMS classes are used only as fallbacks.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from posting_requirements import (
    REQUIREMENT_FIELDS,
    clean_line,
    empty_requirement_field,
    extract_requirements,
    extract_posting_schedule,
    normalize_description,
)

TIMEOUT = 25
INTERFACE = "icims_jobposting_jsonld"
ICIMS_HOST = re.compile(r"^(?:[a-z0-9-]+\.)+icims\.com$", re.I)
UNAVAILABLE_TEXT = (
    re.compile(r"job that you were looking for .* no longer open", re.I),
    re.compile(r"job (?:is|has been) no longer (?:open|available)", re.I),
    re.compile(r"position (?:is|has been) no longer (?:open|available)", re.I),
    re.compile(r"job has been filled", re.I),
)


class UnsupportedIcimsUrl(ValueError):
    """Raised when a URL cannot identify a public iCIMS job posting."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def derive_icims_endpoint(job_url: str) -> dict[str, str]:
    """Return a deterministic identity and public iframe URL for an iCIMS job."""

    decoded_url = html.unescape(job_url or "")
    parsed = urlparse(decoded_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not ICIMS_HOST.fullmatch(host):
        raise UnsupportedIcimsUrl("expected an HTTPS *.icims.com job URL")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0].lower() != "jobs" or not parts[1].isdigit():
        raise UnsupportedIcimsUrl("iCIMS URL does not contain a /jobs/<numeric-id>/ path")
    if parts[-1].lower() not in {"job", "login"} or len(parts) > 4:
        raise UnsupportedIcimsUrl("iCIMS job URL must end in /job or /login")

    job_id = parts[1]
    canonical_path = f"/jobs/{job_id}/job"
    canonical_url = urlunparse(("https", host, canonical_path, "", "", ""))
    endpoint_url = urlunparse(
        ("https", host, canonical_path, "", urlencode({"in_iframe": "1"}), "")
    )
    return {
        "host": host,
        "job_id": job_id,
        "canonical_job_url": canonical_url,
        "endpoint_url": endpoint_url,
    }


def _job_postings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _job_postings(item)
        return
    if not isinstance(value, dict):
        return
    types = value.get("@type")
    if isinstance(types, str):
        types = [types]
    if isinstance(types, list) and any(str(item).casefold() == "jobposting" for item in types):
        yield value
    for key in ("@graph", "mainEntity", "itemListElement"):
        if key in value:
            yield from _job_postings(value[key])


def extract_jobposting_jsonld(soup: BeautifulSoup) -> dict[str, Any] | None:
    """Return the first recognizable JobPosting JSON-LD object."""

    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        for posting in _job_postings(payload):
            if posting.get("title") or posting.get("description"):
                return posting
    return None


def _fallback_description(soup: BeautifulSoup) -> str | None:
    """Collect generic iCIMS posting sections without navigation/apply chrome."""

    blocks: list[str] = []
    for heading in soup.select("h2.iCIMS_InfoField_Job"):
        title = clean_line(heading.get_text(" "))
        content = heading.find_next_sibling("div", class_="iCIMS_InfoMsg_Job")
        if title:
            blocks.append(f"<h2>{html.escape(title)}</h2>")
        if content is not None:
            expandable = content.select_one(".iCIMS_Expandable_Text") or content
            blocks.append(str(expandable))
    return "\n".join(blocks) or None


def _header_fields(soup: BeautifulSoup) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in soup.select(".iCIMS_JobHeaderTag"):
        label = item.select_one(".iCIMS_JobHeaderField")
        value = item.select_one(".iCIMS_JobHeaderData")
        key = clean_line(label.get_text(" ") if label else "")
        data = clean_line(value.get_text(" ") if value else "")
        if key and data:
            fields[key.casefold()] = data
    return fields


def _location_value(value: Any) -> str | None:
    if isinstance(value, str):
        return clean_line(value) or None
    if not isinstance(value, dict):
        return None
    address = value.get("address") if isinstance(value.get("address"), dict) else value
    pieces: list[str] = []
    for key in ("addressLocality", "addressRegion", "postalCode", "addressCountry"):
        piece = clean_line(address.get(key))
        if piece and piece.casefold() not in {"unavailable", "n/a", "none"}:
            pieces.append(piece)
    if not pieces and clean_line(value.get("name")):
        pieces.append(clean_line(value.get("name")))
    return ", ".join(dict.fromkeys(pieces)) or None


def extract_locations(posting: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    values: list[str] = []
    raw = posting.get("jobLocation")
    locations = raw if isinstance(raw, list) else [raw]
    for location in locations:
        value = _location_value(location)
        if value and value.casefold() not in {item.casefold() for item in values}:
            values.append(value)
    if not values:
        for key, value in headers.items():
            if "location" in key and value.casefold() not in {item.casefold() for item in values}:
                values.append(value)
    return {"status": "authoritative" if values else "unknown", "values": values}


def _requisition_id(headers: dict[str, str], description: str | None) -> str | None:
    for label in ("requisition id", "job id", "id"):
        if clean_line(headers.get(label)):
            return clean_line(headers[label])
    if description:
        match = re.search(r"(?:^|\n)ID\s*\n([^\n]+)(?:\n|$)", description, flags=re.I)
        if match:
            return clean_line(match.group(1)) or None
    return None


def _is_unavailable(soup: BeautifulSoup) -> bool:
    text = clean_line(soup.get_text(" "))
    return any(pattern.search(text) for pattern in UNAVAILABLE_TEXT)


def normalize_html(raw_html: str, *, job_id: str) -> dict[str, Any]:
    """Normalize one public iCIMS iframe response."""

    soup = BeautifulSoup(raw_html or "", "html.parser")
    if _is_unavailable(soup):
        return {"status": "unavailable"}

    posting = extract_jobposting_jsonld(soup)
    structured = posting is not None
    fallback_html = _fallback_description(soup)
    if not posting:
        if not fallback_html:
            raise ValueError("iCIMS response contained neither JobPosting JSON-LD nor job content")
        title_node = soup.select_one("#iCIMS_Header") or soup.select_one("h1.iCIMS_Header")
        posting = {
            "title": clean_line(title_node.get_text(" ") if title_node else ""),
            "description": fallback_html,
        }

    raw_description = posting.get("description") or fallback_html
    description, lines = normalize_description(str(raw_description or ""))
    headers = _header_fields(soup)
    apply_button = soup.select_one(".iCIMS_ApplyOnlineButton") is not None
    direct_apply = (
        posting.get("directApply") if isinstance(posting.get("directApply"), bool) else None
    )
    can_apply = True if apply_button else direct_apply
    application_status = "available" if can_apply is True else "unknown"
    requisition_id = _requisition_id(headers, description)
    canonical = clean_line(posting.get("url")) or None

    return {
        "status": "inspected",
        "posting": {
            "title": clean_line(posting.get("title")) or None,
            "description": description or None,
            "requisition_id": requisition_id,
            "posting_id": job_id,
            "locations": extract_locations(posting, headers),
            "can_apply": can_apply,
            "posted": True,
            "application_status": application_status,
            "date_posted": clean_line(posting.get("datePosted")) or None,
            "valid_through": clean_line(posting.get("validThrough")) or None,
        },
        "schedule": extract_posting_schedule(lines),
        "requirements": extract_requirements(lines),
        "document_canonical_url": canonical,
        "structured": structured,
    }


def _base_result(job_url: str, inspected_at: datetime) -> dict[str, Any]:
    return {
        "provider": "icims",
        "status": "failed",
        "retrieval_confidence": "none",
        "error": None,
        "posting": None,
        "requirements": {key: empty_requirement_field() for key in REQUIREMENT_FIELDS},
        "provenance": {
            "provider": "icims",
            "interface": INTERFACE,
            "source_url": job_url,
            "endpoint_url": None,
            "inspected_at": iso(inspected_at),
        },
    }


def inspect_icims_url(
    job_url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    """Inspect an iCIMS URL without raising; failures stay structured."""

    inspected_at = now()
    result = _base_result(job_url, inspected_at)
    try:
        endpoint = derive_icims_endpoint(job_url)
    except UnsupportedIcimsUrl as exc:
        result["status"] = "unsupported_url"
        result["error"] = str(exc)
        return result

    result["provenance"].update(
        {
            "endpoint_url": endpoint["endpoint_url"],
            "canonical_job_url": endpoint["canonical_job_url"],
            "host": endpoint["host"],
            "job_id": endpoint["job_id"],
        }
    )
    client = session or requests.Session()
    try:
        response = client.get(
            endpoint["endpoint_url"],
            headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "Yartchives/1.0 (+public job inspection)"},
            timeout=timeout,
        )
        if response.status_code in {404, 410}:
            result["status"] = "unavailable"
            result["error"] = f"iCIMS returned HTTP {response.status_code}"
            return result
        response.raise_for_status()
        normalized = normalize_html(response.text, job_id=endpoint["job_id"])
    except requests.RequestException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    except ValueError as exc:
        result["status"] = "changed_response"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    if normalized["status"] == "unavailable":
        result["status"] = "unavailable"
        result["error"] = "iCIMS says the job is no longer open"
        return result

    document_canonical = normalized.pop("document_canonical_url", None)
    structured = normalized.pop("structured", False)
    result.update(normalized)
    if document_canonical:
        result["provenance"]["document_canonical_url"] = document_canonical
    result["provenance"]["interface"] = INTERFACE if structured else "icims_public_html"
    result["retrieval_confidence"] = (
        "high" if structured and result["posting"].get("description") else "medium"
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
    preserved["inspection"] = inspect_icims_url(
        str(listing.get("url") or ""), session=session, timeout=timeout, now=now
    )
    return preserved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Authoritative public iCIMS job URL")
    args = parser.parse_args()
    result = inspect_icims_url(args.url)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "inspected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
