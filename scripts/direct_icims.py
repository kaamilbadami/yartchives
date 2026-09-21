#!/usr/bin/env python3
"""Add US CS-relevant sibling jobs from iCIMS career sites already evidenced in-feed.

This is a provider-family gap-filler, not a broad iCIMS crawler. A site becomes
eligible only when the normalized feed already contains a CS listing with an
authoritative public iCIMS URL. We then search that same public career site for
student roles and merge matching US CS opportunities using the existing direct
source upsert semantics.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

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
    is_target_state,
    session as retry_session,
    stable_projection,
    upsert_direct_job,
)
from icims_inspector import UnsupportedIcimsUrl, derive_icims_endpoint, inspect_icims_url  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
TIMEOUT = 25
MAX_SEARCH_PAGES = 5
NETWORK_WORKERS = 12
JOB_LINK = re.compile(r"^/jobs/(\d+)(?:/[^?#]+)?/job/?$", re.I)
SITEMAP_LOC = re.compile(r"<loc>\s*(https?://[^<]+)\s*</loc>", re.I)
STRUCTURAL_SOURCE_STATUSES = {403, 404, 410}


class StructuralSourceError(RuntimeError):
    """An auto-discovered provider endpoint is structurally invalid or gone."""

    def __init__(self, message: str, status_codes: list[int] | None = None):
        super().__init__(message)
        self.status_codes = tuple(status_codes or [])


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _evidences_cs(job: dict[str, Any]) -> bool:
    return "cs" in {str(value).lower() for value in (job.get("profiles") or []) if value}


def source_from_job(job: dict[str, Any]) -> dict[str, Any] | None:
    if not _evidences_cs(job):
        return None
    if job.get("link_kind") not in {None, "direct"}:
        return None
    try:
        endpoint = derive_icims_endpoint(_clean(job.get("url")))
    except UnsupportedIcimsUrl:
        return None
    host = endpoint["host"]
    company = _clean(job.get("company")) or host.split(".", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", host.casefold()).strip("-")
    return {
        "key": f"auto-icims-{slug}",
        "name": f"{company} (auto-discovered iCIMS)",
        "company": company,
        "kind": "icims",
        "host": host,
        "homepage": f"https://{host}/jobs/intro",
        "search_url": f"https://{host}/jobs/search",
        "sitemap_url": f"https://{host}/sitemap.xml",
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
        if not source or source["host"] in seen:
            continue
        out.append(source)
        seen.add(source["host"])
    return out


def extract_job_links(raw_html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    links: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        parsed = urlparse(urljoin(base_url, href))
        if not JOB_LINK.fullmatch(parsed.path):
            continue
        canonical = urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
        try:
            info = derive_icims_endpoint(canonical)
        except UnsupportedIcimsUrl:
            continue
        links[info["job_id"]] = info["canonical_job_url"]
    return [links[key] for key in sorted(links, key=lambda value: int(value))]


def _slug_text(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) < 4 or parts[0].casefold() != "jobs":
        return ""
    return re.sub(r"[-_]+", " ", parts[2]).strip()


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


def extract_sitemap_job_links(raw_xml: str, source: dict[str, Any]) -> list[str]:
    links: dict[str, str] = {}
    for raw_url in SITEMAP_LOC.findall(raw_xml or ""):
        parsed = urlparse(raw_url.strip())
        if parsed.netloc.casefold() != source["host"].casefold():
            continue
        if not JOB_LINK.fullmatch(parsed.path):
            continue
        slug_text = _slug_text(raw_url)
        if not is_student_opportunity(slug_text) or not is_cs_relevant_title(slug_text):
            continue
        canonical = urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
        try:
            info = derive_icims_endpoint(canonical)
        except UnsupportedIcimsUrl:
            continue
        links[info["job_id"]] = info["canonical_job_url"]
    return [links[key] for key in sorted(links, key=lambda value: int(value))]


def sitemap_site(client: requests.Session, source: dict[str, Any]) -> list[str]:
    try:
        response = client.get(
            source["sitemap_url"],
            headers={"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1", "User-Agent": bf.USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return extract_sitemap_job_links(response.text, source)
    except requests.RequestException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in STRUCTURAL_SOURCE_STATUSES:
            raise StructuralSourceError(f"sitemap structural error {status}: {exc}", [status]) from exc
        raise


def search_site(client: requests.Session, source: dict[str, Any]) -> list[str]:
    seen: dict[str, str] = {}
    for page in range(MAX_SEARCH_PAGES):
        try:
            response = client.get(
                source["search_url"],
                params={"ss": "1", "searchKeyword": "intern", "pr": page},
                headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": bf.USER_AGENT},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in STRUCTURAL_SOURCE_STATUSES:
                raise StructuralSourceError(f"search structural error {status}: {exc}", [status]) from exc
            raise
        links = extract_job_links(response.text, source["search_url"])
        before = len(seen)
        for link in links:
            job_id = derive_icims_endpoint(link)["job_id"]
            seen.setdefault(job_id, link)
        if not links or len(seen) == before:
            break
    if seen:
        return list(seen.values())

    # Some classic iCIMS portals render the search result list client-side, so a
    # normal HTTP response contains the search shell but zero posting anchors.
    # Their public sitemap still exposes canonical posting URLs. Prefilter by the
    # URL slug before inspecting details so this fallback stays request-bounded.
    return sitemap_site(client, source)


def job_from_inspection(source: dict[str, Any], url: str, inspection: dict[str, Any], reference: datetime) -> dict[str, Any] | None:
    if inspection.get("status") != "inspected":
        return None
    posting = inspection.get("posting") or {}
    title = _clean(posting.get("title"))
    locations = ((posting.get("locations") or {}).get("values") or [])
    location = " ".join(_clean(value) for value in locations if _clean(value)) or "Location not listed"
    if not is_student_opportunity(title) or not is_cs_relevant_title(title):
        return None
    if not _looks_us(location):
        return None

    posted_raw = _clean(posting.get("date_posted"))
    posted_at = bf.parse_relative_date(posted_raw, reference) if posted_raw else None
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
        url=url,
        posted_raw=posted_raw,
        source=direct_source,
        section="Auto-discovered iCIMS sibling role",
        function_primary="Computer Science / Technology",
        posted_at=posted_at,
    )
    if not job:
        return None
    job["direct_employer"] = True
    return job


def fetch_source(client: requests.Session, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for url in search_site(client, source):
        inspection = inspect_icims_url(url, session=client)
        job = job_from_inspection(source, url, inspection, reference)
        if job:
            out.append(job)
    return out


def fetch_sources_concurrently(
    client: requests.Session,
    sources: list[dict[str, Any]],
    reference: datetime,
) -> dict[str, tuple[list[dict[str, Any]] | None, Exception | None]]:
    """Fetch independent iCIMS boards in parallel."""
    if not sources:
        return {}

    results: dict[str, tuple[list[dict[str, Any]] | None, Exception | None]] = {}
    workers = min(NETWORK_WORKERS, len(sources))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_source, client, source, reference): source
            for source in sources
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                results[source["key"]] = (future.result(), None)
            except Exception as exc:
                results[source["key"]] = (None, exc)
    return results


def enrich(doc: dict[str, Any], old_doc: dict[str, Any], client: requests.Session, reference: datetime) -> dict[str, Any]:
    jobs = doc.setdefault("jobs", [])
    health = doc.setdefault("sources", {})
    old_jobs = old_doc.get("jobs", []) if isinstance(old_doc, dict) else []
    old_jobs_by_id = {j.get("id"): j for j in old_jobs if isinstance(j, dict) and j.get("id")}
    sources = discover_sources(doc)

    fetched = fetch_sources_concurrently(client, sources, reference)

    for source in sources:
        direct_jobs, exc = fetched.get(source["key"], (None, RuntimeError("missing fetch result")))
        if exc is None and direct_jobs is not None:
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
        else:
            if isinstance(exc, StructuralSourceError):
                health[source["key"]] = {
                    "status": "quarantined",
                    "count": 0,
                    "name": source["name"],
                    "direct": True,
                    "auto_discovered": True,
                    "error": f"StructuralSourceError: {exc}",
                }
                print(f"{source['name']}: QUARANTINED (structural source error): {exc}", file=sys.stderr)
            else:
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
        print("Auto-discovered iCIMS coverage unchanged.")
        return 0
    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged auto-discovered iCIMS coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
