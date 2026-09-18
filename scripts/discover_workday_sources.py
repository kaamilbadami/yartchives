#!/usr/bin/env python3
"""Discover reusable US Workday sources from authoritative CS feed links.

The normalized feed often already contains one or more CS-relevant jobs for an
employer on a public Workday career site even when broad aggregators miss
sibling internships. This helper turns those authoritative URLs into bounded,
state-scoped direct-source configs without adding employers one by one.
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
DEFAULT_UNIVERSE = ROOT / "employer_universe.json"
SEARCH_TERMS = ["intern", "co-op", "student"]
LOCALE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _source_identity(source: dict[str, Any]) -> str:
    api_url = _clean(source.get("api_url")).rstrip("/").casefold()
    state = _clean(source.get("state")).upper()
    scope = _clean(source.get("scope")).casefold()
    if api_url and state:
        return f"{api_url}|state:{state}"
    if api_url and scope:
        return f"{api_url}|scope:{scope}"
    return ""


def _job_states(job: dict[str, Any]) -> list[str]:
    profiles = {str(value).lower() for value in (job.get("profiles") or []) if value}
    if "cs" not in profiles:
        return []
    return sorted({str(value).upper() for value in (job.get("states") or []) if value})


def _source_key(tenant: str, site: str, state: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{tenant}-{site}".casefold()).strip("-")
    return f"{state.casefold()}-auto-workday-{slug}"


def source_from_job(job: dict[str, Any], state: str) -> dict[str, Any] | None:
    """Backward-compatible state-scoped source constructor for targeted callers/tests."""
    state = state.upper()
    if state not in _job_states(job):
        return None
    source = source_from_job_national(job)
    if not source:
        return None
    source["key"] = _source_key(source["tenant"], source["site"], state)
    source["name"] = f"{source['company']} (auto-discovered Workday, {state})"
    source["state"] = state
    source.pop("scope", None)
    source.pop("tenant", None)
    source.pop("site", None)
    return source


def source_from_job_national(job: dict[str, Any]) -> dict[str, Any] | None:
    """Turn one evidenced CS Workday posting into one reusable US career-site source."""
    if not _job_states(job):
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
    slug = re.sub(r"[^a-z0-9]+", "-", f"{tenant}-{site}".casefold()).strip("-")
    return {
        "key": f"us-feed-workday-{slug}",
        "name": f"{company} (auto-discovered Workday, US)",
        "company": company,
        "kind": "workday",
        "api_url": api_url,
        "public_base": public_base,
        "homepage": public_base,
        "scope": "us",
        "profile_hint": ["cs"],
        "minimum_expected": 0,
        "search_terms": list(SEARCH_TERMS),
        "auto_discovered": True,
        "tenant": tenant,
        "site": site,
    }


def source_from_employer(employer: dict[str, Any]) -> dict[str, Any] | None:
    provider = employer.get("provider") or {}
    resolution = employer.get("careers_resolution") or {}
    if provider.get("family") != "workday" or resolution.get("status") != "resolved":
        return None

    url = _clean(employer.get("careers_url"))
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not re.fullmatch(r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com", host, flags=re.I):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if parts and LOCALE.fullmatch(parts[0]):
        parts = parts[1:]
    if not parts:
        return None
    site = parts[0]
    tenant = host.split(".", 1)[0]
    api_url = f"https://{host}/wday/cxs/{quote(tenant, safe='-._~')}/{quote(site, safe='-._~')}/jobs"
    public_base = f"https://{host}/en-US/{quote(site, safe='-._~')}"
    company = _clean(employer.get("name")) or tenant
    slug = re.sub(r"[^a-z0-9]+", "-", f"{tenant}-{site}".casefold()).strip("-")
    return {
        "key": f"us-auto-workday-{slug}",
        "name": f"{company} (resolved Workday, US)",
        "company": company,
        "kind": "workday",
        "api_url": api_url,
        "public_base": public_base,
        "homepage": public_base,
        "scope": "us",
        "profile_hint": ["cs"],
        "minimum_expected": 0,
        "search_terms": list(SEARCH_TERMS),
        "auto_discovered": True,
        "universe_discovered": True,
    }


def discover_sources(
    feed: dict[str, Any],
    configured: list[dict[str, Any]],
    universe: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return configured plus universe-resolved and feed-evidenced Workday sources."""
    out = [dict(source) for source in configured if isinstance(source, dict)]
    seen = {_source_identity(source) for source in out if _source_identity(source)}

    for employer in sorted((universe or {}).get("employers", []), key=lambda row: _clean(row.get("id"))):
        if not isinstance(employer, dict):
            continue
        source = source_from_employer(employer)
        if not source:
            continue
        identity = _source_identity(source)
        if not identity or identity in seen:
            continue
        out.append(source)
        seen.add(identity)

    national_apis = {
        _clean(source.get("api_url")).rstrip("/").casefold()
        for source in out
        if _clean(source.get("scope")).casefold() == "us"
    }

    jobs = [job for job in (feed.get("jobs") or []) if isinstance(job, dict)]
    jobs.sort(key=lambda job: (_clean(job.get("company")).casefold(), _clean(job.get("url")).casefold()))
    for job in jobs:
        source = source_from_job_national(job)
        if not source:
            continue
        api_key = _clean(source.get("api_url")).rstrip("/").casefold()
        if api_key in national_apis:
            continue
        identity = _source_identity(source)
        if not identity or identity in seen:
            continue
        source.pop("tenant", None)
        source.pop("site", None)
        out.append(source)
        seen.add(identity)
        national_apis.add(api_key)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--configured", type=Path, default=DEFAULT_CONFIGURED)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    feed = json.loads(args.feed.read_text(encoding="utf-8"))
    configured = json.loads(args.configured.read_text(encoding="utf-8"))
    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    sources = discover_sources(feed, configured, universe)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    auto_count = sum(bool(source.get("auto_discovered")) for source in sources)
    national = sum(source.get("scope") == "us" for source in sources)
    targeted = sum(bool(source.get("state")) for source in sources)
    print(
        f"Prepared {len(sources)} direct Workday source(s): "
        f"{national} national source(s), {targeted} targeted state source(s), "
        f"{auto_count} auto-discovered source(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
