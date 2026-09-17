#!/usr/bin/env python3
"""Re-normalize cached authoritative requirements when extractor semantics change.

This migration is request-free when an inspected posting retains its authoritative
full description. If a stale cached inspection cannot be reprocessed locally, it
is marked for the normal bounded ATS refresh queue instead of continuing to expose
requirements extracted with older semantics.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from posting_requirements import EXTRACTOR_VERSION, extract_requirements, normalize_description

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data" / "workday-inspections.json"


def migrate_entry(entry: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return (entry, state): current, migrated, invalidated, or ignored."""

    out = copy.deepcopy(entry)
    inspection = out.get("inspection")
    if not isinstance(inspection, dict) or inspection.get("status") != "inspected":
        return out, "ignored"
    if out.get("requirements_extractor_version") == EXTRACTOR_VERSION:
        return out, "current"

    posting = inspection.get("posting")
    description = posting.get("description") if isinstance(posting, dict) else None
    if isinstance(description, str) and description.strip():
        normalized, lines = normalize_description(description)
        posting["description"] = normalized or description
        inspection["requirements"] = extract_requirements(lines)
        out["requirements_extractor_version"] = EXTRACTOR_VERSION
        return out, "migrated"

    message = (
        f"Cached inspection needs requirement extractor v{EXTRACTOR_VERSION} "
        "but has no authoritative description to reprocess"
    )
    inspection["status"] = "stale_requirements"
    inspection["error"] = message
    out["last_success_at"] = None
    out["last_attempted_at"] = None
    out["last_error"] = message
    out.pop("requirements_extractor_version", None)
    return out, "invalidated"


def migrate_cache(cache: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    out = copy.deepcopy(cache) if isinstance(cache, dict) else {}
    entries = out.get("entries")
    if not isinstance(entries, dict):
        out["entries"] = {}
        entries = out["entries"]

    stats = {"current": 0, "migrated": 0, "invalidated": 0, "ignored": 0}
    for key, entry in list(entries.items()):
        if not isinstance(entry, dict):
            stats["ignored"] += 1
            continue
        migrated, state = migrate_entry(entry)
        entries[key] = migrated
        stats[state] += 1
    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", nargs="?", default=str(DEFAULT_CACHE))
    args = parser.parse_args()
    path = Path(args.cache)
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read inspection cache: {exc}") from exc

    migrated, stats = migrate_cache(cache)
    if migrated != cache:
        path.write_text(json.dumps(migrated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "Requirement cache migration: "
        + ", ".join(f"{key}={value}" for key, value in stats.items())
        + f", extractor_version={EXTRACTOR_VERSION}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
