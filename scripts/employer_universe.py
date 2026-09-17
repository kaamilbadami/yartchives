#!/usr/bin/env python3
"""Build and validate a persistent employer universe from independent seed sets."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
IDENTITY_FIELDS = {"id", "name", "aliases", "seed_sets", "seed_metadata"}


def normalize_name(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def employer_id(name: str) -> str:
    return normalize_name(name).replace(" ", "-")


def _seed_metadata(employer: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic source-specific metadata without identity fields."""
    return {
        key: json.loads(json.dumps(employer[key]))
        for key in sorted(employer)
        if key not in IDENTITY_FIELDS
    }


def validate_seed(seed: dict[str, Any]) -> None:
    if seed.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported seed schema_version")
    source = seed.get("source") or {}
    if not source.get("key") or not source.get("kind"):
        raise ValueError("seed source requires key and kind")
    employers = seed.get("employers")
    if not isinstance(employers, list):
        raise ValueError("seed employers must be a list")
    seen: set[str] = set()
    for employer in employers:
        name = str((employer or {}).get("name") or "").strip()
        if not name:
            raise ValueError("seed employer requires name")
        key = normalize_name(name)
        if key in seen:
            raise ValueError(f"duplicate employer in seed: {name}")
        seen.add(key)


def merge_seed(universe: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    validate_seed(seed)
    result = json.loads(json.dumps(universe))
    result.setdefault("schema_version", SCHEMA_VERSION)
    result.setdefault("seed_sets", [])
    result.setdefault("employers", [])

    source = dict(seed["source"])
    source_key = source["key"]
    existing_sources = {item["key"]: item for item in result["seed_sets"]}
    existing_sources[source_key] = source
    result["seed_sets"] = [existing_sources[key] for key in sorted(existing_sources)]

    by_identity: dict[str, dict[str, Any]] = {}
    for employer in result["employers"]:
        names = [employer.get("name", ""), *(employer.get("aliases") or [])]
        for name in names:
            if name:
                by_identity[normalize_name(name)] = employer

    for incoming in seed["employers"]:
        name = incoming["name"].strip()
        aliases = [str(alias).strip() for alias in incoming.get("aliases", []) if str(alias).strip()]
        match = None
        for candidate in [name, *aliases]:
            match = by_identity.get(normalize_name(candidate))
            if match:
                break
        if match is None:
            match = {
                "id": employer_id(name),
                "name": name,
                "aliases": [],
                "seed_sets": [],
            }
            result["employers"].append(match)
        merged_aliases = {*(match.get("aliases") or [])}
        for alias in aliases:
            if normalize_name(alias) != normalize_name(match["name"]):
                merged_aliases.add(alias)
        match["aliases"] = sorted(merged_aliases, key=str.casefold)
        match["seed_sets"] = sorted({*(match.get("seed_sets") or []), source_key})

        metadata = _seed_metadata(incoming)
        seed_metadata = dict(match.get("seed_metadata") or {})
        if metadata:
            seed_metadata[source_key] = metadata
        else:
            seed_metadata.pop(source_key, None)
        if seed_metadata:
            match["seed_metadata"] = {key: seed_metadata[key] for key in sorted(seed_metadata)}
        else:
            match.pop("seed_metadata", None)

        by_identity[normalize_name(match["name"])] = match
        for alias in match["aliases"]:
            by_identity[normalize_name(alias)] = match

    result["employers"] = sorted(result["employers"], key=lambda item: item["id"])
    validate_universe(result)
    return result


def validate_universe(universe: dict[str, Any]) -> None:
    if universe.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported universe schema_version")
    seed_keys = [item.get("key") for item in universe.get("seed_sets", [])]
    if any(not key for key in seed_keys) or len(seed_keys) != len(set(seed_keys)):
        raise ValueError("seed_sets require unique keys")
    known_seed_keys = set(seed_keys)
    employer_ids: set[str] = set()
    identities: set[str] = set()
    for employer in universe.get("employers", []):
        employer_key = employer.get("id")
        name = str(employer.get("name") or "").strip()
        if not employer_key or not name:
            raise ValueError("employers require id and name")
        if employer_key in employer_ids:
            raise ValueError(f"duplicate employer id: {employer_key}")
        employer_ids.add(employer_key)
        for value in [name, *(employer.get("aliases") or [])]:
            normalized = normalize_name(value)
            if normalized in identities:
                raise ValueError(f"duplicate employer identity: {value}")
            identities.add(normalized)
        employer_seed_keys = set(employer.get("seed_sets") or [])
        unknown = employer_seed_keys - known_seed_keys
        if unknown:
            raise ValueError(f"unknown seed set(s): {sorted(unknown)}")
        seed_metadata = employer.get("seed_metadata") or {}
        if not isinstance(seed_metadata, dict):
            raise ValueError("seed_metadata must be an object")
        unknown_metadata = set(seed_metadata) - employer_seed_keys
        if unknown_metadata:
            raise ValueError(f"seed_metadata references unknown employer seed set(s): {sorted(unknown_metadata)}")
        if any(not isinstance(value, dict) for value in seed_metadata.values()):
            raise ValueError("seed_metadata values must be objects")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("universe")
    parser.add_argument("seed", nargs="*")
    parser.add_argument("--output")
    args = parser.parse_args()

    universe_path = Path(args.universe)
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    validate_universe(universe)
    for seed_path in args.seed:
        seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
        universe = merge_seed(universe, seed)

    output = json.dumps(universe, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
