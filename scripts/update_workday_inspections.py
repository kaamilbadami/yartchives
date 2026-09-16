#!/usr/bin/env python3
"""Incrementally inspect authoritative Workday listings into a static cache artifact."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from workday_inspector import derive_cxs_endpoint, inspect_workday_url  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_CACHE = ROOT / "data" / "workday-inspections.json"
DEFAULT_MAX_REQUESTS = 25
DEFAULT_TTL_DAYS = 7
CACHE_VERSION = 1
REUSABLE_STATUSES = {"inspected", "unavailable"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def empty_cache() -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "updated_at": None,
        "entries": {},
        "listing_index": {},
    }


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(fallback)


def load_cache(path: Path) -> dict[str, Any]:
    raw = load_json(path, empty_cache())
    if not isinstance(raw, dict):
        return empty_cache()
    entries = raw.get("entries")
    listing_index = raw.get("listing_index")
    return {
        "version": CACHE_VERSION,
        "updated_at": raw.get("updated_at"),
        "entries": entries if isinstance(entries, dict) else {},
        "listing_index": listing_index if isinstance(listing_index, dict) else {},
    }


def workday_identity(job: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(job, dict):
        return None
    if job.get("link_kind") in {"listing", "source"}:
        return None
    url = str(job.get("url") or "").strip()
    if not url:
        return None
    try:
        derived = derive_cxs_endpoint(url)
    except ValueError:
        return None
    return {
        "canonical_url": derived["canonical_job_url"],
        "endpoint_url": derived["endpoint_url"],
    }


def build_listing_index(jobs: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    listing_index: dict[str, str] = {}
    by_url: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        identity = workday_identity(job)
        if not identity:
            continue
        canonical = identity["canonical_url"]
        if job.get("id"):
            listing_index[str(job["id"])] = canonical
        by_url.setdefault(canonical, []).append(job)
    return dict(sorted(listing_index.items())), by_url


def latest_posted_at(jobs: list[dict[str, Any]]) -> float:
    stamps: list[float] = []
    for job in jobs:
        value = job.get("posted_at")
        if not value:
            continue
        try:
            stamps.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
        except ValueError:
            continue
    return max(stamps, default=0.0)


def reusable(entry: dict[str, Any] | None, now: datetime, ttl_days: int) -> bool:
    if not isinstance(entry, dict):
        return False
    inspection = entry.get("inspection")
    if not isinstance(inspection, dict) or inspection.get("status") not in REUSABLE_STATUSES:
        return False
    success_at = parse_time(entry.get("last_success_at"))
    if not success_at:
        return False
    return now - success_at < timedelta(days=ttl_days)


def candidate_urls(
    by_url: dict[str, list[dict[str, Any]]],
    entries: dict[str, Any],
    now: datetime,
    ttl_days: int,
) -> list[str]:
    unseen: list[tuple[float, str]] = []
    stale: list[tuple[datetime, float, str]] = []

    for canonical, jobs in by_url.items():
        entry = entries.get(canonical)
        if reusable(entry, now, ttl_days):
            continue
        posted = latest_posted_at(jobs)
        if not isinstance(entry, dict) or not entry.get("inspection"):
            unseen.append((-posted, canonical))
            continue
        last_success = parse_time(entry.get("last_success_at")) or datetime.min.replace(tzinfo=timezone.utc)
        stale.append((last_success, -posted, canonical))

    unseen.sort()
    stale.sort()
    return [canonical for _, canonical in unseen] + [canonical for _, _, canonical in stale]


def refresh_cache(
    feed: dict[str, Any],
    cache: dict[str, Any],
    *,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    ttl_days: int = DEFAULT_TTL_DAYS,
    now: Callable[[], datetime] = utc_now,
    inspector: Callable[[str], dict[str, Any]] = inspect_workday_url,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Return an updated cache without mutating the feed or input cache."""

    reference = now()
    jobs = feed.get("jobs") if isinstance(feed, dict) else []
    if not isinstance(jobs, list):
        jobs = []

    out = copy.deepcopy(cache) if isinstance(cache, dict) else empty_cache()
    out["version"] = CACHE_VERSION
    if not isinstance(out.get("entries"), dict):
        out["entries"] = {}
    listing_index, by_url = build_listing_index(jobs)
    out["listing_index"] = listing_index

    entries = {key: value for key, value in out["entries"].items() if key in by_url}
    out["entries"] = entries
    candidates = candidate_urls(by_url, entries, reference, ttl_days)
    requested = 0
    succeeded = 0
    preserved = 0

    for canonical in candidates[: max(0, int(max_requests))]:
        requested += 1
        old_entry = copy.deepcopy(entries.get(canonical)) if isinstance(entries.get(canonical), dict) else None
        result = inspector(canonical)
        if not isinstance(result, dict):
            result = {
                "status": "failed",
                "retrieval_confidence": "none",
                "error": "Inspector returned a non-object result",
                "posting": None,
                "requirements": {},
                "provenance": {"source_url": canonical, "inspected_at": iso(reference)},
            }

        status = result.get("status")
        attempted_at = result.get("provenance", {}).get("inspected_at") or iso(reference)
        if status in REUSABLE_STATUSES:
            entries[canonical] = {
                "inspection": result,
                "last_attempted_at": attempted_at,
                "last_success_at": attempted_at,
                "last_error": None,
            }
            succeeded += 1
            continue

        if old_entry and isinstance(old_entry.get("inspection"), dict) and old_entry["inspection"].get("status") in REUSABLE_STATUSES:
            old_entry["last_attempted_at"] = attempted_at
            old_entry["last_error"] = result.get("error") or f"Inspection status: {status or 'failed'}"
            entries[canonical] = old_entry
            preserved += 1
        else:
            entries[canonical] = {
                "inspection": result,
                "last_attempted_at": attempted_at,
                "last_success_at": None,
                "last_error": result.get("error") or f"Inspection status: {status or 'failed'}",
            }

    out["entries"] = dict(sorted(entries.items()))
    stats = {
        "workday_listings": len(listing_index),
        "workday_postings": len(by_url),
        "eligible_for_refresh": len(candidates),
        "requested": requested,
        "succeeded": succeeded,
        "preserved_last_good": preserved,
    }
    return out, stats


def semantic_payload(cache: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(cache)
    payload.pop("updated_at", None)
    return payload


def write_if_changed(path: Path, original: dict[str, Any], updated: dict[str, Any], now: datetime) -> bool:
    if semantic_payload(original) == semantic_payload(updated):
        return False
    updated = copy.deepcopy(updated)
    updated["updated_at"] = iso(now)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    parser.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    args = parser.parse_args()

    feed = load_json(args.feed, {"jobs": []})
    original = load_cache(args.cache)
    reference = utc_now()
    updated, stats = refresh_cache(
        feed,
        original,
        max_requests=args.max_requests,
        ttl_days=args.ttl_days,
        now=lambda: reference,
    )
    changed = write_if_changed(args.cache, original, updated, reference)
    print(json.dumps({**stats, "cache_changed": changed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
