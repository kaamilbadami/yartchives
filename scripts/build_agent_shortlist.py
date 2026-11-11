#!/usr/bin/env python3
"""Create a public, non-personalized shortlist from a validated Yartchives feed.

This is a discovery export, NOT a statement that each job is still open or
that any applicant meets its eligibility requirements.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from urllib.parse import urlsplit

MAX_FEED_AGE_HOURS = 6
DEFAULT_DAYS = 21
DEFAULT_LIMIT = 250
ALLOWED_PROFILES = {"cs", "tech-business", "finance-econ", "engineering"}
FIELDS = (
    "id", "company", "title", "location", "states", "url", "posting_url",
    "posted_at", "first_seen", "term", "opportunity_type", "education_level",
    "profiles", "function_primary", "direct_employer", "source_names",
    "source_keys", "link_kind", "link_status", "link_checked_at",
    "salary_min", "salary_max", "salary_period", "salary_currency",
    "remote_type",
)


def timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except ValueError:
        return None


def valid_http_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"https", "http"} and bool(parsed.hostname) and not parsed.username and not parsed.password


def suitable(job, now, days):
    if not isinstance(job, dict) or not job.get("id"):
        return False
    if not valid_http_url(job.get("posting_url") or job.get("url")):
        return False
    label = str(job.get("title") or "").lower()
    kind = str(job.get("opportunity_type") or "").lower()
    if kind not in {"internship", "co-op", "coop"} and not any(
        word in label for word in ("intern", "co-op", "coop")
    ):
        return False
    # Do not confuse graduating senior internships with senior-level employment.
    profiles = set(job.get("profiles") or [])
    if profiles and not (profiles & ALLOWED_PROFILES):
        return False
    posted = timestamp(job.get("posted_at")) or timestamp(job.get("first_seen"))
    if posted is None or posted > now + timedelta(days=1):
        return False
    return posted >= now - timedelta(days=days)


def relevant_inspection(job_id, cache):
    """Extract bounded, employer-derived requirements without posting descriptions."""
    if not isinstance(cache, dict):
        return None
    canonical = (cache.get("listing_index") or {}).get(str(job_id))
    entry = (cache.get("entries") or {}).get(canonical, {}) if canonical else {}
    inspection = entry.get("inspection") if isinstance(entry, dict) else None
    if not isinstance(inspection, dict):
        return None
    posting = inspection.get("posting") or {}
    requirements = inspection.get("requirements") or {}
    result = {"inspection_status": inspection.get("status")}
    for key in ("requisition_id", "application_status", "application_deadline"):
        if isinstance(posting, dict) and posting.get(key):
            result[key] = posting[key]
    if isinstance(requirements, dict):
        for category in ("graduation", "citizenship", "work_authorization", "education", "student_status", "major_fields", "skills"):
            field = requirements.get(category) or {}
            if not isinstance(field, dict):
                continue
            values = []
            for level in ("required", "preferred", "not_required"):
                for fact in (field.get(level) or [])[:2]:
                    if isinstance(fact, dict) and fact.get("statement"):
                        values.append({"level": level, "statement": str(fact["statement"])[:320]})
            if values:
                result.setdefault("requirements", {})[category] = values
    return result if len(result) > 1 or result.get("inspection_status") not in (None, "queued") else None


def build_export(feed, now=None, days=DEFAULT_DAYS, limit=DEFAULT_LIMIT, inspections=None):
    now = now or datetime.now(timezone.utc)
    generated = timestamp(feed.get("generated_at"))
    if generated is None:
        raise ValueError("feed has no valid generated_at")
    age = (now - generated).total_seconds() / 3600
    if age < -0.25 or age > MAX_FEED_AGE_HOURS:
        raise ValueError(f"refusing stale/future feed: age {age:.1f}h")
    jobs = feed.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("feed jobs must be an array")
    eligible = [j for j in jobs if suitable(j, now, days)]
    eligible.sort(
        key=lambda j: (
            timestamp(j.get("posted_at")) or timestamp(j.get("first_seen")),
            bool(j.get("direct_employer")),
        ), reverse=True,
    )
    chosen = []
    seen = set()
    for job in eligible:
        dedupe = (
            str(job.get("company") or "").casefold().strip(),
            str(job.get("title") or "").casefold().strip(),
            str(job.get("posting_url") or job.get("url") or "").split("?")[0].rstrip("/"),
        )
        if dedupe in seen:
            continue
        seen.add(dedupe)
        record = {key: job[key] for key in FIELDS if key in job}
        evidence = relevant_inspection(job["id"], inspections)
        if evidence:
            record["employer_evidence"] = evidence
        chosen.append(record)
        if len(chosen) >= limit:
            break
    return {
        "schema_version": 1,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "source_generated_at": generated.isoformat().replace("+00:00", "Z"),
        "source_content_hash": feed.get("content_hash"),
        "source_job_count": len(jobs),
        "eligible_recent_count": len(eligible),
        "selection": {"max_age_days": days, "max_jobs": limit, "personalized": False},
        "caveat": "Discovery metadata only. Verify live application availability and applicant requirements with employer; not a personalized or confirmed-open list.",
        "jobs": chosen,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--inspections", type=Path, default=None)\n    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()
    if not (1 <= args.days <= 90 and 1 <= args.limit <= 1000):
        parser.error("days must be 1..90 and limit must be 1..1000")
    data = json.loads(args.feed.read_text(encoding="utf-8"))
    inspections = json.loads(args.inspections.read_text(encoding="utf-8")) if args.inspections else None
    payload = build_export(data, days=args.days, limit=args.limit, inspections=inspections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Exported {len(payload['jobs'])} jobs; feed generated {payload['source_generated_at']}")


if __name__ == "__main__":
    main()
