#!/usr/bin/env python3
"""Fingerprint recruiting providers from resolved careers URLs and page evidence."""
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROVIDER_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("workday", ("myworkdayjobs.com", "/wday/cxs/")),
    ("greenhouse", ("greenhouse.io", "boards.greenhouse.io", "job-boards.greenhouse.io")),
    ("icims", ("icims.com",)),
    ("ashby", ("ashbyhq.com", "jobs.ashbyhq.com")),
    ("oracle", ("oraclecloud.com", "taleo.net", "eeho.fa.")),
    ("successfactors", ("successfactors.com", "successfactors.eu", "career5.successfactors")),
    ("smartrecruiters", ("smartrecruiters.com", "jobs.smartrecruiters.com")),
    ("lever", ("lever.co", "jobs.lever.co")),
    ("eightfold", ("eightfold.ai", "eightfold")),
    ("avature", ("avature.net", "avature")),
    ("phenom", ("phenompeople.com", "phenom")),
    ("brassring", ("brassring.com",)),
)


def _evidence_text(*values: str | None) -> str:
    return "\n".join(str(value or "").casefold() for value in values)


def fingerprint_provider(url: str, *, final_url: str | None = None, html: str | None = None) -> dict[str, Any]:
    """Return a deterministic provider classification from URL/page evidence."""
    evidence = _evidence_text(url, final_url, html)
    matched: list[tuple[str, str]] = []
    for provider, markers in PROVIDER_PATTERNS:
        for marker in markers:
            if marker.casefold() in evidence:
                matched.append((provider, marker))
                break

    providers = sorted({provider for provider, _ in matched})
    resolved_url = final_url or url
    host = (urlparse(resolved_url).hostname or "").casefold()

    if len(providers) == 1:
        provider = providers[0]
        marker = next(marker for candidate, marker in matched if candidate == provider)
        return {
            "family": provider,
            "status": "resolved",
            "evidence": "url_or_page_marker",
            "marker": marker,
            "host": host,
        }
    if len(providers) > 1:
        return {
            "family": "unknown",
            "status": "ambiguous",
            "evidence": "multiple_provider_markers",
            "candidates": providers,
            "host": host,
        }
    return {
        "family": "custom_unknown",
        "status": "unresolved",
        "evidence": "no_known_provider_marker",
        "host": host,
    }


def apply_observations(universe: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist careers URLs and provider fingerprints by employer id."""
    result = deepcopy(universe)
    employers = {item.get("id"): item for item in result.get("employers", [])}
    seen: set[str] = set()

    for observation in observations:
        employer_key = str(observation.get("employer_id") or "").strip()
        if not employer_key or employer_key not in employers:
            raise ValueError(f"unknown employer_id: {employer_key or '<missing>'}")
        if employer_key in seen:
            raise ValueError(f"duplicate provider observation: {employer_key}")
        seen.add(employer_key)

        url = str(observation.get("url") or "").strip()
        if not re.match(r"^https?://", url, flags=re.I):
            raise ValueError(f"provider observation requires http(s) url: {employer_key}")
        final_url = str(observation.get("final_url") or "").strip() or None
        html = observation.get("html")
        fingerprint = fingerprint_provider(url, final_url=final_url, html=html)
        employer = employers[employer_key]
        employer["careers_url"] = final_url or url
        employer["provider"] = fingerprint

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("universe")
    parser.add_argument("observations")
    parser.add_argument("--output")
    args = parser.parse_args()

    universe = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    observations = json.loads(Path(args.observations).read_text(encoding="utf-8"))
    if not isinstance(observations, list):
        raise ValueError("observations must be a list")
    result = apply_observations(universe, observations)
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
