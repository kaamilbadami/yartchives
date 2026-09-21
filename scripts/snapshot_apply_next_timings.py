#!/usr/bin/env python3
"""Build a bounded, privacy-safe Apply Next timing snapshot from Formspree submissions."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

ALLOWED_STAGES = (
    "paint_wait",
    "candidate_artifact",
    "candidate_filter",
    "inspection_artifact",
    "inspection_attach",
    "location_enrichment",
    "ranking",
    "render",
)
ALLOWED_COUNTS = ("candidates", "rankable", "recommendations")


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value or value[0] not in "[{":
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _timing_rows(submission: dict[str, Any]) -> list[dict[str, Any]]:
    if submission.get("schema") != "yartchives-usage-v2":
        return []
    raw = _json_value(submission.get("timings"))
    return raw if isinstance(raw, list) else []


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def sanitize_timing(timing: dict[str, Any], *, build: str, received_at: str) -> dict[str, Any] | None:
    total = _finite_number(timing.get("total_ms"))
    if total is None:
        return None

    stages: dict[str, float] = {}
    raw_stages = timing.get("stages_ms")
    if isinstance(raw_stages, dict):
        for name in ALLOWED_STAGES:
            value = _finite_number(raw_stages.get(name))
            if value is not None:
                stages[name] = round(value, 1)

    counts: dict[str, int] = {}
    raw_counts = timing.get("counts")
    if isinstance(raw_counts, dict):
        for name in ALLOWED_COUNTS:
            value = _finite_number(raw_counts.get(name))
            if value is not None:
                counts[name] = int(value)

    status = str(timing.get("status") or "success")[:20]
    return {
        "received_at": received_at,
        "build": build[:40],
        "total_ms": round(total, 1),
        "stages_ms": stages,
        "counts": counts,
        "status": status,
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 1)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = [float(row["total_ms"]) for row in rows]
    stage_values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for name, value in row.get("stages_ms", {}).items():
            stage_values[name].append(float(value))

    stages = {}
    for name in ALLOWED_STAGES:
        values = stage_values.get(name, [])
        if not values:
            continue
        stages[name] = {
            "samples": len(values),
            "median_ms": round(median(values), 1),
            "p90_ms": percentile(values, 0.9),
        }

    return {
        "samples": len(rows),
        "median_total_ms": round(median(totals), 1) if totals else None,
        "p90_total_ms": percentile(totals, 0.9),
        "stages": stages,
    }


def build_snapshot(payload: dict[str, Any], *, max_samples: int = 20) -> dict[str, Any]:
    submissions = payload.get("submissions")
    if not isinstance(submissions, list):
        submissions = []

    rows: list[dict[str, Any]] = []
    for submission in submissions:
        if not isinstance(submission, dict):
            continue
        build = str(submission.get("build") or "")
        received_at = str(submission.get("_date") or submission.get("endedAt") or "")
        for timing in _timing_rows(submission):
            if not isinstance(timing, dict):
                continue
            sanitized = sanitize_timing(timing, build=build, received_at=received_at)
            if sanitized:
                rows.append(sanitized)

    rows = rows[:max_samples]
    by_build: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_build[row["build"] or "unknown"].append(row)

    return {
        "version": 1,
        "generated_at": rows[0]["received_at"] if rows else None,
        "privacy": "aggregate timing only; visitor/session/profile/job fields omitted",
        "recent": rows,
        "summary": summarize(rows),
        "by_build": {build: summarize(items) for build, items in sorted(by_build.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-samples", type=int, default=20)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    snapshot = build_snapshot(payload, max_samples=max(1, min(100, args.max_samples)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
