#!/usr/bin/env python3
"""Refresh the persistent employer universe from independent coverage benchmarks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from employer_seed_from_benchmark import build_seed
from employer_universe import merge_seed, validate_universe


def refresh_universe(universe: dict, benchmarks: list[dict]) -> dict:
    result = json.loads(json.dumps(universe))
    validate_universe(result)
    for benchmark in benchmarks:
        result = merge_seed(result, build_seed(benchmark))
    validate_universe(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("universe")
    parser.add_argument("benchmark", nargs="+")
    parser.add_argument("--output")
    args = parser.parse_args()

    universe_path = Path(args.universe)
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    benchmarks = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.benchmark]
    refreshed = refresh_universe(universe, benchmarks)

    output = json.dumps(refreshed, indent=2) + "\n"
    output_path = Path(args.output) if args.output else universe_path
    output_path.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
