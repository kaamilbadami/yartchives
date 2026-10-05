#!/usr/bin/env python3
"""Produce machine-readable, evidence-backed coverage-gap candidates."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.provider_fingerprint import fingerprint_provider
except ModuleNotFoundError:
    from provider_fingerprint import fingerprint_provider

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIVERSE = ROOT / "employer_universe.json"
MIN_ATS_GAP = 1
MIN_UNKNOWN_GAP = 10

ATS_RESOURCES = {
    "workday": "ats-workday",
    "greenhouse": "ats-greenhouse",
    "lever": "ats-lever",
    "oracle": "ats-oracle",
    "icims": "ats-icims",
    "smartrecruiters": "ats-smartrecruiters",
    "ashby": "ats-ashby",
    "successfactors": "ats-successfactors",
    "eightfold": "ats-eightfold",
    "avature": "ats-avature",
    "phenom": "ats-phenom",
    "brassring": "ats-brassring",
    "beamery": "ats-beamery",
    "jobvite": "ats-jobvite",
    "paylocity": "ats-paylocity",
    "breezy": "ats-breezy",
    "workable": "ats-workable",
    "applytojob": "ats-applytojob",
    "paradox": "ats-paradox",
}


def _benchmark_employers(universe: dict[str, Any]) -> list[dict[str, Any]]:
    employers = universe.get("employers", [])
    seeded = [
        employer
        for employer in employers
        if any(
            "benchmark" in seed.lower() or "fortune" in seed.lower()
            for seed in (employer.get("seed_sets") or [])
        )
    ]
    return seeded or list(employers)


def _hint_families(employer: dict[str, Any]) -> set[str]:
    families: set[str] = set()
    provider_family = str((employer.get("provider") or {}).get("family") or "")
    if provider_family and provider_family not in {"unknown", "custom_unknown"}:
        families.add(provider_family)
    for hint in employer.get("domain_hints") or []:
        family = str(fingerprint_provider(str(hint)).get("family") or "")
        if family and family not in {"unknown", "custom_unknown"}:
            families.add(family)
    for metadata in (employer.get("seed_metadata") or {}).values():
        if not isinstance(metadata, dict):
            continue
        for hint in metadata.get("domain_hints", []) or []:
            family = str(fingerprint_provider(str(hint)).get("family") or "")
            if family and family not in {"unknown", "custom_unknown"}:
                families.add(family)
    return families


def build_gap_candidates(universe: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank generic provider-resolution gaps from the current employer universe."""
    by_family: dict[str, set[str]] = defaultdict(set)
    unknown: set[str] = set()

    for employer in _benchmark_employers(universe):
        provider = employer.get("provider") or {}
        if provider.get("status") == "resolved":
            continue
        employer_id = str(employer.get("id") or employer.get("name") or "").strip()
        if not employer_id:
            continue
        families = _hint_families(employer)
        if families:
            for family in families:
                by_family[family].add(employer_id)
        else:
            unknown.add(employer_id)

    candidates: list[dict[str, Any]] = []
    for family, employer_ids in by_family.items():
        if len(employer_ids) < MIN_ATS_GAP:
            continue
        resource = ATS_RESOURCES.get(family, f"ats-{family}")
        candidates.append(
            {
                "id": f"{resource}:provider-resolution",
                "kind": "ats-provider-resolution",
                "family": family,
                "resources": [resource],
                "affected_employers": len(employer_ids),
                "confidence": 1.0,
                "generic_leverage": 1.0,
                "score": len(employer_ids),
                "title": f"Close {family.title()} provider-resolution coverage gap",
                "evidence": (
                    f"{len(employer_ids)} benchmark employers have unresolved provider "
                    f"records but domain evidence fingerprints as {family}."
                ),
            }
        )

    if len(unknown) >= MIN_UNKNOWN_GAP:
        candidates.append(
            {
                "id": "source-registry:unknown-provider-resolution",
                "kind": "unknown-provider-resolution",
                "family": "unknown",
                "resources": ["source-registry"],
                "affected_employers": len(unknown),
                "confidence": 0.7,
                "generic_leverage": 0.8,
                "score": len(unknown) * 0.56,
                "title": "Reduce unresolved provider discovery gaps",
                "evidence": (
                    f"{len(unknown)} benchmark employers remain unresolved without a "
                    "known ATS fingerprint in their current domain hints."
                ),
            }
        )

    candidates.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["affected_employers"]),
            str(item["id"]),
        )
    )
    return candidates


def load_candidates(path: Path = DEFAULT_UNIVERSE) -> list[dict[str, Any]]:
    universe = json.loads(path.read_text(encoding="utf-8"))
    return build_gap_candidates(universe)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    args = parser.parse_args()
    print(json.dumps(load_candidates(Path(args.universe)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
