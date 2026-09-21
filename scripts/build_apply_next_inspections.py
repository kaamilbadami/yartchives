#!/usr/bin/env python3
"""Build the browser-facing Apply Next inspection artifact.

The durable inspection cache intentionally keeps audit/provenance metadata and
full normalized posting data. Apply Next only needs a narrow ranking/presentation
contract, so project that contract explicitly before publishing to the browser.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

POSTING_FIELDS = (
    "posted_at",
    "application_status",
    "title",
    "requisition_id",
    "locations",
)

SCHEDULE_FIELDS = (
    "terms",
    "duration_evidence",
    "date_range_evidence",
)

REQUIREMENT_FIELDS = (
    "graduation",
    "citizenship",
    "work_authorization",
    "education",
    "student_status",
    "major_fields",
    "skills",
)

EVIDENCE_BUCKETS = ("required", "preferred", "not_required")


def project_fact(fact: Any) -> dict[str, Any] | None:
    if not isinstance(fact, dict):
        return None
    out: dict[str, Any] = {}
    if "statement" in fact:
        out["statement"] = fact.get("statement")
    technologies = fact.get("technologies")
    if isinstance(technologies, list) and technologies:
        out["technologies"] = technologies
    return out or None


def project_requirement(field: Any) -> dict[str, Any] | None:
    if not isinstance(field, dict):
        return None
    out: dict[str, Any] = {}
    for bucket in EVIDENCE_BUCKETS:
        values = field.get(bucket)
        if not isinstance(values, list):
            continue
        projected = [item for value in values if (item := project_fact(value)) is not None]
        if projected:
            out[bucket] = projected
    return out or None


def project_inspection(inspection: Any) -> Any:
    if not isinstance(inspection, dict):
        return inspection

    out: dict[str, Any] = {}
    if "status" in inspection:
        out["status"] = inspection.get("status")

    posting = inspection.get("posting")
    if isinstance(posting, dict):
        projected_posting = {
            key: posting.get(key)
            for key in POSTING_FIELDS
            if key in posting and posting.get(key) is not None
        }
        if projected_posting:
            out["posting"] = projected_posting

    schedule = inspection.get("schedule")
    if isinstance(schedule, dict):
        projected_schedule = {
            key: schedule.get(key)
            for key in SCHEDULE_FIELDS
            if isinstance(schedule.get(key), list) and schedule.get(key)
        }
        if projected_schedule:
            out["schedule"] = projected_schedule

    requirements = inspection.get("requirements")
    if isinstance(requirements, dict):
        projected_requirements: dict[str, Any] = {}
        for key in REQUIREMENT_FIELDS:
            projected = project_requirement(requirements.get(key))
            if projected:
                projected_requirements[key] = projected
        if projected_requirements:
            out["requirements"] = projected_requirements

    return out


def build_frontend_artifact(cache: dict[str, Any]) -> dict[str, Any]:
    entries = cache.get("entries") if isinstance(cache.get("entries"), dict) else {}
    compact_entries: dict[str, Any] = {}

    for canonical, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        compact_entry: dict[str, Any] = {}
        if "provider" in entry:
            compact_entry["provider"] = entry.get("provider")
        if "inspection" in entry:
            compact_entry["inspection"] = project_inspection(entry.get("inspection"))
        compact_entries[str(canonical)] = compact_entry

    listing_index = cache.get("listing_index")
    if not isinstance(listing_index, dict):
        listing_index = {}

    return {
        "version": cache.get("version") or 1,
        "updated_at": cache.get("updated_at"),
        "priority_term": cache.get("priority_term"),
        "entries": compact_entries,
        "listing_index": listing_index,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    cache = json.loads(args.input.read_text(encoding="utf-8"))
    artifact = build_frontend_artifact(cache if isinstance(cache, dict) else {})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
