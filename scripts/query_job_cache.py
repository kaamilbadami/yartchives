#!/usr/bin/env python3
"""Query one job across the feed and authoritative-inspection cache.

This utility is intentionally local-first: it reads the repository JSON files on
 disk, finds only records whose stable identifiers or job metadata match a query,
and prints a compact diagnostic payload. That avoids shipping multi-megabyte cache
artifacts through external API/connector response limits just to inspect one job.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_CACHE = ROOT / "data" / "workday-inspections.json"

LISTING_SEARCH_FIELDS = (
    "id",
    "company",
    "title",
    "url",
    "resolved_from_url",
)
CACHE_POSTING_SEARCH_FIELDS = (
    "title",
    "requisition_id",
    "posting_id",
)
CACHE_PROVENANCE_SEARCH_FIELDS = (
    "source_url",
    "canonical_job_url",
    "endpoint_url",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: Any) -> str:
    return str(value or "").strip().casefold()


def contains_query(values: Iterable[Any], query: str) -> bool:
    needle = normalize(query)
    return bool(needle) and any(needle in normalize(value) for value in values)


def listing_matches(job: dict[str, Any], query: str) -> bool:
    values = [job.get(field) for field in LISTING_SEARCH_FIELDS]
    for field in ("source_keys", "source_names", "source_urls"):
        raw = job.get(field) or []
        if isinstance(raw, list):
            values.extend(raw)
        else:
            values.append(raw)
    return contains_query(values, query)


def cache_entry_matches(cache_key: str, entry: dict[str, Any], query: str) -> bool:
    values: list[Any] = [cache_key, entry.get("provider")]
    inspection = entry.get("inspection") if isinstance(entry.get("inspection"), dict) else {}
    posting = inspection.get("posting") if isinstance(inspection.get("posting"), dict) else {}
    provenance = inspection.get("provenance") if isinstance(inspection.get("provenance"), dict) else {}
    values.extend(posting.get(field) for field in CACHE_POSTING_SEARCH_FIELDS)
    values.extend(provenance.get(field) for field in CACHE_PROVENANCE_SEARCH_FIELDS)
    return contains_query(values, query)


def compact_listing(job: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "id",
        "company",
        "title",
        "location",
        "url",
        "resolved_from_url",
        "link_kind",
        "link_origin",
        "link_status",
        "direct_employer",
        "posted_at",
        "term",
        "education_level",
        "source_keys",
        "source_names",
        "source_urls",
    )
    return {field: copy.deepcopy(job[field]) for field in keep if field in job}


def compact_cache_entry(cache_key: str, entry: dict[str, Any]) -> dict[str, Any]:
    inspection = entry.get("inspection") if isinstance(entry.get("inspection"), dict) else {}
    posting = inspection.get("posting") if isinstance(inspection.get("posting"), dict) else {}
    compact_posting = {
        field: copy.deepcopy(posting[field])
        for field in (
            "title",
            "requisition_id",
            "posting_id",
            "locations",
            "can_apply",
            "posted",
            "application_status",
        )
        if field in posting
    }
    return {
        "cache_key": cache_key,
        "provider": entry.get("provider"),
        "last_attempted_at": entry.get("last_attempted_at"),
        "last_success_at": entry.get("last_success_at"),
        "last_error": entry.get("last_error"),
        "requirements_extractor_version": entry.get("requirements_extractor_version"),
        "inspection": {
            "status": inspection.get("status"),
            "retrieval_confidence": inspection.get("retrieval_confidence"),
            "error": inspection.get("error"),
            "posting": compact_posting,
            "requirements": copy.deepcopy(inspection.get("requirements")),
            "provenance": copy.deepcopy(inspection.get("provenance")),
        },
    }


def query_records(
    feed: Any,
    cache: Any,
    query: str,
    *,
    limit: int = 20,
    full: bool = False,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    jobs = feed if isinstance(feed, list) else feed.get("jobs", []) if isinstance(feed, dict) else []
    entries = cache.get("entries", {}) if isinstance(cache, dict) else {}

    listing_results: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict) or not listing_matches(job, query):
            continue
        listing_results.append(copy.deepcopy(job) if full else compact_listing(job))
        if len(listing_results) >= limit:
            break

    cache_results: list[dict[str, Any]] = []
    if isinstance(entries, dict):
        for cache_key, entry in entries.items():
            if not isinstance(entry, dict) or not cache_entry_matches(str(cache_key), entry, query):
                continue
            if full:
                cache_results.append({"cache_key": cache_key, "entry": copy.deepcopy(entry)})
            else:
                cache_results.append(compact_cache_entry(str(cache_key), entry))
            if len(cache_results) >= limit:
                break

    return {
        "query": query,
        "listings": listing_results,
        "cache_entries": cache_results,
        "counts": {
            "listings": len(listing_results),
            "cache_entries": len(cache_results),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Requisition, URL fragment, company, title, or stable listing id")
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--full", action="store_true", help="Print complete matching records, including descriptions")
    args = parser.parse_args()

    result = query_records(
        load_json(args.feed),
        load_json(args.cache),
        args.query,
        limit=args.limit,
        full=args.full,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["counts"]["listings"] or result["counts"]["cache_entries"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
