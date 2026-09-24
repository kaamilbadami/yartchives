#!/usr/bin/env python3
"""Add US CS-relevant student roles from resolved SuccessFactors Candidate Experience sites.

This is a provider-family gap filler. It enumerates SuccessFactors career sites
whose employer-universe resolution already includes an explicit Candidate
Experience site identifier.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

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
    session as retry_session,
    stable_projection,
    upsert_direct_job,
)

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_UNIVERSE = ROOT / "employer_universe.json"
TIMEOUT = 25
MAX_RESULTS_PER_SOURCE = 500
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


def _successfactors_source(employer: dict[str, Any]) -> dict[str, Any] | None:
    provider = employer.get("provider") or {}
    if provider.get("family") != "successfactors":
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

    origin = urlunparse((parsed.scheme or "https", parsed.netloc, "", "", "", ""))
    homepage = urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    slug = re.sub(r"[^a-z0-9]+", "-", employer["id"].casefold()).strip("-")

    return {
        "key": f"auto-successfactors-{slug}",
        "name": f"{employer['name']} (resolved SuccessFactors)",
        "company": employer["name"],
        "employer_id": employer["id"],
        "kind": "successfactors",
        "homepage": homepage,
        "sitemap_url": f"{origin}/sitemap.xml",
        "profile_hint": ["cs"],
        "auto_discovered": True,
    }


def discover_sources(universe: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for employer in sorted(universe.get("employers", []), key=lambda row: str(row.get("id") or "")):
        if not isinstance(employer, dict):
            continue
        source = _successfactors_source(employer)
        if not source:
            continue
        key = source["key"]
        if key in seen:
            continue
        seen.add(key)
        out.append(source)
    return out


def _looks_us(locations: list[str]) -> bool:
    text = " | ".join(locations)
    if bf.extract_states(text):
        return True
    return bool(re.search(r"\b(?:United States|USA|U\.S\.|US)\b", text, flags=re.I))


def _posted_at(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        # e.g., "Mon Aug 31 00:00:00 UTC 2026"
        if " UTC " in text:
            parsed = datetime.strptime(text, "%a %b %d %H:%M:%S UTC %Y").replace(tzinfo=timezone.utc)
            return parsed
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None

def fetch_source(client: requests.Session, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        response = client.get(
            source["sitemap_url"],
            headers={"User-Agent": bf.USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in STRUCTURAL_SOURCE_STATUSES:
             raise StructuralSourceError(f"sitemap fetch failed with {status}", [status])
        raise RuntimeError(f"sitemap fetch failed: {exc}")

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
         raise StructuralSourceError(f"sitemap XML parse failed: {exc}", [406])

    job_urls = []

    # SuccessFactors uses RSS format sitemaps which have items with title and link.
    # On the off chance it's a standard sitemap without title, we fall back to scraping all urls.
    is_rss = bool(root.findall('.//item'))

    if is_rss:
        for item in root.findall('.//item'):
            title_elem = item.find('title')
            link_elem = item.find('link')
            if title_elem is not None and link_elem is not None:
                title = title_elem.text
                if not title:
                    continue
                if is_student_opportunity(title) and is_cs_relevant_title(title):
                    job_urls.append(link_elem.text.strip())
                    if len(job_urls) >= MAX_RESULTS_PER_SOURCE:
                        break
    else:
        # standard sitemap without title
        # For successfactors jobs2web we check URL patterns or just fetch all
        # This fallback is unlikely since SuccessFactors /sitemap.xml is universally RSS format as verified,
        # but to be safe:
        for loc in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
            url = loc.text
            if url and '/job/' in url:
                job_urls.append(url.strip())
                if len(job_urls) >= MAX_RESULTS_PER_SOURCE:
                    break

    for job_url in job_urls:
        try:
            r = client.get(job_url, headers={"User-Agent": bf.USER_AGENT}, timeout=TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            jp = soup.find(itemtype="http://schema.org/JobPosting")
            if not jp:
                continue

            title_elem = jp.find(itemprop="title")
            title = _clean(title_elem.text) if title_elem else ""
            if not title:
                continue

            # If we collected all urls blindly, verify it is CS student
            if not is_rss and not (is_student_opportunity(title) and is_cs_relevant_title(title)):
                continue

            loc_elem = jp.find(itemprop="jobLocation")
            locations = []
            if loc_elem:
                locality = loc_elem.find(itemprop="addressLocality")
                region = loc_elem.find(itemprop="addressRegion")
                country = loc_elem.find(itemprop="addressCountry")
                loc_parts = [
                    _clean(x.get('content') or x.text)
                    for x in (locality, region, country) if x
                ]
                loc_parts = [x for x in loc_parts if x]
                if loc_parts:
                    locations.append(", ".join(loc_parts))
                else:
                    locations.append(_clean(loc_elem.text))

            if not locations:
                 match = re.search(r'\(([^)]+)\)$', title)
                 if match:
                     locations.append(_clean(match.group(1)))

            if not _looks_us(locations):
                continue

            location = " | ".join(locations) or "Location not listed"

            date_elem = jp.find(itemprop="datePosted")
            posted_raw = ""
            if date_elem:
                 posted_raw = _clean(date_elem.get('content') or date_elem.text)

            job_id_match = re.search(r'-(\d+)(?:-[^/]+)?/\d+/?$', job_url)
            job_id = job_id_match.group(1) if job_id_match else job_url

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
                url=job_url,
                posted_raw=posted_raw,
                source=direct_source,
                section="Resolved SuccessFactors Candidate Experience role",
                function_primary="Computer Science / Technology",
                posted_at=_posted_at(posted_raw),
            )
            if not job:
                continue
            job["direct_employer"] = True
            job["employer_id"] = source["employer_id"]
            job["successfactors_job_id"] = job_id

            out.append(job)

        except requests.RequestException:
            pass

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
        print("Resolved SuccessFactors coverage unchanged.")
        return 0
    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged resolved SuccessFactors coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
