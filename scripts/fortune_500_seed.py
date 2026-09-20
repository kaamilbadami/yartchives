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

EDITION = 2026
EXPECTED_COUNT = 500
DEFAULT_SOURCE_URL = "https://fortune.com/ranking/fortune500/2026/"
NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def enrich_domains(seed: dict[str, Any]) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import urllib.request
    import urllib.parse

    def normalize_company(name: str) -> str:
        name = name.lower()
        for suffix in [" inc", " corp", " corporation", " company", " co", " llc", " group", " holdings", " platforms", " technologies"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        name = re.sub(r'[^a-z0-9]', '', name)
        return name

    def get_company_domain(name: str) -> str | None:
        query = urllib.parse.quote(f"{name} company")
        target_norm = normalize_company(name)

        # Try Wikipedia first, it's highly curated and much less prone to data poisoning
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&utf8=&format=json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get('query', {}).get('search'):
                    title = data['query']['search'][0]['title']

                    title_norm = normalize_company(title)
                    if target_norm in title_norm or title_norm in target_norm:
                        title_encoded = urllib.parse.quote(title)
                        url_page = f"https://en.wikipedia.org/w/api.php?action=parse&page={title_encoded}&prop=text&format=json"
                        req_page = urllib.request.Request(url_page, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req_page, timeout=10) as resp_page:
                            data_page = json.loads(resp_page.read().decode('utf-8'))
                            if 'parse' in data_page and 'text' in data_page['parse']:
                                html_text = data_page['parse']['text']['*']
                                m = re.search(r'Website.*?<a[^>]*href="([^"]+)"', html_text, re.DOTALL | re.IGNORECASE)
                                if m:
                                    domain = urllib.parse.urlparse(m.group(1)).netloc
                                    if domain and not "wikipedia" in domain and not "wikimedia" in domain:
                                        return domain.removeprefix("www.")
        except Exception:
            pass

        # If Wikipedia fails, try Clearbit, but with strict matching
        query_cb = urllib.parse.quote(name)
        url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={query_cb}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data:
                    for item in data:
                        res_name = item.get('name', '')
                        res_norm = normalize_company(res_name)
                        if not target_norm or not res_norm:
                            continue

                        if target_norm == res_norm or target_norm in res_norm or res_norm in target_norm:
                            domain = str(item['domain']).lower()
                            domain_norm = re.sub(r'[^a-z0-9]', '', domain.split('.')[0])
                            if domain_norm in target_norm or target_norm in domain_norm:
                                return str(item['domain'])
        except Exception:
            pass

        return None

    def fetch(emp: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        return emp, get_company_domain(emp['name'])

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch, emp): emp for emp in seed.get("employers", [])}
        for future in as_completed(futures):
            emp, domain = future.result()
            if domain:
                emp["domain_hints"] = [domain]

    # Sort keys to maintain stability
    for emp in seed.get("employers", []):
        if "domain_hints" in emp:
            emp["domain_hints"] = sorted(emp["domain_hints"])

    return seed


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
