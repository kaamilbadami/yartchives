#!/usr/bin/env python3
"""Print compact feed diagnostics for coverage and link quality."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROFILES = ["cs", "tech-business", "finance-econ", "mechanical", "aero", "electrical", "policy", "health"]
INTERNSHIP_TYPES = {"internship", "co-op", "student"}


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
    for job in jobs:
        kind = job.get("link_kind") or "legacy"
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind != "direct":
            value = job.get("listing_url") or job.get("url") or ""
            host = urlparse(value).netloc.lower() if value else "no-link"
            hosts[host] = hosts.get(host, 0) + 1
    print("\nLink quality:", ", ".join(f"{k}={v}" for k, v in kinds.items()))
    print("Largest non-direct link buckets:")
    for host, count in sorted(hosts.items(), key=lambda item: item[1], reverse=True)[:10]:
        print(f"- {host}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
