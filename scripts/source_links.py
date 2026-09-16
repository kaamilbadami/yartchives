#!/usr/bin/env python3
"""Recover direct links for records that otherwise fall back to GitHub sources.

Some upstream repos contain a real Apply URL even when the generic merge cannot
match it back to the deduplicated record. This pass re-reads the configured
markdown sources, indexes direct links within each source, and uses conservative
source+title/location/company matching. A source repo URL is provenance only; it
is never promoted as Apply.
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
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import repair_links as links  # noqa: E402

TIMEOUT = 12
WORKERS = 18
USER_AGENT = "Yartchives/1.0 source-link-recovery (+https://github.com/kaamilbadami/yartchives)"
DEAD_VISIBLE_PHRASES = (
    "the page you are looking for doesn't exist",
    "the page you are looking for does not exist",
    "this job is no longer available",
    "this position is no longer available",
    "job is no longer available",
    "position has been filled",
)


def norm(value: str | None) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def unique_index(rows: list[dict[str, Any]], key_fn) -> dict[tuple[str, ...], str]:
    buckets: dict[tuple[str, ...], set[str]] = {}
    for row in rows:
        direct = row.get("url")
        if not links.is_direct_application_url(direct):
            continue
        key = key_fn(row)
        if not key or any(not part for part in key):
            continue
        buckets.setdefault(key, set()).add(str(direct))
    return {key: next(iter(values)) for key, values in buckets.items() if len(values) == 1}


def build_indexes(rows: list[dict[str, Any]]) -> tuple[dict, dict, dict]:
    by_source_company_title = unique_index(
        rows,
        lambda row: (
            str(row.get("source_key") or ""),
            compact(row.get("company")),
            norm(row.get("title")),
        ),
    )
    by_source_title_location = unique_index(
        rows,
        lambda row: (
            str(row.get("source_key") or ""),
            norm(row.get("title")),
            norm(row.get("location")),
        ),
    )
    by_source_title = unique_index(
        rows,
        lambda row: (
            str(row.get("source_key") or ""),
            norm(row.get("title")),
        ),
    )
    return by_source_company_title, by_source_title_location, by_source_title


def choose_direct(job: dict[str, Any], indexes: tuple[dict, dict, dict]) -> str | None:
    by_company_title, by_title_location, by_title = indexes
    title = norm(job.get("title"))
    company = compact(job.get("company"))
    location = norm(job.get("location"))
    source_keys = [str(key) for key in (job.get("source_keys") or [])]

    candidates: set[str] = set()
    for source in source_keys:
        value = by_company_title.get((source, company, title))
        if value:
            candidates.add(value)
        value = by_title_location.get((source, title, location))
        if value:
            candidates.add(value)
    if len(candidates) == 1:
        return next(iter(candidates))
    if len(candidates) > 1:
        return None

    # Title-only is only used when the URL is unique within that same upstream
    # source, which handles harmless company/location normalization differences.
    for source in source_keys:
        value = by_title.get((source, title))
        if value:
            candidates.add(value)
    return next(iter(candidates)) if len(candidates) == 1 else None


def visible_text_prefix(response: requests.Response, limit: int = 160_000) -> str:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=32_768):
        if not chunk:
            continue
        remaining = limit - size
        if remaining <= 0:
            break
        chunks.append(chunk[:remaining])
        size += min(len(chunk), remaining)
        if size >= limit:
            break
    encoding = response.encoding or "utf-8"
    raw = b"".join(chunks).decode(encoding, errors="replace")
    soup = BeautifulSoup(raw, "html.parser")
    for node in soup(["script", "style", "noscript", "template"]):
        node.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).lower()


def validate_source_candidate(value: str) -> tuple[str, str]:
    if not links.is_direct_application_url(value):
        return "dead", value
    try:
        response = requests.get(
            value,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        try:
            final = response.url or value
            if response.status_code in {404, 410}:
                return "dead", final
            if response.status_code in {401, 403, 429} or response.status_code >= 500:
                return "unknown", final
            if not (200 <= response.status_code < 400):
                return "unknown", final
            if not links.is_direct_application_url(final):
                return "dead", final
            if "html" in response.headers.get("content-type", "").lower():
                text = visible_text_prefix(response)
                if any(phrase in text for phrase in DEAD_VISIBLE_PHRASES):
                    return "dead", final
            return "ok", final
        finally:
            response.close()
    except requests.RequestException:
        return "unknown", value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/listings.json")
    args = parser.parse_args()

    path = Path(args.path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    parsed = links.fetch_source_direct_jobs()
    indexes = build_indexes(parsed)

    targets: list[tuple[dict[str, Any], str]] = []
    for job in doc.get("jobs", []):
        if not isinstance(job, dict) or job.get("link_kind") != "source":
            continue
        candidate = choose_direct(job, indexes)
        if candidate:
            targets.append((job, candidate))

    upgrades: list[tuple[dict[str, Any], str, str]] = []
    dead = 0
    unknown = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(validate_source_candidate, candidate): (job, candidate) for job, candidate in targets}
        for future in as_completed(futures):
            job, candidate = futures[future]
            try:
                status, final = future.result()
            except Exception:
                status, final = "unknown", candidate
            if status == "dead":
                dead += 1
                continue
            if status == "unknown":
                unknown += 1
            if links.is_direct_application_url(final):
                upgrades.append((job, final, status))

    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for job, direct, status in upgrades:
        job["url"] = direct
        job.pop("listing_url", None)
        job["link_kind"] = "direct"
        job["link_origin"] = "source-feed-recovered"
        job["link_status"] = status
        job["link_checked_at"] = checked_at
        job.pop("dead_url", None)

    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Source-only direct-link recovery: {len(upgrades)} upgraded from {len(targets)} candidate(s); "
        f"dead={dead}, unknown={unknown}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
