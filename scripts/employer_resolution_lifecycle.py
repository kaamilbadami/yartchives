#!/usr/bin/env python3
"""Persist a bounded, TTL-aware employer careers-resolution lifecycle."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from careers_resolver import MAX_PAGES, has_provider_tenant_identity, resolve_employer  # noqa: E402
from employer_resolution_queue import queue_entry  # noqa: E402
from employer_universe import validate_universe  # noqa: E402

DEFAULT_TTL_DAYS = 7
DEFAULT_EMPLOYER_BUDGET = 20
DEFAULT_REQUEST_BUDGET = 120


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _valid_existing_resolution(employer: dict[str, Any]) -> bool:
    url = str(employer.get("careers_url") or "").strip()
    if not url:
        return False
    provider = employer.get("provider") or {}
    if provider.get("status") == "resolved" and not has_provider_tenant_identity(url, provider.get("family")):
        return False
    return True


def _fresh_success(employer: dict[str, Any], now: datetime, ttl_days: int) -> bool:
    resolution = employer.get("careers_resolution") or {}
    if resolution.get("status") != "resolved" or not _valid_existing_resolution(employer):
        return False
    resolved_at = _parse_timestamp(resolution.get("resolved_at"))
    return bool(resolved_at and now - resolved_at < timedelta(days=ttl_days))


def _attempt_status(resolution: dict[str, Any]) -> str:
    evidence = resolution.get("evidence") or []
    statuses = [
        item.get("status")
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("status"), int)
    ]
    if any(status == 429 or status >= 500 for status in statuses):
        return "transient"
    if any(status in {401, 403} for status in statuses):
        return "blocked"
    if any(isinstance(item, dict) and item.get("error") for item in evidence):
        return "transient"
    return "unresolved"


def _request_count(resolution: dict[str, Any]) -> int:
    return sum(
        1
        for item in resolution.get("evidence") or []
        if isinstance(item, dict) and item.get("type") == "http"
    )


def _candidate_rows(universe: dict[str, Any], now: datetime, ttl_days: int) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for employer in universe.get("employers", []):
        if _fresh_success(employer, now, ttl_days):
            continue
        entry = queue_entry(employer)
        if entry["resolution_readiness"] != "ready":
            continue
        rows.append((employer, entry))
    rows.sort(key=lambda pair: (
        pair[1]["resolution_priority"],
        -pair[1]["authoritative_evidence_count"],
        -pair[1]["evidence_count"],
        pair[1]["id"],
    ))
    return rows


def run_lifecycle(
    universe: dict[str, Any],
    *,
    now: datetime | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    employer_budget: int = DEFAULT_EMPLOYER_BUDGET,
    request_budget: int = DEFAULT_REQUEST_BUDGET,
    resolver: Callable[..., dict[str, Any]] = resolve_employer,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_universe(universe)
    if ttl_days <= 0 or employer_budget <= 0 or request_budget <= 0:
        raise ValueError("ttl_days, employer_budget, and request_budget must be positive")

    now = now or _utc_now()
    output = json.loads(json.dumps(universe))
    by_id = {employer["id"]: employer for employer in output.get("employers", [])}
    candidates = _candidate_rows(output, now, ttl_days)
    attempts = 0
    requests_used = 0
    outcomes: Counter[str] = Counter()

    for _, entry in candidates:
        if attempts >= employer_budget or requests_used >= request_budget:
            break
        employer = by_id[entry["id"]]
        if not _valid_existing_resolution(employer):
            employer.pop("careers_url", None)
            employer.pop("careers_platform", None)
            employer.pop("provider", None)
        max_pages = min(MAX_PAGES, request_budget - requests_used)
        resolution = resolver(entry, max_pages=max_pages)
        requests_used += _request_count(resolution)
        attempts += 1
        attempted_at = _timestamp(now)

        if resolution.get("status") == "resolved":
            employer["careers_url"] = resolution.get("url")
            employer["careers_platform"] = resolution.get("platform")
            employer["provider"] = resolution.get("provider")
            employer["careers_resolution"] = {
                "status": "resolved",
                "attempt_status": "resolved",
                "resolved_at": attempted_at,
                "last_attempt_at": attempted_at,
                "evidence": resolution.get("evidence") or [],
            }
            outcomes["resolved"] += 1
            continue

        previous = employer.get("careers_resolution") or {}
        status = _attempt_status(resolution)
        lifecycle = {
            "status": "resolved" if employer.get("careers_url") else status,
            "attempt_status": status,
            "last_attempt_at": attempted_at,
            "evidence": resolution.get("evidence") or [],
        }
        if previous.get("resolved_at"):
            lifecycle["resolved_at"] = previous["resolved_at"]
        employer["careers_resolution"] = lifecycle
        outcomes[status] += 1

    providers = Counter(
        str(employer.get("careers_platform") or "unknown")
        for employer in output.get("employers", [])
        if employer.get("careers_url")
    )
    summary = {
        "candidate_employers": len(candidates),
        "attempted_employers": attempts,
        "requests_used": requests_used,
        "employer_budget": employer_budget,
        "request_budget": request_budget,
        "outcomes": dict(sorted(outcomes.items())),
        "resolved_provider_families": dict(sorted(providers.items())),
    }
    validate_universe(output)
    return output, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("universe", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    parser.add_argument("--employer-budget", type=int, default=DEFAULT_EMPLOYER_BUDGET)
    parser.add_argument("--request-budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    args = parser.parse_args()

    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    try:
        updated, summary = run_lifecycle(
            universe,
            ttl_days=args.ttl_days,
            employer_budget=args.employer_budget,
            request_budget=args.request_budget,
        )
    except ValueError as exc:
        parser.error(str(exc))
    rendered = json.dumps(updated, indent=2, ensure_ascii=False) + "\n"
    target = args.output or args.universe
    target.write_text(rendered, encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
