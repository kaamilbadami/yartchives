#!/usr/bin/env python3
"""Discover reusable Connecticut Workday sources from authoritative feed links.

The normalized feed often already contains one or more jobs for an employer on a
public Workday career site even when broad aggregators miss sibling internships.
This helper turns those existing authoritative URLs into direct-source configs so
the normal Workday gap-filling pass can query the whole career site without
adding employers one by one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from workday_inspector import UnsupportedWorkdayUrl, derive_cxs_endpoint  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_CONFIGURED = ROOT / "direct_sources.json"
DEFAULT_STATE = "CT"
SEARCH_TERMS = ["intern", "co-op", "student"]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _source_identity(source: dict[str, Any]) -> str:
    return _clean(source.get("api_url")).rstrip("/").casefold()


def _job_in_scope(job: dict[str, Any], state: str) -> bool:
    states = {str(value).upper() for value in (job.get("states") or []) if value}
    profiles = {str(value).lower() for value in (job.get("profiles") or []) if value}
    return state.upper() in states and "cs" in profiles


def _source_key(tenant: str, site: str, state: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{tenant}-{site}".casefold()).strip("-")
    return f"{state.casefold()}-auto-workday-{slug}"


def source_from_job(job: dict[str, Any], state: str = DEFAULT_STATE) -> dict[str, Any] | None:
    if not _job_in_scope(job, state):
        return None
    url = _clean(job.get("url"))
    try:
        endpoint = derive_cxs_endpoint(url)
    except UnsupportedWorkdayUrl:
        return None

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return None

    tenant = endpoint["tenant"]
    site = endpoint["site"]
    api_url = f"https://{host}/wday/cxs/{quote(tenant, safe='-._~')}/{quote(site, safe='-._~')}/jobs"
    public_base = f"https://{host}/en-US/{quote(site, safe='-._~')}"
    company = _clean(job.get("company")) or tenant
    return {
        "key": _source_key(tenant, site, state),
        "name": f"{company} (auto-discovered Workday)",
        "company": company,
        "kind": "workday",
        "api_url": api_url,
        "public_base": public_base,
        "homepage": public_base,
        "state": state.upper(),
        "profile_hint": ["cs"],
        "minimum_expected": 0,
        "search_terms": list(SEARCH_TERMS),
        "auto_discovered": True,
    }


def discover_sources(
    feed: dict[str, Any],
    configured: list[dict[str, Any]],
    state: str = DEFAULT_STATE,
) -> list[dict[str, Any]]:
    """Return configured sources plus deterministic Workday sites evidenced in-feed."""
    out = [dict(source) for source in configured if isinstance(source, dict)]
    seen = {_source_identity(source) for source in out if _source_identity(source)}

    jobs = [job for job in (feed.get("jobs") or []) if isinstance(job, dict)]
    jobs.sort(key=lambda job: (_clean(job.get("company")).casefold(), _clean(job.get("url")).casefold()))
    for job in jobs:
        source = source_from_job(job, state)
        if not source:
            continue
        identity = _source_identity(source)
        if not identity or identity in seen:
            continue
        out.append(source)
        seen.add(identity)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--configured", type=Path, default=DEFAULT_CONFIGURED)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state", default=DEFAULT_STATE)
    args = parser.parse_args()

    feed = json.loads(args.feed.read_text(encoding="utf-8"))
    configured = json.loads(args.configured.read_text(encoding="utf-8"))
    sources = discover_sources(feed, configured, args.state)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    auto_count = sum(bool(source.get("auto_discovered")) for source in sources)
    print(f"Prepared {len(sources)} direct Workday source(s), including {auto_count} auto-discovered site(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
