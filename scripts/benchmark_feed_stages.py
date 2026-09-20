#!/usr/bin/env python3
"""Benchmark opportunity-feed runtime by stage."""

import argparse
import shutil
import subprocess
import time
from pathlib import Path
import tempfile
import sys
import json

def run_stage(name: str, commands: list[list[str]]) -> float:
    print(f"Running {name}...")
    start = time.perf_counter()
    for cmd in commands:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    duration = time.perf_counter() - start
    print(f"  {duration:.2f}s")
    return duration

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, default=Path("data/listings.json"))
    parser.add_argument("--inspections", type=Path, default=Path("data/workday-inspections.json"))
    parser.add_argument("--limit", type=int, help="Limit number of jobs for faster testing")
    parser.add_argument("--output-json", type=Path, help="Write durations out to JSON")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        listings_path = temp / "listings.json"
        inspections_path = temp / "inspections.json"
        sources_path = temp / "sources.json"

        # Initialize from existing feed
        if args.limit:
             with open(args.feed, "r", encoding="utf-8") as f:
                 data = json.load(f)
             if isinstance(data, dict) and "jobs" in data and isinstance(data["jobs"], list):
                 data["jobs"] = data["jobs"][:args.limit]
             elif isinstance(data, list):
                 data = data[:args.limit]
             with open(listings_path, "w", encoding="utf-8") as f:
                 json.dump(data, f)
        else:
             shutil.copy(args.feed, listings_path)

        shutil.copy(args.inspections, inspections_path)

        # Empty sources file for parallel collection
        sources_path.write_text("[]", encoding="utf-8")

        stages = {
            "source collection": [
                ["python3", "scripts/parallel_ats_collect.py", str(listings_path), "--old-feed", str(args.feed), "--sources", str(sources_path), "--universe", "employer_universe.json"]
            ],
            "normalization": [
                ["python3", "scripts/enrich_feed.py", str(listings_path)],
                ["python3", "scripts/repair_links.py", str(listings_path), "--old-feed", str(args.feed), "--offline"],
                ["python3", "scripts/provider_links.py", str(listings_path)],
                ["python3", "scripts/jobright_links.py", str(listings_path)],
                ["python3", "scripts/source_links.py", str(listings_path)],
                ["python3", "scripts/reconcile_workday_duplicates.py", str(listings_path)],
                ["python3", "scripts/stabilize_job_ids.py", str(listings_path), "--old-feed", str(args.feed)]
            ],
            "authoritative inspection": [
                ["python3", "scripts/update_workday_inspections.py", str(listings_path), "--cache", str(inspections_path), "--max-workday-requests", "0", "--max-icims-requests", "0", "--max-greenhouse-requests", "0", "--ttl-days", "7"]
            ],
            "validation": [
                ["python3", "scripts/validate_feed.py", str(listings_path), "--minimum-jobs", "0", "--minimum-healthy-sources", "0"]
            ],
            "generated artifacts": [
                ["python3", "scripts/audit_feed.py", str(listings_path)],
                ["python3", "scripts/coverage_audit.py", "audit/samples/northeast-midatlantic-cs-2026-09-17.json", "--feed", str(listings_path)]
            ]
        }

        durations = {}
        for name, cmds in stages.items():
            durations[name] = run_stage(name, cmds)

        print("\n--- Pipeline Runtime Benchmark ---")
        for name, duration in durations.items():
            print(f"- {name.capitalize()}: {duration:.2f}s")

        total = sum(durations.values())
        print(f"\nTotal time: {total:.2f}s")
        if durations:
            dominant = max(durations, key=durations.get)
            print(f"Dominant stage: {dominant} ({durations[dominant]:.2f}s, {durations[dominant]/total*100:.1f}%)")

        if args.output_json:
            result = {
                "total": total,
                "dominant": dominant,
                "stages": durations
            }
            with open(args.output_json, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
