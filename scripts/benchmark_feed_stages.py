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
import datetime
import os

METRICS_HISTORY_LIMIT = 30
CURRENT_RUN_METRICS = Path("/tmp/feed-metrics-current.json")
PERSISTENT_METRICS = Path("data/pipeline-metrics.json")

def run_stage(name: str, commands: list[list[str]]) -> float:
    print(f"Running {name}...")
    start = time.perf_counter()
    for cmd in commands:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    duration = time.perf_counter() - start
    print(f"  {duration:.2f}s")
    return duration

def record_stage(name: str, command: list[str]) -> int:
    start = time.perf_counter()
    print(f"Recording stage: {name}")
    print(f"Command: {' '.join(command)}")

    result = subprocess.run(command)
    duration = time.perf_counter() - start
    success = (result.returncode == 0)

    current_metrics = {}
    if CURRENT_RUN_METRICS.exists():
        try:
            with open(CURRENT_RUN_METRICS, "r", encoding="utf-8") as f:
                current_metrics = json.load(f)
        except Exception:
            pass

    stage_data = current_metrics.get(name, {"duration": 0.0, "success": True})
    stage_data["duration"] += duration
    stage_data["success"] = stage_data["success"] and success
    current_metrics[name] = stage_data

    with open(CURRENT_RUN_METRICS, "w", encoding="utf-8") as f:
        json.dump(current_metrics, f)

    return result.returncode

def finalize_metrics(output_file: Path) -> int:
    current_metrics = {}
    if CURRENT_RUN_METRICS.exists():
        try:
            with open(CURRENT_RUN_METRICS, "r", encoding="utf-8") as f:
                current_metrics = json.load(f)
        except Exception as e:
            print(f"Error reading current metrics: {e}", file=sys.stderr)

    if not current_metrics:
        print("No metrics recorded for this run.")
        return 0

    total_duration = sum(data["duration"] for data in current_metrics.values())
    dominant_stage = max(current_metrics.keys(), key=lambda k: current_metrics[k]["duration"]) if current_metrics else None

    failed_stages = [name for name, data in current_metrics.items() if not data["success"]]
    failed_stage = failed_stages[0] if failed_stages else None

    run_record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_duration": total_duration,
        "dominant_stage": dominant_stage,
        "failed_stage": failed_stage,
        "stages": current_metrics
    }

    history = []
    if output_file.exists():
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    if not isinstance(history, list):
        history = []

    history.append(run_record)

    # Keep only the last N runs
    history = history[-METRICS_HISTORY_LIMIT:]

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    print(f"Metrics finalized. Total duration: {total_duration:.2f}s")
    if failed_stage:
        print(f"Failed stage: {failed_stage}")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, default=Path("data/listings.json"))
    parser.add_argument("--inspections", type=Path, default=Path("data/workday-inspections.json"))
    parser.add_argument("--limit", type=int, help="Limit number of jobs for faster testing")
    parser.add_argument("--output-json", type=Path, help="Write durations out to JSON")

    parser.add_argument("--record", type=str, help="Record metrics for a specific stage")
    parser.add_argument("--finalize", action="store_true", help="Finalize metrics for the current run")
    parser.add_argument("--metrics-file", type=Path, default=PERSISTENT_METRICS, help="File to persist history to")

    # We use parse_known_args because we might have trailing command arguments when using --record
    args, unknown = parser.parse_known_args()

    if args.finalize:
        return finalize_metrics(args.metrics_file)

    if args.record:
        if not unknown:
            print("Error: --record requires a command to execute", file=sys.stderr)
            return 1

        # Strip the leading '--' if present in the unknown args before the command
        cmd = unknown
        if cmd[0] == '--':
            cmd = cmd[1:]

        return record_stage(args.record, cmd)

    if unknown:
        print(f"Unknown arguments: {unknown}", file=sys.stderr)
        return 1

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
            "collection": [
                ["python3", "scripts/parallel_ats_collect.py", str(listings_path), "--old-feed", str(args.feed), "--sources", str(sources_path), "--universe", "employer_universe.json"]
            ],
            "enrichment": [
                ["python3", "scripts/enrich_feed.py", str(listings_path)]
            ],
            "link repair": [
                ["python3", "scripts/repair_links.py", str(listings_path), "--old-feed", str(args.feed), "--offline"],
                ["python3", "scripts/provider_links.py", str(listings_path)],
                ["python3", "scripts/jobright_links.py", str(listings_path)],
                ["python3", "scripts/source_links.py", str(listings_path)]
            ],
            "ATS reconciliation": [
                ["python3", "scripts/reconcile_workday_duplicates.py", str(listings_path)],
                ["python3", "scripts/stabilize_job_ids.py", str(listings_path), "--old-feed", str(args.feed)]
            ],
            "authoritative inspection": [
                ["python3", "scripts/update_workday_inspections.py", str(listings_path), "--cache", str(inspections_path), "--max-workday-requests", "0", "--max-icims-requests", "0", "--max-greenhouse-requests", "0", "--ttl-days", "7"]
            ],
            "validation": [
                ["python3", "scripts/validate_feed.py", str(listings_path), "--minimum-jobs", "0", "--minimum-healthy-sources", "0"]
            ],
            "audit": [
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
