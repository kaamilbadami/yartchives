#!/usr/bin/env python3
"""Validate and summarize an independent coverage benchmark before comparison."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DISCOVERY_KINDS = {"discovery_surface"}
AUTHORITATIVE_KINDS = {"authoritative"}
REQUIRED_ROW_FIELDS = ("company", "title", "location", "url", "source", "expected_state")
ATS_HINTS = {
    "workday": ("myworkdayjobs.com",),
    "greenhouse": ("greenhouse.io",),
    "icims": ("icims.com",),
    "ashby": ("ashbyhq.com",),
    "lever": ("lever.co",),
    "oracle": ("oraclecloud.com",),
    "eightfold": ("eightfold.ai",),
}


def _host(url: str) -> str:
    return urlparse(str(url or "")).netloc.lower().removeprefix("www.")


def _city(location: str) -> str:
    return str(location or "").split(",", 1)[0].strip() or "unknown"


def _ats(url: str) -> str:
    hostname = _host(url)
    for family, hints in ATS_HINTS.items():
        if any(hostname == hint or hostname.endswith(f".{hint}") for hint in hints):
            return family
    return "employer/custom" if hostname else "unknown"


def _counts(rows: list[dict[str, Any]], field: str, fallback: str = "unknown") -> Counter[str]:
    return Counter(str(row.get(field) or fallback) for row in rows)


def _distribution(counts: Counter[str], total: int) -> dict[str, dict[str, Any]]:
    return {
        key: {"count": count, "share": round(count / total, 4) if total else None}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    }


def _top_share(counts: Counter[str], total: int) -> float:
    return max(counts.values(), default=0) / total if total else 0.0


def analyze(document: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in document.get("discoveries", []) if isinstance(row, dict)]
    total = len(rows)
    states = _counts(rows, "expected_state")
    sources = _counts(rows, "source")
    employers = _counts(rows, "company")
    cities = Counter(_city(row.get("location")) for row in rows)
    ats = Counter(_ats(row.get("url")) for row in rows)
    kinds = _counts(rows, "url_kind")
    authoritative = sum(kinds[kind] for kind in AUTHORITATIVE_KINDS)
    discovery_only = sum(kinds[kind] for kind in DISCOVERY_KINDS)
    authoritative_search = kinds["authoritative_search"]
    explicit_provenance = sum(bool(row.get("discovery_url")) for row in rows)

    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(document.get("discoveries"), list):
        errors.append("discoveries must be a list")
    for index, row in enumerate(rows, 1):
        missing = [field for field in REQUIRED_ROW_FIELDS if not row.get(field)]
        if missing:
            errors.append(f"row {index} missing required fields: {', '.join(missing)}")
        if row.get("url_kind") not in AUTHORITATIVE_KINDS | DISCOVERY_KINDS | {"authoritative_search"}:
            errors.append(f"row {index} has unsupported url_kind")
        if not row.get("discovery_url"):
            warnings.append(f"row {index} lacks an explicit discovery_url")

    declared_states = [str(value).upper() for value in (document.get("scope", {}).get("states") or [])]
    missing_states = sorted(set(declared_states) - set(states))
    unexpected_states = sorted(set(states) - set(declared_states))
    if missing_states:
        errors.append(f"declared states without rows: {', '.join(missing_states)}")
    if unexpected_states:
        errors.append(f"row states outside declared scope: {', '.join(unexpected_states)}")

    method = document.get("sampling_method") or {}
    constraints = method.get("quality_constraints") or {}
    checks = {
        "minimum_sample_size": (total, constraints.get("minimum_sample_size"), ">="),
        "minimum_per_state": (min(states.values(), default=0), constraints.get("minimum_per_state"), ">="),
        "maximum_state_share": (_top_share(states, total), constraints.get("maximum_state_share"), "<="),
        "maximum_discovery_source_share": (_top_share(sources, total), constraints.get("maximum_discovery_source_share"), "<="),
        "maximum_employer_share": (_top_share(employers, total), constraints.get("maximum_employer_share"), "<="),
        "maximum_city_share": (_top_share(cities, total), constraints.get("maximum_city_share"), "<="),
        "minimum_authoritative_url_rate": (authoritative / total if total else 0.0, constraints.get("minimum_authoritative_url_rate"), ">="),
        "minimum_explicit_discovery_provenance_rate": (explicit_provenance / total if total else 0.0, constraints.get("minimum_explicit_discovery_provenance_rate"), ">="),
    }
    check_results = {}
    for name, (actual, threshold, operator) in checks.items():
        passed = True if threshold is None else (actual >= threshold if operator == ">=" else actual <= threshold)
        check_results[name] = {"actual": round(actual, 4), "threshold": threshold, "operator": operator, "passed": passed}
        if not passed:
            errors.append(f"{name} failed: {actual:.4f} {operator} {threshold}")

    if method and method.get("selection_independent_of_yartchives") is not True:
        errors.append("sampling_method must affirm selection_independent_of_yartchives")
    if not document.get("benchmark_fixed_at"):
        warnings.append("benchmark_fixed_at is not recorded")

    return {
        "schema_version": 1,
        "name": document.get("name"),
        "sample_size": total,
        "scope_states": declared_states,
        "state_distribution": _distribution(states, total),
        "discovery_source_distribution": _distribution(sources, total),
        "employer_distribution": _distribution(employers, total),
        "city_distribution": _distribution(cities, total),
        "ats_distribution": _distribution(ats, total),
        "url_counts": {
            "authoritative": authoritative,
            "authoritative_search": authoritative_search,
            "discovery_surface": discovery_only,
            "unknown": total - authoritative - authoritative_search - discovery_only,
        },
        "authoritative_url_rate": round(authoritative / total, 4) if total else None,
        "explicit_discovery_provenance": {
            "count": explicit_provenance,
            "rate": round(explicit_provenance / total, 4) if total else None,
        },
        "concentration": {
            "largest_state_share": round(_top_share(states, total), 4),
            "largest_discovery_source_share": round(_top_share(sources, total), 4),
            "largest_employer_share": round(_top_share(employers, total), 4),
            "largest_city_share": round(_top_share(cities, total), 4),
            "largest_ats_share": round(_top_share(ats, total), 4),
        },
        "checks": check_results,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def markdown(report: dict[str, Any]) -> str:
    url_counts = report["url_counts"]
    lines = [
        f"# Benchmark quality: {report.get('name') or 'unnamed benchmark'}",
        "",
        f"- Sample size: **{report['sample_size']}**",
        f"- Direct authoritative URLs: **{url_counts['authoritative']}** ({report['authoritative_url_rate']:.1%})",
        f"- Authoritative search/program URLs: **{url_counts['authoritative_search']}**",
        f"- Discovery-surface URLs: **{url_counts['discovery_surface']}**",
        f"- Explicit discovery URLs: **{report['explicit_discovery_provenance']['count']}** ({report['explicit_discovery_provenance']['rate']:.1%})",
        f"- Validation: **{'PASS' if report['valid'] else 'FAIL'}**",
        "",
        "## State distribution",
        "",
    ]
    lines.extend(f"- `{key}`: **{value['count']}** ({value['share']:.1%})" for key, value in report["state_distribution"].items())
    lines += ["", "## Discovery-source distribution", ""]
    lines.extend(f"- `{key}`: **{value['count']}** ({value['share']:.1%})" for key, value in report["discovery_source_distribution"].items())
    lines += ["", "## Employer concentration", ""]
    for key, value in list(report["employer_distribution"].items())[:10]:
        lines.append(f"- `{key}`: **{value['count']}** ({value['share']:.1%})")
    lines += ["", "## Concentration checks", ""]
    for name, result in report["checks"].items():
        threshold = "not set" if result["threshold"] is None else f"{result['operator']} {result['threshold']}"
        lines.append(f"- `{'PASS' if result['passed'] else 'FAIL'}` {name}: {result['actual']} ({threshold})")
    if report["errors"]:
        lines += ["", "## Errors", ""] + [f"- {value}" for value in report["errors"]]
    if report["warnings"]:
        lines += ["", "## Provenance warnings", "", f"- {len(report['warnings'])} rows lack ideal metadata; see JSON output for row-level details."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    parser.add_argument("--require-valid", action="store_true")
    args = parser.parse_args()
    document = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    report = analyze(document)
    rendered = markdown(report)
    print(rendered, end="")
    if args.json_output:
        target = Path(args.json_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown_output:
        target = Path(args.markdown_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    return 1 if args.require_valid and not report["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
