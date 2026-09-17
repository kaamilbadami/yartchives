#!/usr/bin/env python3
"""Retrieve and conservatively normalize one public Oracle HCM Candidate Experience posting."""

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
INTERFACE = "oracle_hcm_candidate_experience_api"
ORACLE_HOST = re.compile(r"^[a-z0-9-]+\.fa\.[a-z0-9-]+\.oraclecloud\.com$", re.I)
JOB_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SITE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class UnsupportedOracleHcmUrl(ValueError):
    """Raised when a URL cannot identify a public Oracle HCM Candidate Experience job."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def derive_oracle_hcm_endpoint(job_url: str) -> dict[str, str]:
    parsed = urlparse(html.unescape(job_url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not ORACLE_HOST.fullmatch(host):
        raise UnsupportedOracleHcmUrl("expected an HTTPS Oracle Cloud HCM host")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    lower = [part.lower() for part in parts]
    try:
        ce_index = lower.index("candidateexperience")
    except ValueError as exc:
        raise UnsupportedOracleHcmUrl("expected an Oracle CandidateExperience job URL") from exc

    tail = parts[ce_index + 1 :]
    if len(tail) < 5 or tail[1].lower() != "sites" or tail[3].lower() != "job":
        raise UnsupportedOracleHcmUrl(
            "Oracle CandidateExperience URL must include /<lang>/sites/<site>/job/<job-id>"
        )
    language = tail[0].strip().lower()
    site_number = tail[2].strip()
    job_id = tail[4].strip()
    if not language or not SITE_ID.fullmatch(site_number) or not JOB_ID.fullmatch(job_id):
        raise UnsupportedOracleHcmUrl("Oracle CandidateExperience URL contains invalid site or job identity")

    encoded_site = quote(site_number, safe="-._~")
    encoded_job = quote(job_id, safe="-._~")
    canonical_path = f"/hcmUI/CandidateExperience/{quote(language, safe='-._~')}/sites/{encoded_site}/job/{encoded_job}"
    canonical_url = urlunparse(("https", host, canonical_path, "", "", ""))
    endpoint_url = urlunparse(
        (
            "https",
            host,
            "/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails",
            "",
            "",
            "",
        )
    )
    return {
        "host": host,
        "language": language,
        "site_number": site_number,
        "job_id": job_id,
        "canonical_job_url": canonical_url,
        "endpoint_url": endpoint_url,
    }


def _append_unique(values: list[str], value: Any) -> None:
    cleaned = posting_requirements.clean_line(str(value) if value is not None else "")
    if cleaned and cleaned.casefold() not in {item.casefold() for item in values}:
        values.append(cleaned)


def _locations(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    _append_unique(values, item.get("PrimaryLocation"))
    for key in ("secondaryLocations", "otherWorkLocations"):
        children = item.get(key)
        if not isinstance(children, list):
            continue
        for child in children:
            if isinstance(child, dict):
                _append_unique(
                    values,
                    child.get("Name")
                    or child.get("Location")
                    or child.get("PrimaryLocation")
                    or child.get("Address"),
                )
            else:
                _append_unique(values, child)
    return values


def _clean(value: Any) -> str:
    return posting_requirements.clean_line(str(value) if value is not None else "")


def normalize_payload(payload: Any, *, expected_job_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Oracle HCM response was not a JSON object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("Oracle HCM response did not contain an items collection")
    if not items:
        raise LookupError("Oracle HCM posting is not currently published")
    item = items[0]
    if not isinstance(item, dict):
        raise ValueError("Oracle HCM response item was not a JSON object")

    identifiers = {
        str(item.get(key)).strip()
        for key in ("Id", "RequisitionNumber", "ExternalRequisitionNumber")
        if item.get(key) is not None
    }
    if identifiers and expected_job_id not in identifiers:
        raise ValueError("Oracle HCM response did not match the requested job ID")
    if not any(item.get(key) for key in ("Title", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")):
        raise ValueError("Oracle HCM response did not contain recognizable public job fields")

    sections: list[str] = []
    responsibilities = item.get("ExternalResponsibilitiesStr")
    qualifications = item.get("ExternalQualificationsStr")
    corporate = item.get("CorporateDescriptionStr")
    short_description = item.get("ShortDescriptionStr")
    if responsibilities:
        sections.extend(["Responsibilities", str(responsibilities)])
    if qualifications:
        sections.extend(["Qualifications", str(qualifications)])
    if corporate:
        sections.extend(["About", str(corporate)])
    if short_description and not sections:
        sections.append(str(short_description))

    description, lines = posting_requirements.normalize_description("\n".join(sections))
    locations = _locations(item)
    posting_id = _clean(item.get("Id")) or expected_job_id
    requisition_id = _clean(item.get("RequisitionId")) or None
    return {
        "posting": {
            "title": _clean(item.get("Title")) or None,
            "description": description or None,
            "requisition_id": requisition_id,
            "posting_id": posting_id,
            "locations": {
                "status": "authoritative" if locations else "unknown",
                "values": locations,
            },
            "can_apply": True,
            "posted": True,
            "application_status": "available",
            "first_published": _clean(item.get("ExternalPostedStartDate")) or None,
            "updated_at": _clean(item.get("LastUpdateDate")) or None,
            "application_deadline": _clean(item.get("ExternalPostedEndDate")) or None,
        },
        "requirements": posting_requirements.extract_requirements(lines),
    }


def _base_result(job_url: str, inspected_at: datetime) -> dict[str, Any]:
    return {
        "provider": "oracle_hcm",
        "status": "failed",
        "retrieval_confidence": "none",
        "error": None,
        "posting": None,
        "requirements": {
            key: posting_requirements.empty_requirement_field()
            for key in posting_requirements.REQUIREMENT_FIELDS
        },
        "provenance": {
            "provider": "oracle_hcm",
            "interface": INTERFACE,
            "source_url": job_url,
            "endpoint_url": None,
            "inspected_at": iso(inspected_at),
        },
    }


def inspect_oracle_hcm_url(
    job_url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    inspected_at = now()
    result = _base_result(job_url, inspected_at)
    try:
        endpoint = derive_oracle_hcm_endpoint(job_url)
    except UnsupportedOracleHcmUrl as exc:
        result["status"] = "unsupported_url"
        result["error"] = str(exc)
        return result

    result["provenance"].update(
        {
            "endpoint_url": endpoint["endpoint_url"],
            "canonical_job_url": endpoint["canonical_job_url"],
            "site_number": endpoint["site_number"],
            "job_id": endpoint["job_id"],
        }
    )
    client = session or requests.Session()
    try:
        response = client.get(
            endpoint["endpoint_url"],
            params={
                "expand": "all",
                "onlyData": "true",
                "finder": f'ById;Id="{endpoint["job_id"]}",siteNumber={endpoint["site_number"]}',
            },
            headers={
                "Accept": "application/json",
                "User-Agent": "Yartchives/1.0 (+public job inspection)",
                "Ora-Irc-Language": endpoint["language"],
            },
            timeout=timeout,
        )
        if response.status_code in {404, 410}:
            result["status"] = "unavailable"
            result["error"] = f"Oracle HCM returned HTTP {response.status_code}"
            return result
        response.raise_for_status()
        try:
            normalized = normalize_payload(response.json(), expected_job_id=endpoint["job_id"])
        except LookupError as exc:
            result["status"] = "unavailable"
            result["error"] = str(exc)
            return result
    except requests.RequestException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    except (ValueError, json.JSONDecodeError) as exc:
        result["status"] = "changed_response"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result.update(normalized)
    result["status"] = "inspected"
    result["retrieval_confidence"] = "high" if normalized["posting"].get("description") else "medium"
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
    preserved["inspection"] = inspect_oracle_hcm_url(
        str(listing.get("url") or ""), session=session, timeout=timeout, now=now
    )
    return preserved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Authoritative public Oracle HCM Candidate Experience job URL")
    args = parser.parse_args()
    result = inspect_oracle_hcm_url(args.url)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "inspected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
