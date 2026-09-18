#!/usr/bin/env python3
"""Print compact feed diagnostics for coverage and link quality."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROFILES = ["cs", "tech-business", "finance-econ", "mechanical", "aero", "electrical", "policy", "health"]
INTERNSHIP_TYPES = {"internship", "co-op", "student"}
WORKDAY_HOST_RE = re.compile(r"^[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com$", re.I)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def age_days(job: dict, reference: datetime) -> float | None:
    posted = parse_time(job.get("posted_at"))
    if not posted:
        return None
    return max(0.0, (reference - posted).total_seconds() / 86400)


def default_eligible(job: dict) -> bool:
    return job.get("education_level") != "graduate-only" and job.get("opportunity_type") in INTERNSHIP_TYPES


def zapply_provider(value: str) -> str:
    parsed = urlparse(value or "")
    if parsed.netloc.lower() not in {"zapply.jobs", "www.zapply.jobs"}:
        return ""
    slug = parsed.path.rstrip("/").split("/")[-1].lower()
    match = re.match(r"([a-z0-9]+)-", slug)
    return match.group(1) if match else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/listings.json")
    args = parser.parse_args()

    doc = json.loads(Path(args.path).read_text(encoding="utf-8"))
    jobs = [j for j in doc.get("jobs", []) if isinstance(j, dict)]
    reference = parse_time(doc.get("generated_at")) or datetime.now(timezone.utc)
    eligible = [j for j in jobs if default_eligible(j)]

    print("=== Yartchives coverage audit (default student/type filters) ===")
    print(f"Reference: {reference.isoformat()}")
    print(f"Indexed: {len(jobs)} | undergrad-friendly internship/co-op/student: {len(eligible)}")
    print("profile | all locations | CT any age | CT past 7d")
    for profile in PROFILES:
        all_count = sum(profile in (j.get("profiles") or []) for j in eligible)
        ct = [j for j in eligible if profile in (j.get("profiles") or []) and "CT" in (j.get("states") or [])]
        ct7 = [j for j in ct if (d := age_days(j, reference)) is not None and d <= 7]
        print(f"{profile:13} | {all_count:5} | {len(ct):5} | {len(ct7):5}")

    cs_eligible = [j for j in eligible if "cs" in (j.get("profiles") or [])]
    source_contrib: Counter[str] = Counter()
    source_unique: Counter[str] = Counter()
    multi_source = 0
    for job in cs_eligible:
        keys = [str(key) for key in (job.get("source_keys") or []) if key]
        for key in set(keys):
            source_contrib[key] += 1
        if len(set(keys)) == 1:
            source_unique[keys[0]] += 1
        elif len(set(keys)) > 1:
            multi_source += 1

    print("\n=== Computer Science coverage overlap ===")
    print(f"Yartchives deduplicated CS union: {len(cs_eligible)}")
    print(f"Listings seen in 2+ upstream sources: {multi_source}")
    print("source key | contributes to union | unique to source")
    for source, count in source_contrib.most_common():
        print(f"{source:28} | {count:5} | {source_unique[source]:5}")

    target = [
        j for j in eligible
        if "cs" in (j.get("profiles") or [])
        and "CT" in (j.get("states") or [])
        and (d := age_days(j, reference)) is not None
        and d <= 7
    ]
    target.sort(key=lambda j: j.get("posted_at") or "", reverse=True)
    print(f"\nCT + Computer Science + past 7 days: {len(target)}")
    for job in target[:25]:
        host = urlparse(job.get("url") or job.get("listing_url") or "").netloc or "no-link"
        print(f"- {job.get('company')} — {job.get('title')} — {job.get('location')} — {job.get('posted_at')} — {job.get('link_kind', 'legacy')}:{host}")

    kinds = {"direct": 0, "listing": 0, "source": 0, "legacy": 0}
    hosts: dict[str, int] = {}
    unresolved_sources: Counter[str] = Counter()
    zapply_providers: Counter[str] = Counter()
    zapply_companies: Counter[str] = Counter()
    source_only_sources: Counter[str] = Counter()
    non_direct: list[dict] = []

    for job in jobs:
        kind = job.get("link_kind") or "legacy"
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "direct":
            continue
        non_direct.append(job)
        value = job.get("listing_url") or job.get("url") or ""
        host = urlparse(value).netloc.lower() if value else "no-link"
        hosts[host] = hosts.get(host, 0) + 1
        for source in job.get("source_keys") or ["unknown"]:
            unresolved_sources[str(source)] += 1
        if kind == "source":
            for source in job.get("source_keys") or ["unknown"]:
                source_only_sources[str(source)] += 1
        provider = zapply_provider(value)
        if provider:
            zapply_providers[provider] += 1
            zapply_companies[str(job.get("company") or "unknown")] += 1

    workday_direct = [
        j for j in jobs
        if j.get("link_kind") == "direct"
        and WORKDAY_HOST_RE.fullmatch((urlparse(str(j.get("url") or "")).hostname or "").lower())
    ]
    workday_contract_violations = [
        j for j in workday_direct
        if (
            not urlparse(str(j.get("url") or "")).path.rstrip("/").casefold().endswith("/apply")
            or j.get("link_status") != "ok"
            or not str(j.get("link_checked_at") or "").strip()
        )
    ]

    print("\nLink quality:", ", ".join(f"{k}={v}" for k, v in kinds.items()))
    print(
        "Workday direct contract: "
        f"direct={len(workday_direct)}, violations={len(workday_contract_violations)}"
    )
    for job in workday_contract_violations[:10]:
        print(
            "- CONTRACT VIOLATION: "
            f"{job.get('company')} — {job.get('title')} — "
            f"status={job.get('link_status')!r} — {job.get('url') or 'no-link'}"
        )
    print("Largest non-direct link buckets:")
    for host, count in sorted(hosts.items(), key=lambda item: item[1], reverse=True)[:10]:
        print(f"- {host}: {count}")

    print("Unresolved by source key:")
    for source, count in unresolved_sources.most_common(15):
        print(f"- {source}: {count}")

    print("Zapply unresolved provider prefixes:")
    for provider, count in zapply_providers.most_common(15):
        print(f"- {provider}: {count}")

    print("Zapply unresolved companies:")
    for company, count in zapply_companies.most_common(20):
        print(f"- {company}: {count}")

    print("Source-only by source key:")
    for source, count in source_only_sources.most_common(15):
        print(f"- {source}: {count}")

    print("Remaining non-direct sample:")
    for job in non_direct[:40]:
        value = job.get("listing_url") or job.get("url") or ""
        print(
            f"- [{job.get('link_kind')}] {job.get('company')} — {job.get('title')} — "
            f"{job.get('location')} — {value or 'no-link'} — sources={','.join(job.get('source_keys') or [])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
