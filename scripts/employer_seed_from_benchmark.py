#!/usr/bin/env python3
"""Derive an employer-universe seed from an independent coverage benchmark."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from employer_universe import normalize_name


EXCLUDED_DISCOVERY_HOSTS = {
    "indeed.com",
    "www.indeed.com",
    "linkedin.com",
    "www.linkedin.com",
    "internships.com",
    "www.internships.com",
}


def _host(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").casefold()
    except ValueError:
        return None
    if not host or host in EXCLUDED_DISCOVERY_HOSTS:
        return None
    return host.removeprefix("www.")


def build_seed(benchmark: dict[str, Any], source_key: str | None = None) -> dict[str, Any]:
    discoveries = benchmark.get("discoveries")
    if not isinstance(discoveries, list):
        raise ValueError("benchmark discoveries must be a list")

    scope = benchmark.get("scope") or {}
    scope_states = sorted({str(state).strip().upper() for state in scope.get("states", []) if str(state).strip()})
    collected_at = str(benchmark.get("collected_at") or "").strip() or None
    key = source_key or f"coverage-benchmark-{(collected_at or 'undated')[:10]}"

    grouped: dict[str, dict[str, Any]] = {}
    aliases: dict[str, set[str]] = defaultdict(set)
    for row in discoveries:
        company = str((row or {}).get("company") or "").strip()
        if not company:
            continue
        identity = normalize_name(company)
        item = grouped.setdefault(
            identity,
            {
                "name": company,
                "states": set(),
                "domain_hints": set(),
                "evidence_count": 0,
                "authoritative_evidence_count": 0,
            },
        )
        if company != item["name"]:
            aliases[identity].add(company)
        state = str((row or {}).get("expected_state") or "").strip().upper()
        if state:
            item["states"].add(state)
        item["evidence_count"] += 1
        if (row or {}).get("url_kind") == "authoritative":
            item["authoritative_evidence_count"] += 1
            host = _host(str((row or {}).get("url") or ""))
            if host:
                item["domain_hints"].add(host)

    employers = []
    for identity in sorted(grouped):
        item = grouped[identity]
        employer: dict[str, Any] = {
            "name": item["name"],
            "states": sorted(item["states"]),
            "evidence_count": item["evidence_count"],
            "authoritative_evidence_count": item["authoritative_evidence_count"],
        }
        if aliases[identity]:
            employer["aliases"] = sorted(aliases[identity], key=str.casefold)
        if item["domain_hints"]:
            employer["domain_hints"] = sorted(item["domain_hints"])
        employers.append(employer)

    return {
        "schema_version": 1,
        "source": {
            "key": key,
            "kind": "coverage_benchmark",
            "name": benchmark.get("name") or key,
            "collected_at": collected_at,
            "states": scope_states,
        },
        "employers": employers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark")
    parser.add_argument("--output")
    parser.add_argument("--source-key")
    args = parser.parse_args()

    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    seed = build_seed(benchmark, source_key=args.source_key)
    output = json.dumps(seed, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
