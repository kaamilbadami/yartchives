#!/usr/bin/env python3
"""Build a deterministic employer seed from Fortune's edition-pinned ranking page."""
from __future__ import annotations

import argparse
import hashlib
import html as html_module
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from employer_universe import common_name_aliases, validate_seed  # noqa: E402
from domain_discovery import enrich_domains

EDITION = 2026
EXPECTED_COUNT = 500
DEFAULT_SOURCE_URL = "https://fortune.com/ranking/fortune500/2026/"
NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def extract_page_data(page_html: str) -> dict[str, Any]:
    match = NEXT_DATA_PATTERN.search(page_html)
    if not match:
        raise ValueError("official page does not contain __NEXT_DATA__ ranking data")
    return json.loads(html_module.unescape(match.group(1)))


def _ranking(page_data: dict[str, Any]) -> dict[str, Any]:
    try:
        return page_data["props"]["pageProps"]["franchiseSearch"]
    except (KeyError, TypeError) as exc:
        raise ValueError("official page ranking payload has an unsupported shape") from exc


def build_seed(
    page_data: dict[str, Any],
    *,
    source_url: str = DEFAULT_SOURCE_URL,
    retrieved_at: str,
    enrich_domain_hints: bool = False,
) -> dict[str, Any]:
    ranking = _ranking(page_data)
    if str(ranking.get("year")) != str(EDITION):
        raise ValueError(f"expected Fortune {EDITION}, found edition {ranking.get('year')!r}")

    items = sorted(ranking.get("items") or [], key=lambda item: int(item.get("order") or 0))
    selected = items[:EXPECTED_COUNT]
    if len(selected) != EXPECTED_COUNT:
        raise ValueError(f"expected {EXPECTED_COUNT} ranked companies, found {len(selected)}")
    orders = [int(item.get("order") or 0) for item in selected]
    if orders != list(range(1, EXPECTED_COUNT + 1)):
        raise ValueError("official ranking orders are not the contiguous range 1..500")

    normalized_rows = [
        {
            "order": int(item["order"]),
            "rank": int(item["rank"]),
            "name": str(item["name"]).strip(),
            "fortune_slug": str(item["slug"]).strip(),
        }
        for item in selected
    ]
    if any(not row["name"] or not row["fortune_slug"] for row in normalized_rows):
        raise ValueError("official ranking contains a company without a name or Fortune slug")
    selection_json = json.dumps(normalized_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    employers = []
    for row in normalized_rows:
        employer = dict(row)
        aliases = common_name_aliases(row["name"])
        if aliases:
            employer["aliases"] = aliases
        employers.append(employer)

    seed = {
        "schema_version": 1,
        "source": {
            "key": "fortune-500-2026",
            "kind": "fortune_500",
            "name": "Fortune 500",
            "edition": EDITION,
            "publisher": "Fortune Media IP Limited",
            "source_url": source_url,
            "published_at": ranking.get("modifiedGmt"),
            "retrieved_at": retrieved_at,
            "selection": "First 500 rows by order from props.pageProps.franchiseSearch.items",
            "selection_sha256": hashlib.sha256(selection_json.encode("utf-8")).hexdigest(),
            "status": "active",
        },
        "employers": employers,
    }

    if enrich_domain_hints:
        seed = enrich_domains(seed)
    validate_seed(seed)
    return seed


def fetch_page(source_url: str) -> str:
    request = Request(source_url, headers={"User-Agent": "Yartchives employer seed catalog/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--html", type=Path, help="Use a saved official page instead of fetching it")
    parser.add_argument("--retrieved-at", required=True, help="Explicit ISO-8601 retrieval timestamp")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    page_html = args.html.read_text(encoding="utf-8") if args.html else fetch_page(args.source_url)
    seed = build_seed(
        extract_page_data(page_html),
        source_url=args.source_url,
        retrieved_at=args.retrieved_at,
        enrich_domain_hints=True,
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
