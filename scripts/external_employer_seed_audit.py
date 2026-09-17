#!/usr/bin/env python3
"""Audit external employer/ATS seed datasets against the Yartchives employer universe.

This tool is intentionally read-only: it never mutates employer_universe.json.
It separates authoritative employer rows from URL-only ATS-board evidence so
URL slugs cannot silently become production employer identities.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from employer_universe import normalize_name
from provider_fingerprint import PROVIDER_PATTERNS

PROVIDER_ALIASES = {
    "workday": "workday",
    "greenhouse": "greenhouse",
    "icims": "icims",
    "ashby": "ashby",
    "oracle cloud hcm": "oracle",
    "taleo": "oracle",
    "successfactors": "successfactors",
    "sap successfactors": "successfactors",
    "smartrecruiters": "smartrecruiters",
    "lever": "lever",
    "eightfold": "eightfold",
    "avature": "avature",
    "phenom": "phenom",
    "phenom people": "phenom",
}
SUPPORTED_FAMILIES = {family for family, _ in PROVIDER_PATTERNS}


def _identity_index(universe: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for employer in universe.get("employers", []):
        for value in [employer.get("name", ""), *(employer.get("aliases") or [])]:
            key = normalize_name(str(value))
            if key:
                index[key] = employer
    return index


def _has_domain_hint(employer: dict[str, Any]) -> bool:
    if employer.get("careers_url"):
        return True
    for metadata in (employer.get("seed_metadata") or {}).values():
        if isinstance(metadata, dict) and metadata.get("domain_hints"):
            return True
    return False


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _provider_family(label: str) -> str | None:
    return PROVIDER_ALIASES.get(normalize_name(label))


def audit(
    universe: dict[str, Any],
    employer_rows: list[dict[str, str]],
    board_rows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    identities = _identity_index(universe)
    verified_host_rows = [
        row for row in employer_rows
        if str(row.get("verified", "")).casefold() == "true"
        and str(row.get("apply_host", "")).strip()
    ]

    enrichments: list[dict[str, Any]] = []
    new_employers: list[dict[str, Any]] = []
    matched_verified_hosts = 0

    for row in verified_host_rows:
        employer = identities.get(normalize_name(row.get("name", "")))
        item = {
            "name": row.get("name", ""),
            "ats_system": row.get("ats_system", ""),
            "apply_host": row.get("apply_host", ""),
            "checked_at": row.get("checked_at", ""),
            "evidence_method": row.get("evidence_method", ""),
        }
        if employer is not None:
            matched_verified_hosts += 1
            if not _has_domain_hint(employer):
                enrichments.append({
                    **item,
                    "employer_id": employer.get("id"),
                    "current_name": employer.get("name"),
                })
        else:
            new_employers.append(item)

    provider_counts = Counter(
        str(row.get("ats_system", "")).strip()
        for row in verified_host_rows
        if str(row.get("ats_system", "")).strip()
    )
    unsupported_provider_counts: dict[str, int] = {}
    for label, count in sorted(provider_counts.items(), key=lambda pair: (-pair[1], pair[0].casefold())):
        family = _provider_family(label)
        if family is None or family not in SUPPORTED_FAMILIES:
            unsupported_provider_counts[label] = count

    board_platform_counts: dict[str, int] = {}
    if board_rows is not None:
        board_platform_counts = dict(sorted(
            Counter(
                str(row.get("ats_platform", "")).strip()
                for row in board_rows
                if str(row.get("ats_platform", "")).strip()
            ).items(),
            key=lambda pair: (-pair[1], pair[0].casefold()),
        ))

    return {
        "schema_version": 1,
        "mode": "read_only_external_seed_audit",
        "universe": {
            "employer_count": len(universe.get("employers", [])),
        },
        "authoritative_employer_dataset": {
            "row_count": len(employer_rows),
            "verified_host_rows": len(verified_host_rows),
            "matched_verified_host_rows": matched_verified_hosts,
            "existing_employer_enrichments": len(enrichments),
            "verified_host_new_employer_candidates": len(new_employers),
        },
        "existing_employer_enrichments": sorted(enrichments, key=lambda row: row["current_name"].casefold()),
        "verified_host_new_employer_candidates": sorted(new_employers, key=lambda row: row["name"].casefold()),
        "provider_gap_counts": unsupported_provider_counts,
        "board_dataset": {
            "row_count": len(board_rows or []),
            "platform_counts": board_platform_counts,
            "identity_policy": (
                "URL-only board rows are evidence only. They never create employer identities "
                "because the dataset has no authoritative company field."
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    dataset = report["authoritative_employer_dataset"]
    lines = [
        "# External employer seed audit",
        "",
        "Read-only audit. No production employer records are changed.",
        "",
        "## Summary",
        "",
        f"- Current employer universe: **{report['universe']['employer_count']}**",
        f"- Authoritative employer dataset rows: **{dataset['row_count']}**",
        f"- Verified rows with apply hosts: **{dataset['verified_host_rows']}**",
        f"- Verified-host rows matching existing employers: **{dataset['matched_verified_host_rows']}**",
        f"- Existing employers that can gain a verified host: **{dataset['existing_employer_enrichments']}**",
        f"- Verified-host rows that are candidate new employers: **{dataset['verified_host_new_employer_candidates']}**",
        f"- URL-only ATS board rows inspected: **{report['board_dataset']['row_count']}**",
        "",
        "## Provider-family gaps",
        "",
    ]
    gaps = report["provider_gap_counts"]
    if gaps:
        lines.extend(f"- {provider}: {count}" for provider, count in gaps.items())
    else:
        lines.append("- None in the authoritative verified-host subset.")
    lines.extend([
        "",
        "## Confidence boundary",
        "",
        report["board_dataset"]["identity_policy"],
        "",
        "The authoritative employer dataset can propose new employer identities only when the row is "
        "verified and publishes an apply host. Those rows are still audit candidates; this script does "
        "not write them into the production universe.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("universe")
    parser.add_argument("employer_dataset")
    parser.add_argument("--board-dataset")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    universe = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    employer_rows = _read_csv(args.employer_dataset)
    board_rows = _read_csv(args.board_dataset) if args.board_dataset else None
    report = audit(universe, employer_rows, board_rows)

    output = json.dumps(report, indent=2) + "\n"
    if args.json_output:
        Path(args.json_output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")

    if args.markdown_output:
        Path(args.markdown_output).write_text(render_markdown(report) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
