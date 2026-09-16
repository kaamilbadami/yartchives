#!/usr/bin/env python3
"""Incrementally inspect authoritative ATS listings into a static cache artifact.

The filename is retained for backwards compatibility, while entries and request
budgets are provider-aware for Workday, iCIMS, and Greenhouse.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from greenhouse_inspector import derive_greenhouse_endpoint, inspect_greenhouse_url  # noqa: E402
from icims_inspector import derive_icims_endpoint, inspect_icims_url  # noqa: E402
from posting_requirements import extract_requirements  # noqa: E402
from workday_inspector import derive_cxs_endpoint, inspect_workday_url  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_CACHE = ROOT / "data" / "workday-inspections.json"
DEFAULT_MAX_REQUESTS = 25
DEFAULT_MAX_ICIMS_REQUESTS = 10
DEFAULT_MAX_GREENHOUSE_REQUESTS = 10
DEFAULT_TTL_DAYS = 7
FAILED_RETRY_HOURS = 6
CACHE_VERSION = 4
REUSABLE_STATUSES = {"inspected", "unavailable"}
PROVIDERS = ("workday", "icims", "greenhouse")


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


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def upcoming_summer_term(reference: datetime) -> str:
    """Return the upcoming Summer term without using any private user profile."""
    year = reference.year + (1 if reference.month >= 6 else 0)
    return f"Summer {year}"


def empty_cache() -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "updated_at": None,
        "priority_term": None,
        "entries": {},
        "listing_index": {},
        "queue": {},
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
    queue = raw.get("queue")
    return {
        "version": CACHE_VERSION,
        "updated_at": raw.get("updated_at"),
        "priority_term": raw.get("priority_term"),
        "entries": entries if isinstance(entries, dict) else {},
        "listing_index": listing_index if isinstance(listing_index, dict) else {},
        "queue": queue if isinstance(queue, dict) else {},
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
        "provider": "workday",
        "canonical_url": derived["canonical_job_url"],
        "endpoint_url": derived["endpoint_url"],
        "supported": "true",
    }


def _unsupported_icims_identity(url: str) -> dict[str, str] | None:
    parsed = urlparse(html.unescape(url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not host.endswith(".icims.com"):
        return None
    canonical = urlunparse(("https", host, parsed.path.rstrip("/") or "/", "", "", ""))
    return {
        "provider": "icims",
        "canonical_url": canonical,
        "endpoint_url": canonical,
        "supported": "false",
    }


def icims_identity(job: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(job, dict) or job.get("link_kind") in {"listing", "source"}:
        return None
    url = str(job.get("url") or "").strip()
    if not url:
        return None
    try:
        derived = derive_icims_endpoint(url)
    except ValueError:
        return _unsupported_icims_identity(url)
    return {
        "provider": "icims",
        "canonical_url": derived["canonical_job_url"],
        "endpoint_url": derived["endpoint_url"],
        "supported": "true",
    }


def _unsupported_greenhouse_identity(url: str) -> dict[str, str] | None:
    parsed = urlparse(html.unescape(url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or host not in {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
    }:
        return None
    canonical = urlunparse(("https", "job-boards.greenhouse.io", parsed.path.rstrip("/") or "/", "", "", ""))
    return {
        "provider": "greenhouse",
        "canonical_url": canonical,
        "endpoint_url": canonical,
        "supported": "false",
    }


def greenhouse_identity(job: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(job, dict) or job.get("link_kind") in {"listing", "source"}:
        return None
    url = str(job.get("url") or "").strip()
    if not url:
        return None
    try:
        derived = derive_greenhouse_endpoint(url)
    except ValueError:
        return _unsupported_greenhouse_identity(url)
    return {
        "provider": "greenhouse",
        "canonical_url": derived["canonical_job_url"],
        "endpoint_url": derived["endpoint_url"],
        "supported": "true",
    }


def posting_identity(job: dict[str, Any]) -> dict[str, str] | None:
    return workday_identity(job) or icims_identity(job) or greenhouse_identity(job)


def provider_for_url(url: str) -> str | None:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if re.fullmatch(r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com", host, flags=re.I):
        return "workday"
    if host.endswith(".icims.com"):
        return "icims"
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        return "greenhouse"
    return None


def supported_identity(url: str) -> bool:
    provider = provider_for_url(url)
    try:
        if provider == "workday":
            derive_cxs_endpoint(url)
        elif provider == "icims":
            derive_icims_endpoint(url)
        elif provider == "greenhouse":
            derive_greenhouse_endpoint(url)
        else:
            return False
    except ValueError:
        return False
    return True


def inspect_posting_url(url: str) -> dict[str, Any]:
    provider = provider_for_url(url)
    if provider == "workday":
        return inspect_workday_url(url)
    if provider == "icims":
        return inspect_icims_url(url)
    if provider == "greenhouse":
        return inspect_greenhouse_url(url)
    return {
        "status": "unsupported_url",
        "retrieval_confidence": "none",
        "error": "No supported ATS provider matched the URL",
        "posting": None,
        "requirements": {},
        "provenance": {"source_url": url},
    }


def renormalize_cached_requirements(entry: dict[str, Any]) -> dict[str, Any]:
    """Re-run deterministic extraction from a cached full description without a request."""

    out = copy.deepcopy(entry)
    inspection = out.get("inspection")
    if not isinstance(inspection, dict) or inspection.get("status") != "inspected":
        return out
    posting = inspection.get("posting")
    description = posting.get("description") if isinstance(posting, dict) else None
    if not isinstance(description, str) or not description.strip():
        return out
    inspection["requirements"] = extract_requirements(description.splitlines())
    return out


def build_listing_index(jobs: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    listing_index: dict[str, str] = {}
    by_url: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        identity = posting_identity(job)
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


def age_days(job: dict[str, Any], reference: datetime) -> float | None:
    value = job.get("posted_at")
    if not value:
        return None
    try:
        posted = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
    return max(0.0, (reference - posted).total_seconds() / 86400)


def public_priority(job: dict[str, Any], reference: datetime) -> tuple[int, list[str]]:
    """
    Score generic public metadata for inspection ordering only.

    Keep these weights close to the public pieces of Apply Next instead of letting one
    metadata field dominate the inspection queue. Unknown term/education values retain
    substantial priority because authoritative inspection is most useful when metadata
    leaves an otherwise-promising internship unresolved.
    """
    score = 0
    reasons: list[str] = []

    priority_term = upcoming_summer_term(reference)
    term = str(job.get("term") or "").strip()
    if normalize(term) == normalize(priority_term):
        score += 7
        reasons.append(priority_term)
    elif term:
        score -= 20
        reasons.append(f"other term: {term}")
    else:
        score += 6
        reasons.append("term unknown; inspection can resolve it")

    opportunity = normalize(job.get("opportunity_type"))
    title = normalize(job.get("title"))
    if opportunity in {"internship", "co-op"}:
        score += 7
        reasons.append("internship/co-op")
    elif re.search(r"\b(intern|internship|co-?op)\b", title):
        score += 6
        reasons.append("internship/co-op title")

    education = normalize(job.get("education_level"))
    if education == "graduate-only":
        score -= 20
        reasons.append("graduate-only")
    elif education in {"undergrad", "undergraduate", "undergrad-friendly"}:
        score += 6
        reasons.append("undergrad-friendly")
    else:
        score += 5
        reasons.append("education not restrictive; inspection can clarify")

    profiles = sorted({normalize(value) for value in job.get("profiles", []) if normalize(value)})
    if profiles:
        score += 8
        reasons.append(f"classified career area: {', '.join(profiles[:3])}")

    age = age_days(job, reference)
    if age is not None:
        if age <= 2:
            score += 15
            reasons.append("posted within 2 days")
        elif age <= 7:
            score += 12
            reasons.append("posted within 7 days")
        elif age <= 14:
            score += 9
            reasons.append("posted within 14 days")
        elif age <= 30:
            score += 5
            reasons.append("posted within 30 days")
        elif age <= 60:
            score += 2
            reasons.append("posted within 60 days")

    return score, reasons


def inspection_priority(jobs: list[dict[str, Any]], reference: datetime) -> tuple[int, list[str]]:
    if not jobs:
        return 0, []
    scored = [(*public_priority(job, reference), job) for job in jobs]
    score, reasons, _ = max(scored, key=lambda item: item[0])
    return score, reasons


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


def retry_in_cooldown(entry: dict[str, Any] | None, now: datetime) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("last_success_at"):
        return False
    if not entry.get("last_error"):
        return False
    attempted = parse_time(entry.get("last_attempted_at"))
    if not attempted:
        return False
    return now - attempted < timedelta(hours=FAILED_RETRY_HOURS)


def candidate_urls(
    by_url: dict[str, list[dict[str, Any]]],
    entries: dict[str, Any],
    now: datetime,
    ttl_days: int,
    provider: str | None = None,
) -> list[str]:
    pending: list[tuple[int, int, float, str]] = []
    stale: list[tuple[int, datetime, float, str]] = []

    for canonical, jobs in by_url.items():
        if provider and provider_for_url(canonical) != provider:
            continue
        if not supported_identity(canonical):
            continue
        entry = entries.get(canonical)
        if reusable(entry, now, ttl_days):
            continue
        if retry_in_cooldown(entry, now):
            continue

        priority, _ = inspection_priority(jobs, now)
        posted = latest_posted_at(jobs)
        last_success = parse_time(entry.get("last_success_at")) if isinstance(entry, dict) else None

        if not last_success:
            retry_penalty = 1 if isinstance(entry, dict) and entry.get("last_error") else 0
            pending.append((-priority, retry_penalty, -posted, canonical))
            continue

        stale.append((-priority, last_success, -posted, canonical))

    pending.sort()
    stale.sort()
    return [canonical for _, _, _, canonical in pending] + [canonical for _, _, _, canonical in stale]


def build_queue_metadata(
    by_url: dict[str, list[dict[str, Any]]],
    entries: dict[str, Any],
    now: datetime,
    ttl_days: int,
) -> dict[str, dict[str, Any]]:
    ranks: dict[str, int] = {}
    for provider in PROVIDERS:
        candidates = candidate_urls(by_url, entries, now, ttl_days, provider)
        ranks.update({canonical: index + 1 for index, canonical in enumerate(candidates)})
    queue: dict[str, dict[str, Any]] = {}

    for canonical, jobs in by_url.items():
        entry = entries.get(canonical)
        priority, reasons = inspection_priority(jobs, now)

        if reusable(entry, now, ttl_days):
            state = "cached"
            rank = None
        elif retry_in_cooldown(entry, now):
            state = "retry_cooldown"
            rank = None
        else:
            state = "queued"
            rank = ranks.get(canonical)

        item: dict[str, Any] = {
            "state": state,
            "priority_score": priority,
            "reasons": reasons,
        }
        if not supported_identity(canonical):
            item["state"] = "unsupported_url"
            rank = None
        if rank is not None:
            item["rank"] = rank
        queue[canonical] = item

    return dict(sorted(queue.items()))


def materialize_queue_entries(
    entries: dict[str, Any],
    queue: dict[str, dict[str, Any]],
) -> None:
    """
    Ensure pending ATS postings carry lightweight inspection-status metadata.

    This lets the static frontend explain why a job is still metadata-only without
    exposing private profile data or making browser-side ATS requests.
    """
    for canonical, queue_info in queue.items():
        entry = entries.get(canonical)
        inspection = entry.get("inspection") if isinstance(entry, dict) else None
        provider = provider_for_url(canonical)

        if isinstance(inspection, dict) and inspection.get("status") in REUSABLE_STATUSES:
            entry = copy.deepcopy(entry)
            entry.setdefault("provider", provider)
            entries[canonical] = entry
            continue

        if isinstance(inspection, dict):
            inspection = copy.deepcopy(inspection)
            provenance = inspection.get("provenance")
            if provider == "workday" and not (
                isinstance(provenance, dict) and provenance.get("provider")
            ):
                inspection.pop("provider", None)
            inspection["queue"] = copy.deepcopy(queue_info)
            entry = copy.deepcopy(entry)
            entry.setdefault("provider", provider)
            entry["inspection"] = inspection
            entries[canonical] = entry
            continue

        entries[canonical] = {
            "provider": provider,
            "inspection": {
                "provider": provider,
                "status": "unsupported_url" if queue_info.get("state") == "unsupported_url" else "queued",
                "retrieval_confidence": "none",
                "error": (
                    f"{provider or 'ATS'} URL shape is not recognized by the public posting inspector"
                    if queue_info.get("state") == "unsupported_url"
                    else None
                ),
                "posting": None,
                "requirements": {},
                "queue": copy.deepcopy(queue_info),
                "provenance": {
                    "source_url": canonical,
                    "provider": provider,
                    "interface": {
                        "workday": "workday_cxs_json",
                        "icims": "icims_jobposting_jsonld",
                        "greenhouse": "greenhouse_job_board_api",
                    }.get(provider),
                },
            },
            "last_attempted_at": None,
            "last_success_at": None,
            "last_error": None,
        }


def refresh_cache(
    feed: dict[str, Any],
    cache: dict[str, Any],
    *,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    max_workday_requests: int | None = None,
    max_icims_requests: int = DEFAULT_MAX_ICIMS_REQUESTS,
    max_greenhouse_requests: int = DEFAULT_MAX_GREENHOUSE_REQUESTS,
    ttl_days: int = DEFAULT_TTL_DAYS,
    now: Callable[[], datetime] = utc_now,
    inspector: Callable[[str], dict[str, Any]] = inspect_posting_url,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an updated cache without mutating the feed or input cache."""

    reference = now()
    jobs = feed.get("jobs") if isinstance(feed, dict) else []
    if not isinstance(jobs, list):
        jobs = []

    out = copy.deepcopy(cache) if isinstance(cache, dict) else empty_cache()
    out["version"] = CACHE_VERSION
    out["priority_term"] = upcoming_summer_term(reference)
    if not isinstance(out.get("entries"), dict):
        out["entries"] = {}
    listing_index, by_url = build_listing_index(jobs)
    out["listing_index"] = listing_index

    entries = {key: value for key, value in out["entries"].items() if key in by_url}
    entries = {
        key: renormalize_cached_requirements(value)
        if provider_for_url(key) in PROVIDERS
        else value
        for key, value in entries.items()
    }
    out["entries"] = entries
    candidates = candidate_urls(by_url, entries, reference, ttl_days)
    provider_caps = {
        "workday": max(0, int(max_requests if max_workday_requests is None else max_workday_requests)),
        "icims": max(0, int(max_icims_requests)),
        "greenhouse": max(0, int(max_greenhouse_requests)),
    }
    selected: list[str] = []
    for provider in PROVIDERS:
        provider_candidates = candidate_urls(by_url, entries, reference, ttl_days, provider)
        selected.extend(provider_candidates[: provider_caps[provider]])
    requested = 0
    succeeded = 0
    preserved = 0
    requested_by_provider = {provider: 0 for provider in PROVIDERS}
    succeeded_by_provider = {provider: 0 for provider in PROVIDERS}

    for canonical in selected:
        provider = provider_for_url(canonical)
        requested += 1
        if provider in requested_by_provider:
            requested_by_provider[provider] += 1
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
        result.setdefault("provider", provider)
        if isinstance(result.get("provenance"), dict):
            result["provenance"].setdefault("provider", provider)

        status = result.get("status")
        attempted_at = result.get("provenance", {}).get("inspected_at") or iso(reference)
        if status in REUSABLE_STATUSES:
            entries[canonical] = {
                "provider": provider,
                "inspection": result,
                "last_attempted_at": attempted_at,
                "last_success_at": attempted_at,
                "last_error": None,
            }
            succeeded += 1
            if provider in succeeded_by_provider:
                succeeded_by_provider[provider] += 1
            continue

        if old_entry and isinstance(old_entry.get("inspection"), dict) and old_entry["inspection"].get("status") in REUSABLE_STATUSES:
            old_entry["last_attempted_at"] = attempted_at
            old_entry["last_error"] = result.get("error") or f"Inspection status: {status or 'failed'}"
            old_entry.setdefault("provider", provider)
            entries[canonical] = old_entry
            preserved += 1
        else:
            entries[canonical] = {
                "provider": provider,
                "inspection": result,
                "last_attempted_at": attempted_at,
                "last_success_at": None,
                "last_error": result.get("error") or f"Inspection status: {status or 'failed'}",
            }

    queue = build_queue_metadata(by_url, entries, reference, ttl_days)
    materialize_queue_entries(entries, queue)
    out["entries"] = dict(sorted(entries.items()))
    out["queue"] = queue
    stats = {
        "workday_listings": sum(1 for canonical in listing_index.values() if provider_for_url(canonical) == "workday"),
        "workday_postings": sum(1 for canonical in by_url if provider_for_url(canonical) == "workday"),
        "icims_listings": sum(1 for canonical in listing_index.values() if provider_for_url(canonical) == "icims"),
        "icims_postings": sum(1 for canonical in by_url if provider_for_url(canonical) == "icims"),
        "greenhouse_listings": sum(1 for canonical in listing_index.values() if provider_for_url(canonical) == "greenhouse"),
        "greenhouse_postings": sum(1 for canonical in by_url if provider_for_url(canonical) == "greenhouse"),
        "priority_term": out["priority_term"],
        "eligible_for_refresh": len(candidates),
        "requested": requested,
        "succeeded": succeeded,
        "preserved_last_good": preserved,
        "provider_requests": requested_by_provider,
        "provider_successes": succeeded_by_provider,
        "provider_caps": provider_caps,
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
    parser.add_argument("--max-workday-requests", type=int)
    parser.add_argument("--max-icims-requests", type=int, default=DEFAULT_MAX_ICIMS_REQUESTS)
    parser.add_argument("--max-greenhouse-requests", type=int, default=DEFAULT_MAX_GREENHOUSE_REQUESTS)
    parser.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    args = parser.parse_args()

    feed = load_json(args.feed, {"jobs": []})
    original = load_cache(args.cache)
    reference = utc_now()
    updated, stats = refresh_cache(
        feed,
        original,
        max_requests=args.max_requests,
        max_workday_requests=args.max_workday_requests,
        max_icims_requests=args.max_icims_requests,
        max_greenhouse_requests=args.max_greenhouse_requests,
        ttl_days=args.ttl_days,
        now=lambda: reference,
    )
    changed = write_if_changed(args.cache, original, updated, reference)
    print(json.dumps({**stats, "cache_changed": changed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
