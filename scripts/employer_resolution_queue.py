#!/usr/bin/env python3
"""Build a deterministic careers-resolution queue from employer-universe evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from employer_universe import validate_universe  # noqa: E402
from provider_fingerprint import fingerprint_provider  # noqa: E402

SCHEMA_VERSION = 1
READINESS_ORDER = {"ready": 0, "needs_tenant_identity": 1, "no_domain_hint": 2}


def _url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text.lstrip("/")
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return text


def _hint_identity_status(value: str) -> str:
    """Classify whether a hint identifies an employer rather than a shared ATS."""
    url = _url(value)
    if not url:
        return "invalid"
    parsed = urlparse(url)
    family = fingerprint_provider(url)["family"]
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query.casefold())

    if family == "greenhouse":
        return "tenant" if parts and parts[0].casefold() not in {"jobs", "careers"} else "shared_provider"
    if family in {"ashby", "lever", "smartrecruiters"}:
        return "tenant" if parts else "shared_provider"
    if family == "successfactors":
        return "tenant" if query.get("company") else "shared_provider"
    # Workday, iCIMS, Oracle, Eightfold, Avature, and Phenom commonly encode
    # tenant identity in the hostname. Unknown hosts are employer-domain hints.
    return "tenant"


def _metadata_rows(employer: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    metadata = employer.get("seed_metadata") or {}
    if not isinstance(metadata, dict):
        return []
    return [
        (str(key), value)
        for key, value in sorted(metadata.items())
        if isinstance(value, dict)
    ]


def queue_entry(employer: dict[str, Any]) -> dict[str, Any]:
    domains: set[str] = set()
    states: set[str] = set()
    evidence_count = 0
    authoritative_count = 0
    evidence_sources: list[dict[str, Any]] = []

    for seed_key, metadata in _metadata_rows(employer):
        seed_domains = sorted({
            str(value).strip()
            for value in metadata.get("domain_hints", [])
            if str(value).strip()
        })
        seed_states = sorted({
            str(value).strip().upper()
            for value in metadata.get("states", [])
            if str(value).strip()
        })
        count = max(0, int(metadata.get("evidence_count") or 0))
        authoritative = max(0, int(metadata.get("authoritative_evidence_count") or 0))
        domains.update(seed_domains)
        states.update(seed_states)
        evidence_count += count
        authoritative_count += authoritative
        evidence_sources.append({
            "seed_key": seed_key,
            "evidence_count": count,
            "authoritative_evidence_count": authoritative,
            "domain_hints": seed_domains,
            "states": seed_states,
        })

    valid_domains = sorted(domain for domain in domains if _url(domain))
    statuses = {_hint_identity_status(domain) for domain in valid_domains}
    if "tenant" in statuses:
        readiness = "ready"
    elif "shared_provider" in statuses:
        readiness = "needs_tenant_identity"
    else:
        readiness = "no_domain_hint"

    return {
        "id": employer["id"],
        "name": employer["name"],
        "aliases": sorted(employer.get("aliases") or [], key=str.casefold),
        "seed_sets": sorted(employer.get("seed_sets") or []),
        "domain_hints": valid_domains,
        "states": sorted(states),
        "evidence_count": evidence_count,
        "authoritative_evidence_count": authoritative_count,
        "resolution_readiness": readiness,
        "evidence_sources": evidence_sources,
    }


def build_queue(
    universe: dict[str, Any],
    *,
    ready_only: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    validate_universe(universe)
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")

    entries = [
        queue_entry(employer)
        for employer in universe.get("employers", [])
        if not _url(employer.get("careers_url"))
    ]
    entries.sort(key=lambda row: (
        READINESS_ORDER[row["resolution_readiness"]],
        -row["authoritative_evidence_count"],
        -row["evidence_count"],
        row["id"],
    ))
    counts = {
        readiness: sum(row["resolution_readiness"] == readiness for row in entries)
        for readiness in READINESS_ORDER
    }
    selected = [row for row in entries if not ready_only or row["resolution_readiness"] == "ready"]
    if limit is not None:
        selected = selected[:limit]
    return {
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "unresolved_employers": len(entries),
            "selected_employers": len(selected),
            **counts,
        },
        "employers": selected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("universe", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ready-only", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    try:
        queue = build_queue(universe, ready_only=args.ready_only, limit=args.limit)
    except ValueError as exc:
        parser.error(str(exc))
    rendered = json.dumps(queue, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
