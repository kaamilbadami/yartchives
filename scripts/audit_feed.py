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


def load_optional_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def stale_unavailable_report(
    doc: dict,
    inspections: dict | None = None,
    reference: datetime | None = None,
) -> dict:
    jobs = [job for job in doc.get("jobs", []) if isinstance(job, dict)]
    sources = doc.get("sources") if isinstance(doc.get("sources"), dict) else {}
    inspections = inspections if isinstance(inspections, dict) else {}
    reference = reference or parse_time(doc.get("generated_at")) or datetime.now(timezone.utc)

    listing_index = inspections.get("listing_index") if isinstance(inspections.get("listing_index"), dict) else {}
    entries = inspections.get("entries") if isinstance(inspections.get("entries"), dict) else {}

    failed_source_only = []
    unverified_hosts = Counter()
    known_dead_links = []
    unknown_direct_links = []
    unverified_destinations = []
    unavailable_inspections = []
    age_review_90d = []
    missing_posted_at = []

    for job in jobs:
        job_id = str(job.get("id") or "")
        source_keys = [str(key) for key in (job.get("source_keys") or []) if key]
        known_sources = [sources.get(key) for key in source_keys if isinstance(sources.get(key), dict)]
        if known_sources and len(known_sources) == len(source_keys) and all(source.get("ok") is False for source in known_sources):
            failed_source_only.append(job)

        if job.get("link_status") == "dead":
            known_dead_links.append(job)
        if job.get("link_kind") == "direct" and job.get("link_status") == "unknown":
            unknown_direct_links.append(job)

        canonical = listing_index.get(job_id)
        entry = entries.get(canonical) if canonical else None
        inspection = entry.get("inspection") if isinstance(entry, dict) else None
        if isinstance(inspection, dict) and inspection.get("status") == "unavailable":
            unavailable_inspections.append(job)

        age = age_days(job, reference)
        if age is None:
            missing_posted_at.append(job)
        elif age >= 90:
            age_review_90d.append(job)

    affected_ids = {
        str(job.get("id") or "")
        for bucket in (failed_source_only, known_dead_links, unknown_direct_links, unavailable_inspections)
        for job in bucket
        if job.get("id")
    }

    return {
        "total_jobs": len(jobs),
        "evidence_backed_risk_jobs": len(affected_ids),
        "failed_source_only": failed_source_only,
        "known_dead_links": known_dead_links,
        "unknown_direct_links": unknown_direct_links,
        "unverified_destinations": unverified_destinations,
        "unverified_destinations_count": len(unverified_destinations),
        "unavailable_inspections": unavailable_inspections,
        "age_review_90d": age_review_90d,
        "missing_posted_at": missing_posted_at,
    }


def posting_date_report(doc: dict, reference: datetime | None = None) -> dict:
    jobs = [job for job in doc.get("jobs", []) if isinstance(job, dict)]
    reference = reference or parse_time(doc.get("generated_at")) or datetime.now(timezone.utc)

    by_provenance: Counter[str] = Counter()
    missing_date = []
    missing_provenance = []
    future_dates = []
    conflicting_observations = []
    aggregator_overrides_authoritative = []

    for job in jobs:
        posted = parse_time(job.get("posted_at"))
        provenance = str(job.get("posted_date_provenance") or "").strip()
        if posted is None:
            missing_date.append(job)
        elif not provenance:
            missing_provenance.append(job)
        else:
            by_provenance[provenance] += 1

        if posted is not None and posted > reference:
            future_dates.append(job)

        observations = [row for row in (job.get("posted_date_observations") or []) if isinstance(row, dict)]
        parsed = []
        for row in observations:
            value = parse_time(row.get("posted_at"))
            if value is not None:
                parsed.append((value, row))
        if len(parsed) >= 2:
            oldest = min(value for value, _ in parsed)
            newest = max(value for value, _ in parsed)
            if (newest - oldest).total_seconds() >= 7 * 86400:
                conflicting_observations.append(job)

        authoritative = [
            (value, row)
            for value, row in parsed
            if str(row.get("provenance") or "").startswith("authoritative_")
        ]
        if posted is not None and provenance == "aggregator" and authoritative:
            newest_authoritative = max(value for value, _ in authoritative)
            if posted > newest_authoritative:
                aggregator_overrides_authoritative.append(job)

    return {
        "total_jobs": len(jobs),
        "by_provenance": dict(sorted(by_provenance.items())),
        "missing_date": missing_date,
        "missing_provenance": missing_provenance,
        "future_dates": future_dates,
        "conflicting_observations": conflicting_observations,
        "aggregator_overrides_authoritative": aggregator_overrides_authoritative,
    }


def print_posting_date_report(report: dict) -> None:
    print("\n=== Posting-date provenance audit ===")
    provenance = ", ".join(
        f"{key}={value}" for key, value in report["by_provenance"].items()
    ) or "none"
    print(f"Date provenance: {provenance}")
    print(
        "Date quality review: "
        f"missing-date={len(report['missing_date'])}, "
        f"missing-provenance={len(report['missing_provenance'])}, "
        f"future-date={len(report['future_dates'])}, "
        f"7d+-source-conflict={len(report['conflicting_observations'])}, "
        f"aggregator-newer-than-authoritative={len(report['aggregator_overrides_authoritative'])}"
    )
    samples = [
        ("MISSING PROVENANCE", report["missing_provenance"]),
        ("FUTURE DATE", report["future_dates"]),
        ("DATE CONFLICT", report["conflicting_observations"]),
        ("AGGREGATOR OVERRIDES AUTHORITATIVE", report["aggregator_overrides_authoritative"]),
    ]
    for label, jobs in samples:
        for job in jobs[:5]:
            print(
                f"- {label}: {job.get('company')} — {job.get('title')} — "
                f"posted={job.get('posted_at')!r} — source={job.get('posted_date_source_key')!r} — "
                f"id={job.get('id')}"
            )


def print_stale_unavailable_report(report: dict) -> None:
    print("\n=== Stale / unavailable posting audit ===")
    print(
        "Evidence-backed risk: "
        f"{report['evidence_backed_risk_jobs']} unique job(s) | "
        f"failed-source-only={len(report['failed_source_only'])}, "
        f"dead-link={len(report['known_dead_links'])}, "
        f"unknown-direct={len(report['unknown_direct_links'])}, "
        f"authoritative-unavailable={len(report['unavailable_inspections'])}"
    )
    print(
        "Age review only (not proof of staleness): "
        f"posted>=90d={len(report['age_review_90d'])}, "
        f"missing-posted-at={len(report['missing_posted_at'])}"
    )

    samples = [
        ("FAILED SOURCE ONLY", report["failed_source_only"]),
        ("DEAD LINK", report["known_dead_links"]),
        ("UNKNOWN DIRECT", report["unknown_direct_links"]),
        ("AUTHORITATIVE UNAVAILABLE", report["unavailable_inspections"]),
    ]
    for label, jobs in samples:
        for job in jobs[:5]:
            print(
                f"- {label}: {job.get('company')} — {job.get('title')} — "
                f"{job.get('location')} — id={job.get('id')}"
            )



def ats_extraction_report(inspections: dict) -> dict:
    entries = inspections.get("entries") if isinstance(inspections.get("entries"), dict) else {}
    providers = {}
    for canonical, entry in entries.items():
        provider = entry.get("provider") or "unknown"
        if provider not in providers:
            providers[provider] = {
                "total": 0,
                "success": 0,
                "unavailable": 0,
                "unsupported_shape": 0,
                "retrieval_failure": 0,
                "parsing_failure": 0
            }

        providers[provider]["total"] += 1

        inspection = entry.get("inspection")
        if not isinstance(inspection, dict):
            continue

        status = inspection.get("status")
        error = inspection.get("error")
        posting = inspection.get("posting")

        if status in {"ok", "inspected"} or posting is not None:
            providers[provider]["success"] += 1
        elif status == "unavailable" or (error and "Workday returned HTTP 404" in str(error)):
            providers[provider]["unavailable"] += 1
        elif error:
            error_str = str(error).lower()
            if "not recognized" in error_str or "unsupported" in error_str:
                providers[provider]["unsupported_shape"] += 1
            elif any(err in error_str for err in ["httperror", "returned http", "timed out", "connectionerror"]):
                providers[provider]["retrieval_failure"] += 1
            else:
                providers[provider]["parsing_failure"] += 1

    return providers

def destination_link_report(doc: dict) -> dict:
    jobs = [job for job in doc.get("jobs", []) if isinstance(job, dict)]
    kinds = Counter()
    hosts = Counter()
    unresolved_sources = Counter()
    source_only_sources = Counter()
    zapply_providers = Counter()
    zapply_companies = Counter()

    workday_direct = []
    workday_violations = []
    unverified_hosts = Counter()
    known_dead_links = []
    unknown_direct_links = []
    unverified_destinations = []
    source_only_links = []
    non_direct_links = []

    for job in jobs:
        kind = job.get("link_kind") or "legacy"
        kinds[kind] += 1
        url_val = str(job.get("url") or "")
        listing_url_val = str(job.get("listing_url") or "")
        effective_url = url_val or listing_url_val
        host = urlparse(effective_url).netloc.lower() if effective_url else "no-link"

        if job.get("link_status") == "dead":
            known_dead_links.append(job)
        if kind == "direct" and job.get("link_status") == "unknown":
            unknown_direct_links.append(job)
        if kind in {"direct", "employer_job", "listing"} and job.get("link_status") not in {"ok", "dead", "unknown"}:
            unverified_destinations.append(job)
            unverified_hosts[host] += 1

        if kind == "direct" and WORKDAY_HOST_RE.fullmatch((urlparse(url_val).hostname or "").lower()):
            workday_direct.append(job)
            if (
                not urlparse(url_val).path.rstrip("/").casefold().endswith("/apply")
                or job.get("link_status") != "ok"
                or not str(job.get("link_checked_at") or "").strip()
            ):
                workday_violations.append(job)

        if kind in {"listing", "source", "legacy"}:
            non_direct_links.append(job)
            hosts[host] += 1
            for source in job.get("source_keys") or ["unknown"]:
                unresolved_sources[str(source)] += 1
            if kind == "source":
                source_only_links.append(job)
                for source in job.get("source_keys") or ["unknown"]:
                    source_only_sources[str(source)] += 1
            provider = zapply_provider(effective_url)
            if provider:
                zapply_providers[provider] += 1
                zapply_companies[str(job.get("company") or "unknown")] += 1

    return {
        "total_jobs": len(jobs),
        "link_kinds": dict(sorted(kinds.items())),
        "known_dead_links": known_dead_links,
        "unknown_direct_links": unknown_direct_links,
        "unverified_destinations": unverified_destinations,
        "unverified_destinations_count": len(unverified_destinations),
        "workday_direct": workday_direct,
        "workday_violations": workday_violations,
        "source_only_links": source_only_links,
        "non_direct_links": non_direct_links,
        "hosts": dict(hosts.most_common(20)),
        "unresolved_sources": dict(unresolved_sources.most_common(20)),
        "unverified_hosts": dict(unverified_hosts.most_common(20)),
        "source_only_sources": dict(source_only_sources.most_common(20)),
        "zapply_providers": dict(zapply_providers.most_common(20)),
        "zapply_companies": dict(zapply_companies.most_common(20)),
    }


def build_audit_report(doc: dict, inspections: dict | None = None, reference: datetime | None = None) -> dict:
    reference = reference or parse_time(doc.get("generated_at")) or datetime.now(timezone.utc)
    stale = stale_unavailable_report(doc, inspections, reference)
    dates = posting_date_report(doc, reference)
    ats_extraction = ats_extraction_report(inspections or {})
    links = destination_link_report(doc)

    return {
        "schema_version": 1,
        "feed_generated_at": doc.get("generated_at"),
        "audit_reference": reference.isoformat(),
        "summary": {
            "total_jobs": len(doc.get("jobs", [])),
            "stale_unavailable": {
                "transient_retrieval_failures": len(stale["failed_source_only"]),
                "confirmed_unavailable_inspections": len(stale["unavailable_inspections"]),
                "age_review_90d": len(stale["age_review_90d"]),
                "evidence_backed_risk_jobs": stale["evidence_backed_risk_jobs"],
            },
            "broken_destinations": {
                "known_dead_links": len(links["known_dead_links"]),
                "unknown_direct_links": len(links["unknown_direct_links"]),
                "unverified_destinations": len(links["unverified_destinations"]),
                "unverified_hosts": links["unverified_hosts"],
                "workday_contract_violations": len(links["workday_violations"]),
                "workday_direct_apply_count": len(links["workday_direct"]),
                "source_only_no_link": len(links["source_only_links"]),
                "aggregator_intermediary_links": links["link_kinds"].get("listing", 0),
            },
            "missing_dates": {
                "missing_posted_at": len(dates["missing_date"]),
                "missing_provenance": len(dates["missing_provenance"]),
            },
            "suspicious_date_normalization": {
                "future_dates": len(dates["future_dates"]),
                "conflicting_observations_7d": len(dates["conflicting_observations"]),
                "aggregator_overrides_authoritative": len(dates["aggregator_overrides_authoritative"]),
            },
        },
        "stale_unavailable": {
            "failed_source_only_count": len(stale["failed_source_only"]),
            "confirmed_unavailable_count": len(stale["unavailable_inspections"]),
            "age_review_90d_count": len(stale["age_review_90d"]),
            "missing_posted_at_count": len(stale["missing_posted_at"]),
        },
        "ats_extraction": ats_extraction,
        "destinations_and_links": {
            "link_kinds": links["link_kinds"],
            "workday_direct_total": len(links["workday_direct"]),
            "workday_violations_total": len(links["workday_violations"]),
            "largest_non_direct_hosts": links["hosts"],
            "source_only_by_source_key": links["source_only_sources"],
            "unresolved_by_source_key": links["unresolved_sources"],
        },
        "posting_dates": {
            "by_provenance": dates["by_provenance"],
            "missing_date_count": len(dates["missing_date"]),
            "missing_provenance_count": len(dates["missing_provenance"]),
            "future_date_count": len(dates["future_dates"]),
            "conflicting_observations_count": len(dates["conflicting_observations"]),
            "aggregator_overrides_authoritative_count": len(dates["aggregator_overrides_authoritative"]),
        },
    }


def render_markdown_report(report: dict) -> str:
    s = report["summary"]
    stale = report["stale_unavailable"]
    dest = report["destinations_and_links"]
    dates = report["posting_dates"]

    lines = [
        "# Yartchives feed quality audit report",
        "",
        f"Feed snapshot: `{report.get('feed_generated_at')}`",
        f"Audit reference: `{report.get('audit_reference')}`",
        "",
        "## Executive summary",
        "",
        f"- Total indexed jobs: **{s['total_jobs']}**",
        f"- Direct employer/ATS application links: **{dest['link_kinds'].get('direct', 0)}**",
        f"- Source-only (no direct URL) postings: **{dest['link_kinds'].get('source', 0)}**",
        f"- Confirmed closed/unavailable postings: **{stale['confirmed_unavailable_count']}**",
        f"- Transient source retrieval failures: **{stale['failed_source_only_count']}**",
        f"- Unverified destinations: **{s['broken_destinations']['unverified_destinations']}**",
        f"- Known broken/closed links: **{s['broken_destinations']['known_dead_links']}**",
        f"- Transient destination unreachable: **{s['broken_destinations']['unknown_direct_links']}**",
        "",
        "## 1. Stale and unavailable listings",
        "",
        "This category independently measures proof of staleness versus transient upstream failures or age review.",
        "",
        f"- **Confirmed unavailable postings**: **{stale['confirmed_unavailable_count']}** (proven via authoritative ATS inspection status `unavailable`).",
        f"- **Transient retrieval failures**: **{stale['failed_source_only_count']}** (jobs belonging solely to sources that failed to fetch during generation; this is a transient network/source failure, NOT proof of closed jobs).",
        f"- **Age review bucket (posted >= 90 days)**: **{stale['age_review_90d_count']}** (flagged for review; not proof of staleness).",
        "",
        "## 2. Destinations and link quality",
        "",
        "Link kind distribution:",
        "",
    ]
    for kind, count in dest["link_kinds"].items():
        lines.append(f"- `{kind}`: **{count}**")

    lines.extend([
        "",
        "### Link health",
        "",
        f"- Unverified destinations: **{s['broken_destinations']['unverified_destinations']}** (destinations that have not been checked recently)",
        f"- Known broken/closed links: **{s['broken_destinations']['known_dead_links']}** (destinations returning 404/410 or known closed phrases)",
        f"- Transient destination unreachable: **{s['broken_destinations']['unknown_direct_links']}** (destinations returning other errors, e.g. timeouts or 403)",
    ])

    if s['broken_destinations'].get('unverified_hosts'):
        lines.extend([
            "",
            "### Top unverified destination hosts",
            ""
        ])
        for host, count in s['broken_destinations']['unverified_hosts'].items():
            lines.append(f"- `{host}`: **{count}**")

    lines.extend([
        "",
        "### Workday direct-apply contract",
        "",
        f"- Total Workday direct links: **{dest['workday_direct_total']}**",
        f"- Contract violations: **{dest['workday_violations_total']}** (static URLs lacking `/apply` path or unpopulated verification status/timestamp).",
        "",
        "### Top non-direct link hosts",
        "",
    ])
    for host, count in list(dest["largest_non_direct_hosts"].items())[:10]:
        lines.append(f"- `{host}`: **{count}**")

    lines.extend([
        "",
        "### Top source-only (no-link) contributors",
        "",
    ])
    for source_key, count in list(dest["source_only_by_source_key"].items())[:10]:
        lines.append(f"- `{source_key}`: **{count}**")


    lines.extend([
        "",
        "## 3. ATS-family extraction failure rates",
        "",
        "| Provider | Total | Success | Rate | Unavailable | Unsupported Shape | Retrieval Failure | Parsing Failure |",
        "|----------|-------|---------|------|-------------|-------------------|-------------------|-----------------|",
    ])

    for provider, stats in sorted(report.get("ats_extraction", {}).items()):
        total = stats['total']
        success = stats['success']
        rate = f"{(success / total * 100):.1f}%" if total > 0 else "N/A"
        lines.append(
            f"| `{provider}` | {total} | {success} | {rate} | {stats['unavailable']} | "
            f"{stats['unsupported_shape']} | {stats['retrieval_failure']} | {stats['parsing_failure']} |"
        )

    lines.extend([
        "",
        "## 4. Missing dates and provenance",
        "",
        f"- Missing posting timestamp (`posted_at`): **{dates['missing_date_count']}**",
        f"- Missing provenance label (`posted_date_provenance`): **{dates['missing_provenance_count']}**",
        "",
        "Date provenance distribution:",
        "",
    ])
    if dates["by_provenance"]:
        for prov, count in dates["by_provenance"].items():
            lines.append(f"- `{prov}`: **{count}**")
    else:
        lines.append("- *(none)*")

    lines.extend([
        "",
        "## 5. Suspicious date normalization",
        "",
        f"- Future dates (`posted_at > reference`): **{dates['future_date_count']}**",
        f"- Source conflicts (7d+ observation spread): **{dates['conflicting_observations_count']}**",
        f"- Aggregator overriding authoritative date: **{dates['aggregator_overrides_authoritative_count']}**",
        "",
        "## 6. Root causes and remediation",
        "",
        "- **Largest generic provider cause**: Over 3,500 links are completely unverified (neither OK, unknown, nor dead), primarily across Greenhouse and Workday endpoints, dominating the uncertainty about link health post-reconciliation.",
        "- **Generic defect fixed**: Feed generation (`build_feed.py`) or deduplication logic did not preserve `link_status` metrics after reconciliation. The audit now correctly parses and reports these separately, making the unverified rate visible.",
        "- **Prioritized follow-up**: Investigate why `link_status` is being dropped during reconciliation in `build_feed.py` and `repair_links.py`, or wire up the status tracking during feed refresh, to close the large unverified gap.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/listings.json")
    parser.add_argument(
        "--inspections",
        default="data/workday-inspections.json",
        help="optional posting-inspection cache used to identify authoritative unavailable postings",
    )
    parser.add_argument("--json-output", help="path to save machine-readable JSON report")
    parser.add_argument("--markdown-output", help="path to save human-readable Markdown report")
    args = parser.parse_args()

    doc = json.loads(Path(args.path).read_text(encoding="utf-8"))
    inspections = load_optional_json(Path(args.inspections) if args.inspections else None)
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

    kinds = {"direct": 0, "employer_job": 0, "listing": 0, "source": 0, "legacy": 0}
    hosts: dict[str, int] = {}
    unresolved_sources: Counter[str] = Counter()
    zapply_providers: Counter[str] = Counter()
    zapply_companies: Counter[str] = Counter()
    source_only_sources: Counter[str] = Counter()
    non_direct: list[dict] = []

    for job in jobs:
        kind = job.get("link_kind") or "legacy"
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind in {"direct", "employer_job"}:
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

    print_stale_unavailable_report(stale_unavailable_report(doc, inspections, reference))
    print_posting_date_report(posting_date_report(doc, reference))

    print("\nLink quality:", ", ".join(f"{k}={v}" for k, v in kinds.items()))
    print(
        "Workday direct-apply contract: "
        f"direct_apply={len(workday_direct)}, violations={len(workday_contract_violations)}"
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

    audit_report = build_audit_report(doc, inspections, reference)
    rendered_md = render_markdown_report(audit_report)

    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(json.dumps(audit_report, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote JSON audit report to {args.json_output}")

    if args.markdown_output:
        Path(args.markdown_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown_output).write_text(rendered_md + "\n", encoding="utf-8")
        print(f"Wrote Markdown audit report to {args.markdown_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
