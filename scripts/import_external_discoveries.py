#!/usr/bin/env python3
"""Import independently collected job discoveries from an external source (e.g. ChatGPT).

Validates inputs against REQUIRED_DRAFT_FIELDS from `external_discovery_benchmark.py`.
Normalizes values and merges into an existing draft CSV, preventing duplicate imports.
Keeps imported items in 'draft' mode so they are explicitly reviewed by `external_discovery_benchmark.py` rather than being treated as verified automatically.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to python path
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.external_discovery_benchmark import REQUIRED_DRAFT_FIELDS

def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
    """Normalize row to match REQUIRED_DRAFT_FIELDS with safe empty strings."""
    return {field: str(row.get(field) or "").strip() for field in REQUIRED_DRAFT_FIELDS}

def import_discoveries(input_path: Path, csv_path: Path) -> int:
    """Read a JSON or CSV file of discoveries and append new ones to the draft CSV."""

    # Read imported rows
    imported_rows: list[dict[str, str]] = []

    try:
        if input_path.suffix.lower() == ".json":
            with input_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Allow top-level list or dict with a specific key
            if isinstance(data, list):
                raw_rows = data
            elif isinstance(data, dict):
                # Try finding a list anywhere
                lists = [v for v in data.values() if isinstance(v, list)]
                if not lists:
                    print(f"Error: No list found in JSON at {input_path}", file=sys.stderr)
                    return 1
                raw_rows = lists[0]
            else:
                print(f"Error: JSON must be a list or object containing a list", file=sys.stderr)
                return 1

            for r in raw_rows:
                if not isinstance(r, dict):
                    print("Error: JSON list must contain objects", file=sys.stderr)
                    return 1
                imported_rows.append(_normalize_row(r))

        elif input_path.suffix.lower() == ".csv":
            with input_path.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    imported_rows.append(_normalize_row(r))
        else:
            print(f"Error: Input file must be .json or .csv", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error reading input {input_path}: {e}", file=sys.stderr)
        return 1

    # Validate rows
    valid_rows = []
    for idx, row in enumerate(imported_rows, 1):
        missing = [f for f in ["persona_id", "company", "title", "url"] if not row.get(f)]
        if missing:
            print(f"Row {idx} missing required fields {missing}. Skipping.")
            continue
        valid_rows.append(row)

    if not valid_rows:
        print("No valid rows found to import.")
        return 0

    # Read existing rows to deduplicate
    existing_rows: list[dict[str, str]] = []
    existing_keys = set()

    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    norm = _normalize_row(r)
                    existing_rows.append(norm)
                    # Dedupe by URL + Persona + Company (to allow multiple reqs at same company, or same req across personas)
                    key = (norm["url"], norm["persona_id"], norm["company"])
                    existing_keys.add(key)
        except Exception as e:
            print(f"Error reading existing CSV {csv_path}: {e}", file=sys.stderr)
            return 1

    # Merge
    new_rows = []
    for row in valid_rows:
        key = (row["url"], row["persona_id"], row["company"])
        if key not in existing_keys:
            new_rows.append(row)
            existing_keys.add(key)

    if not new_rows:
        print("No new discoveries to import (all were duplicates).")
        return 0

    # Write back
    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        all_rows = existing_rows + new_rows
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=REQUIRED_DRAFT_FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"Successfully imported {len(new_rows)} new discoveries into {csv_path}.")
        return 0
    except Exception as e:
        print(f"Error writing to {csv_path}: {e}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Input JSON or CSV file containing external discoveries")
    parser.add_argument("--draft-csv", type=Path, required=True, help="Path to the draft CSV file where discoveries should be imported")

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found at {args.input}", file=sys.stderr)
        return 1

    return import_discoveries(args.input, args.draft_csv)


if __name__ == "__main__":
    raise SystemExit(main())
