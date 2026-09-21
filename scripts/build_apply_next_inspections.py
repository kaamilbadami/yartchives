#!/usr/bin/env python3
"""Build the browser-facing Apply Next inspection artifact.

The authoritative inspection cache intentionally retains full posting descriptions
for offline re-normalization and audits. The browser does not need those bodies to
rank or explain recommendations, so publishing the full cache makes Apply Next pay
an avoidable multi-megabyte transfer/JSON-parse cost.

This projection preserves the inspection fields consumed by the frontend while
removing heavyweight posting text.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


def project_inspection(inspection: Any) -> Any:
    if not isinstance(inspection, dict):
        return inspection
    out = copy.deepcopy(inspection)
    posting = out.get("posting")
    if isinstance(posting, dict):
        posting.pop("description", None)
        posting.pop("description_html", None)
        posting.pop("raw_description", None)
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
