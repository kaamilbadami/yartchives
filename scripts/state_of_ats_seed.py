#!/usr/bin/env python3
"""Build a deterministic employer seed from a pinned State of ATS CSV snapshot."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from employer_universe import validate_seed  # noqa: E402

SOURCE_KEY = "state-of-ats-2026-verified-hosts"
SOURCE_NAME = "State of ATS 2026 verified apply hosts"
PUBLISHER = "Kayvan Zahiri / ResumeAI"
UPSTREAM_REPOSITORY = "Kayvan-Zahiri/state-of-ats-2026"
UPSTREAM_COMMIT = "0ba7374eeab4db1d9aa89bdf0db33a6cd11396a2"
UPSTREAM_PATH = "data/companies.csv"
UPSTREAM_VERSION = "2.0.0"
SOURCE_URL = "https://github.com/Kayvan-Zahiri/state-of-ats-2026"
EXPECTED_SELECTED_COUNT = 548
REQUIRED_COLUMNS = {
    "name",
    "slug",
    "ats_system",
    "verified",
    "apply_host",
    "evidence_method",
    "checked_at",
    "hq_country_code",
    "source_url",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_seed(rows: list[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("State of ATS CSV contains no rows")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise ValueError(f"State of ATS CSV is missing columns: {sorted(missing)}")

    selected = [
        row
        for row in rows
        if _clean(row.get("verified")).casefold() == "true"
        and _clean(row.get("apply_host"))
    ]
    selected.sort(key=lambda row: (_clean(row.get("name")).casefold(), _clean(row.get("slug")).casefold()))

    employers: list[dict[str, Any]] = []
    for row in selected:
        name = _clean(row.get("name"))
        slug = _clean(row.get("slug"))
        apply_host = _clean(row.get("apply_host"))
        if not name or not slug or not apply_host:
            raise ValueError("selected State of ATS row is missing name, slug, or apply_host")

        ats_system = _clean(row.get("ats_system"))
        if ats_system.casefold() == "lever" and apply_host == "jobs.lever.co":
            apply_host = f"{apply_host}/{slug}"
        elif ats_system.casefold() == "greenhouse" and apply_host in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
            apply_host = f"{apply_host}/{slug}"

        employer: dict[str, Any] = {
            "name": name,
            "upstream_slug": slug,
            "ats_system": ats_system,
            "apply_host": apply_host,
            "domain_hints": [apply_host],
            "evidence_method": _clean(row.get("evidence_method")),
            "checked_at": _clean(row.get("checked_at")),
            "source_url": _clean(row.get("source_url")),
        }
        hq_country_code = _clean(row.get("hq_country_code"))
        if hq_country_code:
            employer["hq_country_code"] = hq_country_code
        employers.append(employer)

    seed = {
        "schema_version": 1,
        "source": {
            "key": SOURCE_KEY,
            "kind": "external_ats_evidence",
            "name": SOURCE_NAME,
            "publisher": PUBLISHER,
            "upstream_repository": UPSTREAM_REPOSITORY,
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_path": UPSTREAM_PATH,
            "upstream_version": UPSTREAM_VERSION,
            "source_url": SOURCE_URL,
            "license": "MIT",
            "selection": "Rows with verified=true and nonempty apply_host",
            "selected_count": len(employers),
            "status": "active",
        },
        "employers": employers,
    }
    validate_seed(seed)
    return seed


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="Pinned upstream companies.csv snapshot")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-pinned-count",
        action="store_true",
        help=f"Require the pinned snapshot to yield exactly {EXPECTED_SELECTED_COUNT} selected rows",
    )
    args = parser.parse_args()

    seed = build_seed(read_rows(args.csv))
    if args.require_pinned_count and len(seed["employers"]) != EXPECTED_SELECTED_COUNT:
        raise ValueError(
            f"expected {EXPECTED_SELECTED_COUNT} verified host rows, found {len(seed['employers'])}"
        )

    rendered = json.dumps(seed, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
