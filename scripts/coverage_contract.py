#!/usr/bin/env python3
"""Evaluate whether Yartchives has earned its single-discovery-queue claim."""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "coverage_contract.json"


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def hours_between(later: datetime, earlier: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 3600)


def _gate(name: str, actual: Any, target: Any, passed: bool, measurable: bool = True) -> dict[str, Any]:
    return {"name": name, "actual": actual, "target": target, "measurable": measurable, "passed": bool(passed and measurable)}


def evaluate(contract: dict[str, Any], reports: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    gates = contract["gates"]
    results = [result for report in reports for result in (report.get("results") or [])]
    unique_total = sum(int((report.get("summary") or {}).get("external_unique_listings") or 0) for report in reports)
    captured = sum(
        result.get("status") in {"already_in_yartchives", "filtered_or_misclassified", "duplicate_resolution_issue"}
        for result in results
    )
    visible = sum(result.get("status") == "already_in_yartchives" for result in results)
    authoritative = sum(
        (result.get("matched_job") or {}).get("link_kind") == "direct"
        for result in results
        if result.get("status") in {"already_in_yartchives", "filtered_or_misclassified", "duplicate_resolution_issue"}
    )
    capture_rate = captured / unique_total if unique_total else None
    visible_rate = visible / unique_total if unique_total else None
    authoritative_rate = authoritative / captured if captured else None

    states = {
        str(state).upper()
        for report in reports
        for state in ((report.get("scope") or {}).get("states") or [])
        if state
    }
    sample_times = [parse_time((report.get("audit") or {}).get("collected_at")) for report in reports]
    sample_times = [value for value in sample_times if value]
    feed_times = [parse_time((report.get("feed") or {}).get("generated_at")) for report in reports]
    feed_times = [value for value in feed_times if value]
    oldest_sample_age = max((hours_between(now, value) for value in sample_times), default=None)
    oldest_feed_age = max((hours_between(now, value) for value in feed_times), default=None)

    latencies = []
    for result in results:
        discovered = parse_time(result.get("first_discovered_at"))
        first_seen = parse_time((result.get("matched_job") or {}).get("first_seen"))
        if discovered and first_seen:
            latencies.append(hours_between(first_seen, discovered))
    median_latency = statistics.median(latencies) if latencies else None

    checks = [
        _gate("benchmark_size", unique_total, gates["minimum_unique_benchmark_listings"], unique_total >= gates["minimum_unique_benchmark_listings"]),
        _gate("geographic_breadth", len(states), gates["minimum_benchmark_states"], len(states) >= gates["minimum_benchmark_states"]),
        _gate("sample_freshness_hours", oldest_sample_age, gates["maximum_sample_age_hours"], oldest_sample_age is not None and oldest_sample_age <= gates["maximum_sample_age_hours"], oldest_sample_age is not None),
        _gate("feed_freshness_hours", oldest_feed_age, gates["maximum_feed_age_hours"], oldest_feed_age is not None and oldest_feed_age <= gates["maximum_feed_age_hours"], oldest_feed_age is not None),
        _gate("capture_rate", capture_rate, gates["minimum_capture_rate"], capture_rate is not None and capture_rate >= gates["minimum_capture_rate"], capture_rate is not None),
        _gate("visible_rate", visible_rate, gates["minimum_visible_rate"], visible_rate is not None and visible_rate >= gates["minimum_visible_rate"], visible_rate is not None),
        _gate("authoritative_link_rate", authoritative_rate, gates["minimum_authoritative_link_rate"], authoritative_rate is not None and authoritative_rate >= gates["minimum_authoritative_link_rate"], authoritative_rate is not None),
        _gate(
            "median_discovery_latency_hours",
            median_latency,
            gates["maximum_median_discovery_latency_hours"],
            median_latency is not None and median_latency <= gates["maximum_median_discovery_latency_hours"],
            median_latency is not None or not gates.get("require_latency_measurement", True),
        ),
    ]
    ready = all(check["passed"] for check in checks)
    return {
        "schema_version": 1,
        "contract": contract["name"],
        "promise": contract["promise"],
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "status": "ready_as_only_source" if ready else "not_ready_as_only_source",
        "ready": ready,
        "checks": checks,
        "evidence": {
            "reports": len(reports),
            "unique_benchmark_listings": unique_total,
            "states": sorted(states),
            "latency_observations": len(latencies),
        },
    }


def markdown(status: dict[str, Any]) -> str:
    lines = [
        "# Yartchives coverage contract status", "",
        f"**Status: `{status['status']}`**", "",
        status["promise"], "",
        "| Gate | Actual | Required | Measurable | Pass |", "|---|---:|---:|:---:|:---:|",
    ]
    for check in status["checks"]:
        actual = "N/A" if check["actual"] is None else check["actual"]
        lines.append(f"| {check['name']} | {actual} | {check['target']} | {'yes' if check['measurable'] else 'no'} | {'yes' if check['passed'] else 'no'} |")
    if not status["ready"]:
        lines.extend(["", "Yartchives has not earned the claim that it can replace all other discovery sources. Failed or unmeasured gates are the prioritized coverage work queue."])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.reports]
    status = evaluate(contract, reports, datetime.now(timezone.utc))
    rendered = markdown(status)
    print(rendered, end="")
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(rendered, encoding="utf-8")
    return 1 if args.require_ready and not status["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
