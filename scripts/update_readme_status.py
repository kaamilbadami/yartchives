#!/usr/bin/env python3
"""Refresh the generated status block in README.md from checked-in feed data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

START = "<!-- yartchives-status:start -->"
END = "<!-- yartchives-status:end -->"


def listing_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("listings", "jobs", "opportunities"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    raise ValueError("feed must be a list or contain a listings/jobs/opportunities list")


def source_label(row: dict[str, Any]) -> str | None:
    for key in ("source", "source_name", "sourceName", "provider"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    provenance = row.get("provenance")
    if isinstance(provenance, dict):
        for key in ("source", "source_name", "provider"):
            value = provenance.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def render_status(rows: list[dict[str, Any]]) -> str:
    sources = sorted({label for row in rows if (label := source_label(row))})
    return "\n".join(
        [
            START,
            "- **Beta scope:** CS-first",
            "- **Feed refresh:** hourly GitHub Actions pipeline",
            f"- **Published listings:** {len(rows):,}",
            f"- **Distinct source labels:** {len(sources):,}",
            "- **Coverage claim:** not yet certified as a complete single discovery source",
            END,
        ]
    )


def replace_status(readme: str, status: str) -> str:
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain exactly one generated status marker pair")
    start = readme.index(START)
    end = readme.index(END, start) + len(END)
    return readme[:start] + status + readme[end:]


def update_readme(readme_path: Path, feed_path: Path) -> bool:
    payload = json.loads(feed_path.read_text(encoding="utf-8"))
    rows = listing_rows(payload)
    original = readme_path.read_text(encoding="utf-8")
    updated = replace_status(original, render_status(rows))
    if updated == original:
        return False
    readme_path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--feed", type=Path, default=Path("data/listings.json"))
    args = parser.parse_args()
    changed = update_readme(args.readme, args.feed)
    print("README status updated." if changed else "README status already current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
