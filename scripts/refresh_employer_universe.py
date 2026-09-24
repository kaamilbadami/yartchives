#!/usr/bin/env python3
"""Refresh the persistent employer universe from deterministic generic seed inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from employer_seed_from_benchmark import build_seed as build_benchmark_seed
from employer_universe import merge_seed, validate_universe
from domain_discovery import enrich_domains


def refresh_universe(
    universe: dict,
    benchmarks: list[dict] | None = None,
    seeds: list[dict] | None = None,
    enrich_domain_hints: bool = False,
) -> dict:
    result = json.loads(json.dumps(universe))
    validate_universe(result)
    inputs = [build_benchmark_seed(benchmark, enrich_domain_hints=enrich_domain_hints) for benchmark in (benchmarks or [])]
    for seed in (seeds or []):
        s = json.loads(json.dumps(seed))
        if enrich_domain_hints:
            s = enrich_domains(s)
        inputs.append(s)
    keys = [str((seed.get("source") or {}).get("key") or "") for seed in inputs]
    if len(keys) != len(set(keys)):
        raise ValueError("refresh inputs require unique seed source keys")
    for seed in sorted(inputs, key=lambda item: item["source"]["key"]):
        result = merge_seed(result, seed)
    validate_universe(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("universe")
    parser.add_argument("benchmark", nargs="*")
    parser.add_argument("--seed", action="append", default=[], help="Generic employer seed JSON")
    parser.add_argument("--enrich-domain-hints", action="store_true", help="Auto-discover domain hints for benchmark employers without them")
    parser.add_argument("--output")
    args = parser.parse_args()

    universe_path = Path(args.universe)
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    benchmarks = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.benchmark]
    seeds = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.seed]
    if not benchmarks and not seeds:
        parser.error("at least one benchmark or --seed is required")
    try:
        refreshed = refresh_universe(universe, benchmarks, seeds, enrich_domain_hints=args.enrich_domain_hints)
    except ValueError as exc:
        parser.error(str(exc))

    output = json.dumps(refreshed, indent=2, ensure_ascii=False) + "\n"
    output_path = Path(args.output) if args.output else universe_path
    output_path.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
