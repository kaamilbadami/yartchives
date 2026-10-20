#!/usr/bin/env python3
"""Import independent AI/ChatGPT discoveries into the coverage audit draft format.

Schema:
The input can be a JSON object, a JSON array, or a CSV file.
If it's a JSON object, it may optionally contain `run_id` and `collected_at` fields,
and a `discoveries` array.

Each discovery should have:
- company (required)
- title (required)
- url or authoritative_url (required)
- persona_id, persona, or scope (required)
- expected_state (required)
- location (optional)
- source (optional)
- discovery_url (optional)
- discovery_query (optional)
- collected_at (optional)
- run_id (optional)

Validates and normalizes external results, preserving provenance and rejecting malformed
or missing identifiers. Imported results are output as draft CSVs for review via
external_discovery_benchmark.py, ensuring they are not treated as verified until reviewed.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ["company", "title", "url", "persona_id", "expected_state"]
EXTRA_FIELDS = ["collected_at", "run_id"]

def validate_and_normalize(discoveries: list[dict[str, Any]], run_id: str = "", collected_at: str = "") -> list[dict[str, Any]]:
    valid = []
    seen = set()
    for idx, d in enumerate(discoveries):
        # Normalize keys
        url = str(d.get("url") or d.get("authoritative_url") or d.get("authoritative URL") or "").strip()
        persona_id = str(d.get("persona_id") or d.get("persona") or d.get("scope") or "").strip()

        norm_d = {
            "company": str(d.get("company", "")).strip(),
            "title": str(d.get("title", "")).strip(),
            "url": url,
            "persona_id": persona_id,
            "expected_state": str(d.get("expected_state", "")).strip()
        }

        # Must have basic fields
        missing = [f for f in REQUIRED_FIELDS if not norm_d[f]]
        if missing:
            print(f"Skipping malformed discovery at index {idx}: missing {', '.join(missing)}", file=sys.stderr)
            continue

        req_id = str(d.get("requisition_id", "")).strip()

        # deduplicate by company + URL or company + req_id
        # We allow multiple requisitions for the same company if the URL or req_id is different.
        dup_key = (norm_d["company"].lower(), url.lower(), req_id.lower())
        if dup_key in seen:
            print(f"Skipping duplicate discovery at index {idx}: {norm_d['company']} - {url}", file=sys.stderr)
            continue
        seen.add(dup_key)

        valid.append({
            "persona_id": persona_id,
            "company": norm_d["company"],
            "title": norm_d["title"],
            "location": str(d.get("location", "")).strip(),
            "url": url,
            "source": str(d.get("source", "ChatGPT")).strip(),
            "discovery_url": str(d.get("discovery_url", "")).strip(),
            "discovery_query": str(d.get("discovery_query", "")).strip(),
            "expected_state": norm_d["expected_state"],
            "collected_at": str(d.get("collected_at", collected_at)).strip(),
            "run_id": str(d.get("run_id", run_id)).strip()
        })
    return valid

def process_file(input_path: Path, output_csv: Path) -> None:
    content = input_path.read_text(encoding="utf-8")
    discoveries = []
    run_id = ""
    collected_at = ""

    if input_path.suffix.lower() == ".json":
        data = json.loads(content)
        if isinstance(data, dict) and "discoveries" in data:
            discoveries = data["discoveries"]
            run_id = str(data.get("run_id", ""))
            collected_at = str(data.get("collected_at", ""))
        elif isinstance(data, list):
            discoveries = data
        else:
            raise ValueError("JSON must be a list of discoveries or an object with a 'discoveries' key")
    elif input_path.suffix.lower() == ".csv":
        with input_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            discoveries = list(reader)
    else:
        raise ValueError("Unsupported file format. Must be .json or .csv")

    normalized = validate_and_normalize(discoveries, run_id, collected_at)

    if not normalized:
        print("No valid discoveries found to import.", file=sys.stderr)
        sys.exit(1)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "persona_id", "company", "title", "location", "url", "source",
            "discovery_url", "discovery_query", "expected_state",
            "collected_at", "run_id"
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(normalized)

    print(f"Successfully exported {len(normalized)} normalized discoveries to {output_csv}")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Input JSON or CSV file")
    parser.add_argument("output", type=Path, help="Output draft CSV file compatible with external_discovery_benchmark.py")

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file {args.input} not found.", file=sys.stderr)
        return 1

    try:
        process_file(args.input, args.output)
    except Exception as e:
        print(f"Error processing file: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
