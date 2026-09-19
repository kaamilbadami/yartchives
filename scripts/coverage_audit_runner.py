#!/usr/bin/env python3
"""Run a coverage audit using unique external listings as the denominator.

The underlying classifier in ``coverage_audit.py`` evaluates one listing at a
time. This runner adds sample-level integrity: repeated discoveries of the same
internship are collapsed before coverage rates are calculated, while every
observed discovery surface is preserved in the result metadata.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import coverage_audit as base  # noqa: E402
from scripts.build_feed import canonical_url, norm  # noqa: E402

ATS_HOST_HINTS: dict[str, tuple[str, ...]] = {
    "workday": ("myworkdayjobs.com",),
    "greenhouse": ("greenhouse.io",),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
    "smartrecruiters": ("smartrecruiters.com",),
    "icims": ("icims.com",),
    "oracle": ("oraclecloud.com",),
    "jobvite": ("jobvite.com",),
    "successfactors": ("successfactors.com",),
    "taleo": ("taleo.net",),
    "eightfold": ("eightfold.ai",),
    "usajobs": ("usajobs.gov",),
}
MISSING_STATUSES = {
    "configured_source_miss",
    "employer_exists_but_listing_missing",
    "source_not_covered",
    "unknown",
}

REGIONS: dict[str, tuple[str, ...]] = {
    "New England": ("CT", "ME", "MA", "NH", "RI", "VT"),
    "Mid-Atlantic": ("DE", "DC", "MD", "NJ", "NY", "PA", "VA", "WV"),
    "Southeast": ("AL", "AR", "FL", "GA", "KY", "LA", "MS", "NC", "SC", "TN"),
    "Midwest": ("IL", "IN", "IA", "KS", "MI", "MN", "MO", "NE", "ND", "OH", "SD", "WI"),
    "South Central": ("OK", "TX"),
    "Mountain West": ("AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY"),
    "West Coast / Pacific": ("AK", "CA", "HI", "OR", "WA"),
}

STATE_TO_REGION: dict[str, str] = {
    state: region
    for region, states in REGIONS.items()
    for state in states
}


def is_discovery_surface(value: str) -> bool:
    text = norm(value)
    hostname = base.host(value)
    return any(surface in text or surface in hostname for surface in base.DISCOVERY_SURFACES)


def authoritative_identity(url: str) -> tuple[str, str] | None:
    """Return an employer/ATS listing identity, never a discovery-platform ID."""
    if not url or is_discovery_surface(url):
        return None
    return base.url_identity(url)


def has_strong_signature(row: dict[str, Any]) -> bool:
    return all(
        (
            base.company_key(base.first(row, "company", "employer", "organization")),
            norm(base.first(row, "title", "role", "position")),
            base.location_key(base.first(row, "location", "locations")),
        )
    )


def ats_family(url: str) -> str:
    """Identify a known ATS family from a job URL without guessing employers."""
    hostname = base.host(url)
    if not hostname:
        return "unknown"
    for family, hints in ATS_HOST_HINTS.items():
        if any(hostname == hint or hostname.endswith(f".{hint}") for hint in hints):
            return family
    if is_discovery_surface(url):
        return "discovery-only"
    return "employer/custom"


def ats_family_for_result(result: dict[str, Any]) -> str:
    """Use the representative/direct URL first, then preserved observation URLs."""
    candidates = [str(result.get("url") or "")]
    candidates.extend(str(value) for value in (result.get("observation_urls") or []))
    for candidate in candidates:
        family = ats_family(candidate)
        if family not in {"employer/custom", "discovery-only"}:
            return family
    return ats_family(candidates[0]) if candidates else "employer/custom"


def result_states(result: dict[str, Any]) -> list[str]:
    """Return the row-level benchmark states used for regional breakdowns."""
    return [str(state).upper() for state in ((result.get("expected") or {}).get("states") or [])]


def _row_quality(row: dict[str, Any]) -> tuple[int, int]:
    url = base.first(row, "url", "apply_url", "listing_url")
    direct_bonus = 3 if url and not is_discovery_surface(url) else 0
    populated = sum(
        bool(base.first(row, *keys))
        for keys in (
            ("company", "employer", "organization"),
            ("title", "role", "position"),
            ("location", "locations"),
            ("url", "apply_url", "listing_url"),
            ("source", "source_name", "discovered_via"),
        )
    )
    return direct_bonus + populated, len(url)


def dedupe_external_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated discoveries without merging distinct requisitions.

    Matching order is deliberately conservative:
    1. exact canonical URL;
    2. same employer/ATS requisition identity;
    3. normalized company/title/location when authoritative requisition IDs do
       not conflict.

    LinkedIn, Handshake, Indeed, Glassdoor, and ZipRecruiter IDs are treated as
    observation IDs, not employer requisition IDs.
    """
    groups: list[dict[str, Any]] = []
    canonical_to_group: dict[str, int] = {}
    identity_to_group: dict[tuple[str, str], int] = {}
    signature_to_groups: defaultdict[str, list[int]] = defaultdict(list)

    for input_index, original in enumerate(rows, 1):
        row = dict(original)
        url = base.first(row, "url", "apply_url", "listing_url")
        canonical = canonical_url(url) if url else ""
        identity = authoritative_identity(url)
        signature = base.signature(row) if has_strong_signature(row) else ""

        group_index: int | None = None
        if canonical and canonical in canonical_to_group:
            group_index = canonical_to_group[canonical]
        elif identity and identity in identity_to_group:
            group_index = identity_to_group[identity]
        elif signature:
            for candidate_index in signature_to_groups.get(signature, []):
                candidate_ids = groups[candidate_index]["identities"]
                if identity and candidate_ids and identity not in candidate_ids:
                    continue
                group_index = candidate_index
                break

        if group_index is None:
            group_index = len(groups)
            groups.append(
                {
                    "rows": [],
                    "indices": [],
                    "sources": [],
                    "urls": [],
                    "identities": set(),
                    "signature": signature,
                }
            )
            if signature:
                signature_to_groups[signature].append(group_index)

        group = groups[group_index]
        group["rows"].append(row)
        group["indices"].append(input_index)
        source = base.first(row, "source", "source_name", "discovered_via")
        if source and source not in group["sources"]:
            group["sources"].append(source)
        if url and url not in group["urls"]:
            group["urls"].append(url)
        if identity:
            group["identities"].add(identity)
        if canonical:
            canonical_to_group[canonical] = group_index
        if identity:
            identity_to_group[identity] = group_index

    deduped = []
    for group in groups:
        representative = max(group["rows"], key=_row_quality).copy()
        representative["_audit_input_indices"] = group["indices"]
        representative["_audit_observation_count"] = len(group["rows"])
        representative["_audit_observed_sources"] = group["sources"]
        representative["_audit_observation_urls"] = group["urls"]
        deduped.append(representative)
    return deduped


def build_report(
    rows: list[dict[str, Any]],
    feed_doc: dict[str, Any],
    jobs: list[dict[str, Any]],
    catalog: dict[str, set[str]],
    profiles: list[str],
    states: list[str],
    audit_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unique_rows = dedupe_external_rows(rows)
    report = base.build_report(
        unique_rows,
        feed_doc,
        jobs,
        catalog,
        profiles,
        states,
        audit_meta=audit_meta,
    )

    summary = report["summary"]
    summary["external_observations"] = len(rows)
    summary["external_unique_listings"] = len(unique_rows)
    summary["duplicate_observations_collapsed"] = len(rows) - len(unique_rows)
    # Compatibility field: from this runner onward, external_listings means the
    # unique-listing denominator rather than raw discovery observations.
    summary["external_listings"] = len(unique_rows)
    report["schema_version"] = 3
    report["denominator"] = {
        "kind": "unique_external_listings",
        "external_observations": len(rows),
        "external_unique_listings": len(unique_rows),
        "duplicate_observations_collapsed": len(rows) - len(unique_rows),
    }

    for classified, row in zip(report["results"], unique_rows):
        classified["observation_count"] = int(row.get("_audit_observation_count") or 1)
        classified["observed_sources"] = list(row.get("_audit_observed_sources") or [])
        classified["input_indices"] = list(row.get("_audit_input_indices") or [])
        classified["observation_urls"] = list(row.get("_audit_observation_urls") or [])
        classified["ats_family"] = ats_family_for_result(classified)

    missing_by_ats = Counter(
        result["ats_family"]
        for result in report["results"]
        if result.get("status") in MISSING_STATUSES
    )
    summary["missing_by_ats_family"] = {
        family: count
        for family, count in sorted(missing_by_ats.items(), key=lambda item: (-item[1], item[0]))
    }
    by_state: defaultdict[str, Counter[str]] = defaultdict(Counter)
    missing_by_state: Counter[str] = Counter()
    missing_by_reason: Counter[str] = Counter()
    missing_by_discovery_source: Counter[str] = Counter()
    by_region: defaultdict[str, Counter[str]] = defaultdict(Counter)
    missing_by_region: Counter[str] = Counter()

    for result in report["results"]:
        states_for_result = result_states(result) or ["unknown"]
        for state in states_for_result:
            by_state[state][result["status"]] += 1
            if result.get("status") in MISSING_STATUSES:
                missing_by_state[state] += 1

            region = STATE_TO_REGION.get(state, "Other/Unknown")
            by_region[region][result["status"]] += 1
            if result.get("status") in MISSING_STATUSES:
                missing_by_region[region] += 1

        if result.get("status") in MISSING_STATUSES:
            missing_by_reason[str(result.get("reason_code") or "unknown")] += 1
            missing_by_discovery_source[str(result.get("source") or "unknown")] += 1

    summary["by_state"] = {
        state: dict(counts) for state, counts in sorted(by_state.items())
    }
    summary["missing_by_state"] = dict(sorted(missing_by_state.items()))

    recall_by_state: dict[str, dict[str, Any]] = {}
    for state, counts in summary["by_state"].items():
        total = sum(counts.values())
        missing = missing_by_state.get(state, 0)
        captured = total - missing
        recall = round(captured / total, 4) if total else 0.0
        recall_by_state[state] = {
            "total": total,
            "missing": missing,
            "captured": captured,
            "recall": recall,
        }
    summary["recall_by_state"] = dict(sorted(recall_by_state.items()))

    recall_by_region: dict[str, dict[str, Any]] = {}
    for region, counts in sorted(by_region.items()):
        total = sum(counts.values())
        missing = missing_by_region.get(region, 0)
        captured = total - missing
        recall = round(captured / total, 4) if total else 0.0
        recall_by_region[region] = {
            "total": total,
            "missing": missing,
            "captured": captured,
            "recall": recall,
        }
    summary["recall_by_region"] = recall_by_region
    summary["missing_by_reason_code"] = {
        reason: count
        for reason, count in sorted(missing_by_reason.items(), key=lambda item: (-item[1], item[0]))
    }
    summary["missing_by_discovery_source"] = {
        source: count
        for source, count in sorted(
            missing_by_discovery_source.items(), key=lambda item: (-item[1], item[0])
        )
    }

    return report


def markdown(report: dict[str, Any]) -> str:
    text = base.markdown(report)
    summary = report["summary"]
    needle = f"- External listings audited: **{summary['external_listings']}**"
    replacement = "\n".join(
        (
            f"- External observations collected: **{summary['external_observations']}**",
            f"- Unique external listings (denominator): **{summary['external_unique_listings']}**",
            f"- Duplicate observations collapsed: **{summary['duplicate_observations_collapsed']}**",
        )
    )
    text = text.replace(needle, replacement, 1)

    ats_counts = summary.get("missing_by_ats_family") or {}
    ats_lines = ["## Missing listings by ATS family", ""]
    if ats_counts:
        ats_lines.extend(f"- `{family}`: **{count}**" for family, count in ats_counts.items())
    else:
        ats_lines.append("No missing listings in this sample.")
    ats_section = "\n".join(ats_lines) + "\n\n"
    state_lines = ["## Results by benchmark state", ""]
    for state, stats in summary.get("recall_by_state", {}).items():
        total = stats["total"]
        missing = stats["missing"]
        recall = stats["recall"]
        state_lines.append(f"- `{state}`: **{total}** listings, **{missing}** missing ({recall:.1%} recall)")

    region_lines = ["", "## Results by region", ""]
    for region, stats in summary.get("recall_by_region", {}).items():
        total = stats["total"]
        missing = stats["missing"]
        recall = stats["recall"]
        region_lines.append(f"- `{region}`: **{total}** listings, **{missing}** missing ({recall:.1%} recall)")

    reason_lines = ["", "## Missing listings by reason code", ""]
    reason_counts = summary.get("missing_by_reason_code") or {}
    reason_lines.extend(
        (f"- `{reason}`: **{count}**" for reason, count in reason_counts.items()),
    )
    if not reason_counts:
        reason_lines.append("No missing listings in this sample.")
    breakdown_section = "\n".join(state_lines + region_lines + reason_lines) + "\n\n"
    return text.replace(
        "## Status breakdown\n",
        ats_section + breakdown_section + "## Status breakdown\n",
        1,
    )


def _write_text(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("discoveries")
    parser.add_argument("--feed", default=str(base.FEED))
    parser.add_argument("--sources", default=str(base.SOURCES))
    parser.add_argument("--direct-sources", default=str(base.DIRECT))
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--state", action="append", default=[])
    parser.add_argument("--output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    input_path = Path(args.discoveries)
    audit_meta, rows = base.load_audit_input(input_path)
    metadata_scope = audit_meta.get("scope") or {}
    profiles = args.profile or base.as_list(metadata_scope.get("profiles"))
    states = args.state or base.as_list(metadata_scope.get("states"))

    feed_doc = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    jobs = [job for job in feed_doc.get("jobs", []) if isinstance(job, dict)]
    report = build_report(
        rows,
        feed_doc,
        jobs,
        base.source_catalog(Path(args.sources), Path(args.direct_sources)),
        profiles,
        states,
        audit_meta=audit_meta,
    )
    report["input_file"] = str(input_path)

    rendered = markdown(report)
    print(rendered, end="")
    if args.output:
        _write_text(args.output, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if args.markdown_output:
        _write_text(args.markdown_output, rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
