#!/usr/bin/env python3
"""Audit source capture, provenance overlap, and incremental contribution.

This report intentionally measures the generated feed snapshot rather than the
wider internship market.  ``sources[*].count`` is the number of eligible rows
accepted by the production adapter before cross-source deduplication.  It is a
defensible denominator for adapter capture, but not for the source platform's
unpublished or broader inventory.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_SOURCES = ROOT / "sources.json"
DEFAULT_DIRECT = ROOT / "direct_sources.json"

# Classification is about the immediate input Yartchives consumes.  Notes keep
# claimed/original platforms separate from mirrors and public subsets.
SOURCE_METADATA: dict[str, dict[str, str]] = {
    "dreamwork-tech": {"class": "broad aggregator", "scope": "2027 technology internships in Dreamwork's public JSON feed", "confidence": "high"},
    "dreamwork-business": {"class": "broad aggregator", "scope": "2027 business internships in Dreamwork's public JSON feed", "confidence": "high"},
    "zapply": {"class": "broad aggregator", "scope": "2027 internships published in Zapply's GitHub README", "confidence": "high"},
    "simplify": {"class": "curated GitHub/list", "scope": "2027 internships published in SimplifyJobs/Summer2027-Internships", "confidence": "high"},
    "vansh-cscareers": {"class": "curated GitHub/list", "scope": "2027 internships published in vanshb03/Summer2027-Internships", "confidence": "high"},
    "speedyapply": {"class": "curated GitHub/list", "scope": "2027 SWE college jobs published in speedyapply/2027-SWE-College-Jobs", "confidence": "high"},
    "applyguy": {"class": "broad aggregator", "scope": "2027 internships published in ApplyGuy/2027-Internships", "confidence": "high"},
    "sndsh": {"class": "curated GitHub/list", "scope": "2027 internships published in sndsh404/summer-2027-internships", "confidence": "high"},
    "public-sector": {"class": "aggregator-derived mirror/subset", "scope": "rows in jobright-ai/2026-Public-Sector-Internship; broader Jobright inventory is not measurable", "confidence": "high for repository subset; not measurable for Jobright"},
    "campus-to-career": {"class": "curated GitHub/list", "scope": "rows in fromcampustocareer/fromcampustocareer-opportunities", "confidence": "high"},
    "usajobs": {"class": "direct employer / ATS", "scope": "USAJOBS student hiring-path results from the prior 60 days matching explicit student/intern terms", "confidence": "high for API query; broader federal inventory not measured"},
}


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def source_catalog(sources_path: Path, direct_path: Path) -> dict[str, dict[str, Any]]:
    rows = json.loads(sources_path.read_text(encoding="utf-8"))
    direct = json.loads(direct_path.read_text(encoding="utf-8"))
    catalog = {row["key"]: dict(row) for row in rows + direct}
    catalog["usajobs"] = {
        "key": "usajobs", "name": "USAJOBS",
        "url": "https://data.usajobs.gov/api/Search",
        "homepage": "https://www.usajobs.gov/Search/Results?k=intern",
    }
    for key, row in catalog.items():
        if key in SOURCE_METADATA:
            row.update(SOURCE_METADATA[key])
        elif row.get("kind") == "workday":
            row.update({
                "class": "direct employer / ATS",
                "scope": "configured employer's CT student opportunities matching the source-specific CS rules",
                "confidence": "high",
            })
        else:
            row.update({"class": "other", "scope": "configured input", "confidence": "medium"})
    return catalog


def link_bucket(job: dict[str, Any]) -> str:
    kind = str(job.get("link_kind") or "")
    if kind == "direct":
        return "direct_employer_ats"
    if kind == "listing":
        return "aggregator_intermediary"
    if kind == "source":
        return "unresolved_non_authoritative"
    return "employer_careers_page" if job.get("url") else "unresolved_non_authoritative"


def build_report(feed: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    jobs = [job for job in feed.get("jobs", []) if isinstance(job, dict)]
    total = len(jobs)
    health = feed.get("sources") if isinstance(feed.get("sources"), dict) else {}
    keys = sorted({str(key) for job in jobs for key in (job.get("source_keys") or [])})
    source_sets = {key: {i for i, job in enumerate(jobs) if key in (job.get("source_keys") or [])} for key in keys}
    direct_keys = {key for key in keys if catalog.get(key, {}).get("class") == "direct employer / ATS"}

    source_rows = []
    for key in keys:
        indices = source_sets[key]
        unique = sum(len(jobs[i].get("source_keys") or []) == 1 for i in indices)
        buckets = Counter(link_bucket(jobs[i]) for i in indices)
        raw_count = health.get(key, {}).get("count")
        captured = int(raw_count) if isinstance(raw_count, int) else None
        meta = catalog.get(key, {"key": key, "name": health.get(key, {}).get("name", key)})
        source_rows.append({
            "key": key,
            "source": meta.get("name", key),
            "class": meta.get("class", "other"),
            "immediate_upstream": meta.get("url") or meta.get("api_url") or meta.get("homepage", ""),
            "claimed_or_original_source": meta.get("homepage", ""),
            "scope": meta.get("scope", "configured input"),
            "upstream_eligible": captured,
            "ingested": captured,
            "coverage_percent": 100.0 if captured is not None else None,
            "coverage_basis": "production adapter-eligible rows in this feed snapshot; not the platform's wider inventory",
            "final_canonical_jobs": len(indices),
            "unique_jobs": unique,
            "unique_percent_of_feed": pct(unique, total),
            "overlap_jobs": len(indices) - unique,
            "direct_ats_links": buckets["direct_employer_ats"],
            "direct_ats_link_percent": pct(buckets["direct_employer_ats"], len(indices)),
            "link_quality": dict(sorted(buckets.items())),
            "coverage_confidence": meta.get("confidence", "medium"),
        })

    pairs = []
    for left, right in combinations(keys, 2):
        count = len(source_sets[left] & source_sets[right])
        if count:
            pairs.append({"left": left, "right": right, "canonical_jobs": count})
    pairs.sort(key=lambda row: (-row["canonical_jobs"], row["left"], row["right"]))

    direct_provenance = sum(bool(set(job.get("source_keys") or []) & direct_keys) for job in jobs)
    multi_source = sum(len(job.get("source_keys") or []) > 1 for job in jobs)
    direct_links = sum(link_bucket(job) == "direct_employer_ats" for job in jobs)
    return {
        "schema_version": 1,
        "feed_generated_at": feed.get("generated_at"),
        "summary": {
            "final_feed_jobs": total,
            "direct_employer_ats_provenance_jobs": direct_provenance,
            "direct_employer_ats_provenance_percent": pct(direct_provenance, total),
            "aggregator_list_only_provenance_jobs": total - direct_provenance,
            "aggregator_list_only_provenance_percent": pct(total - direct_provenance, total),
            "direct_employer_ats_link_jobs": direct_links,
            "direct_employer_ats_link_percent": pct(direct_links, total),
            "single_source_jobs": total - multi_source,
            "single_source_percent": pct(total - multi_source, total),
            "multi_source_jobs": multi_source,
            "multi_source_percent": pct(multi_source, total),
        },
        "sources": source_rows,
        "pairwise_overlap": pairs,
        "configured_zero_contribution": sorted(
            key for key, value in health.items() if value.get("configured") and key not in keys
        ),
    }


def markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Yartchives source contribution audit", "",
        f"Feed snapshot: `{report.get('feed_generated_at')}`", "",
        "## Executive summary", "",
        f"- Final canonical jobs: **{s['final_feed_jobs']}**",
        f"- Direct employer/ATS source provenance: **{s['direct_employer_ats_provenance_jobs']} ({s['direct_employer_ats_provenance_percent']}%)**",
        f"- Aggregator/list-only provenance: **{s['aggregator_list_only_provenance_jobs']} ({s['aggregator_list_only_provenance_percent']}%)**",
        f"- Direct employer/ATS application links: **{s['direct_employer_ats_link_jobs']} ({s['direct_employer_ats_link_percent']}%)**",
        f"- Single-source canonical jobs: **{s['single_source_jobs']} ({s['single_source_percent']}%)**",
        f"- Multi-source canonical jobs: **{s['multi_source_jobs']} ({s['multi_source_percent']}%)**", "",
        "The 100% capture figures below mean all rows accepted by the production adapter reached pre-dedup ingestion. They do not claim full coverage of a platform, repository rows the adapter cannot interpret, or the wider internship market.", "",
        "## Source coverage", "",
        "| Source | Class | Upstream eligible | Ingested | Final | Coverage | Unique | Unique % feed | Overlap | Direct/ATS links | Confidence |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["sources"]:
        coverage = "not measurable" if row["coverage_percent"] is None else f"{row['coverage_percent']:.1f}%*"
        lines.append(
            f"| {row['source']} (`{row['key']}`) | {row['class']} | {row['upstream_eligible'] if row['upstream_eligible'] is not None else 'N/A'} | "
            f"{row['ingested'] if row['ingested'] is not None else 'N/A'} | {row['final_canonical_jobs']} | {coverage} | "
            f"{row['unique_jobs']} | {row['unique_percent_of_feed']:.1f}% | {row['overlap_jobs']} | "
            f"{row['direct_ats_links']} ({row['direct_ats_link_percent']:.1f}%) | {row['coverage_confidence']} |"
        )
    lines.extend(["", "## Largest pairwise overlaps", ""])
    for pair in report["pairwise_overlap"][:20]:
        lines.append(f"- `{pair['left']}` + `{pair['right']}`: **{pair['canonical_jobs']}**")
    if report["configured_zero_contribution"]:
        lines.extend(["", "Configured inputs with zero final contribution: " + ", ".join(f"`{key}`" for key in report["configured_zero_contribution"]) + "."])
    lines.extend(["", "## Source scope and link quality", ""])
    for row in report["sources"]:
        buckets = ", ".join(f"{key}={value}" for key, value in row["link_quality"].items()) or "none"
        lines.extend([
            f"### {row['source']} (`{row['key']}`)", "",
            f"Immediate upstream: {row['immediate_upstream']}", "",
            f"Scope: {row['scope']}. Link buckets: {buckets}.", "",
        ])
    lines.extend([
        "## Interpretation and gaps", "",
        "- **Source capture gap:** no loss is visible between adapter-eligible rows and ingestion in this snapshot. This does not test rows the adapter failed to recognize, so repository/API raw-universe capture remains a verification gap unless separately inventoried.",
        "- **Market coverage gap:** not measurable from these overlapping aggregators and lists. No market-wide denominator is available.",
        "- **Verification gap:** records in `aggregator_intermediary` or `unresolved_non_authoritative` link buckets still lack a direct authoritative application destination.",
        "- **Mirror warning:** `public-sector` is the public `jobright-ai/2026-Public-Sector-Internship` repository only. Its coverage must not be described as coverage of Jobright's full database.", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", default=str(DEFAULT_FEED))
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    parser.add_argument("--direct-sources", default=str(DEFAULT_DIRECT))
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()
    feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    report = build_report(feed, source_catalog(Path(args.sources), Path(args.direct_sources)))
    rendered = markdown(report)
    print(rendered)
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
