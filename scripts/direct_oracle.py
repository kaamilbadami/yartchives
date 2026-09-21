#!/usr/bin/env python3
"""Add US CS-relevant student roles from resolved Oracle Candidate Experience sites.

This is a provider-family gap filler. It only enumerates Oracle HCM career sites
whose employer-universe resolution already includes an explicit Candidate
Experience site identifier, so bare Oracle tenant hosts are never guessed.
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
from urllib.parse import quote, urlparse, urlunparse

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

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_UNIVERSE = ROOT / "employer_universe.json"
TIMEOUT = 25
PAGE_SIZE = 50
MAX_RESULTS_PER_SOURCE = 500
ORACLE_REST_VERSIONS = ("latest", "11.13.18.05")
ORACLE_REST_RESOURCES = ("recruitingCEJobRequisitions", "recruitingICEJobRequisitions")
ORACLE_SITE_PATH = re.compile(r"/(?:hcmUI/CandidateExperience/)?[a-z]{2}/sites/([^/?#]+)", re.I)
STRUCTURAL_SOURCE_STATUSES = {403, 404, 406, 410, 422}


class StructuralSourceError(RuntimeError):
    """An auto-discovered provider endpoint is structurally invalid or gone."""

    def __init__(self, message: str, status_codes: list[int] | None = None):
        super().__init__(message)
        self.status_codes = tuple(status_codes or [])


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any) -> str:
    return bf.clean_text(value).strip()


def _oracle_source(employer: dict[str, Any]) -> dict[str, Any] | None:
    provider = employer.get("provider") or {}
    if provider.get("family") != "oracle":
        return None
    resolution = employer.get("careers_resolution") or {}
    if resolution.get("status") != "resolved":
        return None

    careers_url = _clean(employer.get("careers_url"))
    if not careers_url:
        return None
    parsed = urlparse(careers_url)
    if not parsed.hostname:
        return None
    match = ORACLE_SITE_PATH.search(parsed.path)
    if not match:
        return None

    site_number = match.group(1)
    origin = urlunparse((parsed.scheme or "https", parsed.netloc, "", "", "", ""))
    homepage = urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    slug = re.sub(r"[^a-z0-9]+", "-", employer["id"].casefold()).strip("-")
    return {
        "key": f"auto-oracle-{slug}-{site_number.casefold()}",
        "name": f"{employer['name']} (resolved Oracle)",
        "company": employer["name"],
        "kind": "oracle",
        "site_number": site_number,
        "homepage": homepage,
        "api_url": f"{origin}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "api_urls": [
            f"{origin}/hcmRestApi/resources/{version}/{resource}"
            for resource in ORACLE_REST_RESOURCES
            for version in ORACLE_REST_VERSIONS
        ],
        "profile_hint": ["cs"],
        "auto_discovered": True,
    }


def discover_sources(universe: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for employer in sorted(universe.get("employers", []), key=lambda row: str(row.get("id") or "")):
        if not isinstance(employer, dict):
            continue
        source = _oracle_source(employer)
        if not source:
            continue
        key = (urlparse(source["api_url"]).netloc.casefold(), source["site_number"].casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(source)
    return out


def _locations(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    primary = _clean(item.get("PrimaryLocation"))
    if primary:
        values.append(primary)
    for key in ("otherWorkLocations", "secondaryLocations", "workLocation"):
        rows = item.get(key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = _clean(row.get("LocationName")) or ", ".join(
                part for part in (_clean(row.get("TownOrCity")), _clean(row.get("Region2")), _clean(row.get("Country"))) if part
            )
            if value:
                values.append(value)
    return list(dict.fromkeys(values))


def _looks_us(item: dict[str, Any], locations: list[str]) -> bool:
    country = _clean(item.get("PrimaryLocationCountry")).upper()
    if country == "US":
        return True
    text = " | ".join(locations)
    if bf.extract_states(text):
        return True
    return bool(re.search(r"\b(?:United States|USA|U\.S\.)\b", text, flags=re.I))


def _posted_at(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def public_job_url(source: dict[str, Any], job_id: str) -> str:
    return f"{source['homepage'].rstrip('/')}/job/{quote(job_id, safe='-._~')}"


def job_from_item(source: dict[str, Any], item: dict[str, Any], reference: datetime) -> dict[str, Any] | None:
    title = _clean(item.get("Title"))
    if not is_student_opportunity(title) or not is_cs_relevant_title(title):
        return None

    job_id = _clean(item.get("Id"))
    if not job_id:
        return None
    locations = _locations(item)
    if not _looks_us(item, locations):
        return None
    location = " | ".join(locations) or "Location not listed"

    posted_raw = _clean(item.get("PostedDate"))
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
        location=location,
        url=public_job_url(source, job_id),
        posted_raw=posted_raw,
        source=direct_source,
        section="Resolved Oracle Candidate Experience role",
        function_primary="Computer Science / Technology",
        posted_at=_posted_at(posted_raw),
    )
    if not job:
        return None
    job["direct_employer"] = True
    job["oracle_site_number"] = source["site_number"]
    job["oracle_job_id"] = job_id
    return job


def _oracle_request_variants(source: dict[str, Any], offset: int) -> list[tuple[str, str]]:
    urls = [str(value) for value in (source.get("api_urls") or []) if value]
    if source.get("api_url") and source["api_url"] not in urls:
        urls.insert(0, str(source["api_url"]))
    if not urls:
        urls = [str(source["api_url"])]

    base = f"findReqs;siteNumber={source['site_number']},limit={PAGE_SIZE},offset={offset},keyword=intern"
    finders = [f"{base},workLocationCountryCode=US", base]
    return [(url, finder) for url in urls for finder in finders]


def _fetch_oracle_page(client: requests.Session, source: dict[str, Any], offset: int) -> list[dict[str, Any]]:
    errors: list[str] = []
    structural_statuses: list[int] = []

    for api_url, finder in _oracle_request_variants(source, offset):
        try:
            response = client.get(
                api_url,
                params={"onlyData": "true", "finder": finder, "expand": "requisitionList"},
                headers={"Accept": "application/json", "User-Agent": bf.USER_AGENT},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            content_type = str(getattr(response, "headers", {}).get("Content-Type", "") or "").casefold()
            if content_type and "json" not in content_type:
                raise ValueError(f"Oracle endpoint returned non-JSON content type: {content_type}")
            payload = response.json()
            containers = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(containers, list):
                raise ValueError("Oracle requisition response did not contain an items list")
            return containers
        except ValueError as exc:
            structural_statuses.append(406)
            errors.append(f"{api_url}: ValueError: {exc}")
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in STRUCTURAL_SOURCE_STATUSES:
                structural_statuses.append(status)
            errors.append(f"{api_url}: {type(exc).__name__}: {exc}")
        except TypeError as exc:
            errors.append(f"{api_url}: TypeError: {exc}")

    if len(structural_statuses) == len(errors) and len(errors) > 0:
        raise StructuralSourceError(
            "all Oracle requisition variants failed with structural HTTP status: " + " | ".join(errors[-4:]),
            structural_statuses,
        )

    raise RuntimeError("all Oracle requisition variants failed: " + " | ".join(errors[-4:]))


def fetch_source(client: requests.Session, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    offset = 0
    while offset < MAX_RESULTS_PER_SOURCE:
        containers = _fetch_oracle_page(client, source, offset)

        page: list[dict[str, Any]] = []
        total = 0
        for container in containers:
            if not isinstance(container, dict):
                continue
            total = max(total, int(container.get("TotalJobsCount") or 0))
            rows = container.get("requisitionList") or []
            if isinstance(rows, list):
                page.extend(row for row in rows if isinstance(row, dict))

        if not page:
            break
        for item in page:
            job_id = _clean(item.get("Id"))
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            job = job_from_item(source, item, reference)
            if job:
                out.append(job)

        offset += len(page)
        if total and offset >= total:
            break
        if len(page) < PAGE_SIZE:
            break
    return out


def enrich(
    doc: dict[str, Any],
    old_doc: dict[str, Any],
    universe: dict[str, Any],
    client: requests.Session,
    reference: datetime,
) -> dict[str, Any]:
    jobs = doc.setdefault("jobs", [])
    health = doc.setdefault("sources", {})
    old_jobs = old_doc.get("jobs", []) if isinstance(old_doc, dict) else []
    old_jobs_by_id = {j.get("id"): j for j in old_jobs if isinstance(j, dict) and j.get("id")}

    for source in discover_sources(universe):
        try:
            direct_jobs = fetch_source(client, source, reference)
            for job in direct_jobs:
                upsert_direct_job(jobs, job, old_jobs_by_id, reference)
            health[source["key"]] = {
                "status": "healthy",
                "count": len(direct_jobs),
                "name": source["name"],
                "direct": True,
                "auto_discovered": True,
            }
            print(f"{source['name']}: {len(direct_jobs)} direct US CS-relevant listing(s)")
        except StructuralSourceError as exc:
            health[source["key"]] = {
                "status": "quarantined",
                "count": 0,
                "name": source["name"],
                "direct": True,
                "auto_discovered": True,
                "error": f"StructuralSourceError: {exc}",
            }
            print(f"{source['name']}: QUARANTINED (structural source error): {exc}", file=sys.stderr)
        except Exception as exc:
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
            print(f"{source['name']}: FAILED: {exc}", file=sys.stderr)
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--old-feed", type=Path)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    args = parser.parse_args()

    doc = json.loads(args.feed.read_text(encoding="utf-8"))
    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    old_doc: dict[str, Any] = {}
    if args.old_feed and args.old_feed.exists():
        try:
            old_doc = json.loads(args.old_feed.read_text(encoding="utf-8"))
        except Exception:
            old_doc = {}
    if not old_doc:
        old_doc = copy.deepcopy(doc)

    reference = now_utc()
    enrich(doc, old_doc, universe, retry_session(), reference)
    if stable_projection(doc) == stable_projection(old_doc):
        print("Resolved Oracle coverage unchanged.")
        return 0
    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged resolved Oracle coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
