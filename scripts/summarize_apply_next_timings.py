#!/usr/bin/env python3
"""Summarize exported Yartchives Apply Next timing telemetry.

Accepts JSON, JSON arrays, JSONL, or wrapper objects containing analytics payloads.
Only timing records from the yartchives-usage-v2 schema are summarized.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "yartchives-usage-v2"


def _iter_json_values(text: str) -> Iterable[Any]:
    stripped = text.strip()
    if not stripped:
        return
    try:
        yield json.loads(stripped)
        return
    except json.JSONDecodeError:
        pass

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def extract_timings(values: Iterable[Any]) -> list[dict[str, Any]]:
    timings: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for value in values:
        for obj in _walk(value):
            if obj.get("schema") != SCHEMA:
                continue
            marker = id(obj)
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            raw_timings = obj.get("timings")
            if not isinstance(raw_timings, list):
                continue
            for timing in raw_timings:
                if not isinstance(timing, dict):
                    continue
                total = timing.get("total_ms")
                try:
                    total_ms = float(total)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(total_ms) or total_ms < 0:
                    continue
                timings.append(timing)
    return timings


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def stats(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "median_ms": round(statistics.median(values), 1) if values else None,
        "p90_ms": round(percentile(values, 0.90), 1) if values else None,
        "p95_ms": round(percentile(values, 0.95), 1) if values else None,
        "max_ms": round(max(values), 1) if values else None,
    }


def summarize(timings: list[dict[str, Any]]) -> dict[str, Any]:
    totals: list[float] = []
    stage_values: dict[str, list[float]] = {}
    successes = 0

    for timing in timings:
        total = float(timing["total_ms"])
        totals.append(total)
        if str(timing.get("status", "success")) == "success":
            successes += 1

        stages = timing.get("stages_ms")
        if not isinstance(stages, dict):
            continue
        for name, raw in stages.items():
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value) and value >= 0:
                stage_values.setdefault(str(name), []).append(value)

    stage_summary = {
        name: stats(values)
        for name, values in sorted(stage_values.items())
    }
    sample_count = len(totals)
    return {
        "schema": "yartchives-apply-next-performance-summary-v1",
        "sample_count": sample_count,
        "success_count": successes,
        "success_rate": round(successes / sample_count, 4) if sample_count else None,
        "total": stats(totals),
        "stages": stage_summary,
    }


def render_text(summary: dict[str, Any]) -> str:
    total = summary["total"]
    lines = [
        f"Apply Next performance summary ({summary['sample_count']} samples)",
        (
            "Total latency: "
            f"median {format_ms(total['median_ms'])} · "
            f"p90 {format_ms(total['p90_ms'])} · "
            f"p95 {format_ms(total['p95_ms'])} · "
            f"max {format_ms(total['max_ms'])}"
        ),
    ]
    rate = summary.get("success_rate")
    if rate is not None:
        lines.append(f"Success rate: {rate * 100:.1f}%")

    stages = summary.get("stages", {})
    if stages:
        lines.append("Stages:")
        ordered = sorted(
            stages.items(),
            key=lambda item: item[1].get("median_ms") or 0,
            reverse=True,
        )
        for name, values in ordered:
            lines.append(
                f"- {name}: median {format_ms(values['median_ms'])} · "
                f"p90 {format_ms(values['p90_ms'])} · "
                f"p95 {format_ms(values['p95_ms'])}"
            )
    return "\n".join(lines)


def format_ms(value: float | int | None) -> str:
    return "n/a" if value is None else f"{float(value):.1f} ms"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize exported Apply Next timing telemetry."
    )
    parser.add_argument("input", type=Path, help="JSON or JSONL analytics export")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args(argv)

    try:
        values = list(_iter_json_values(args.input.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    summary = summarize(extract_timings(values))
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(render_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
