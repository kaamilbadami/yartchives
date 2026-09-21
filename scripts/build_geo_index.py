#!/usr/bin/env python3
"""Build a compact browser geo index from the pinned ZIP CSV source."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


def normalize_place(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()


def build_geo_artifact(rows: list[dict[str, str]]) -> dict[str, Any]:
    zips: list[list[Any]] = []
    city_acc: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])

    for row in rows:
        zip_code = str(row.get("zip_code") or "").zfill(5)
        city = str(row.get("city") or "").strip()
        state = str(row.get("state") or "").strip().upper()
        try:
            lat = float(row.get("latitude") or "")
            lon = float(row.get("longitude") or "")
        except ValueError:
            continue
        if not re.fullmatch(r"\d{5}", zip_code) or not city or not state:
            continue

        zips.append([zip_code, round(lat, 5), round(lon, 5), state, city])
        key = (state, normalize_place(city))
        acc = city_acc[key]
        acc[0] += lat
        acc[1] += lon
        acc[2] += 1

    cities = [
        [state, city, round(lat_sum / count, 5), round(lon_sum / count, 5)]
        for (state, city), (lat_sum, lon_sum, count) in sorted(city_acc.items())
        if count
    ]
    return {"version": 1, "zips": zips, "cities": cities}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    artifact = build_geo_artifact(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
