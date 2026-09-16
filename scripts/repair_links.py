#!/usr/bin/env python3
"""Repair and label application links after the feed is merged.

The source repos are heterogeneous: some expose direct employer application
URLs, some expose an aggregator listing/redirect, and some only expose a source
page. Yartchives should never label a generic/source URL as "Apply".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "listings.json"
APPLYGUY_JSON = "https://raw.githubusercontent.com/ApplyGuy/2027-Internships/main/data/internships.json"
TIMEOUT = 25

AGGREGATOR_HOSTS = {
    "simplify.jobs",
    "www.simplify.jobs",
    "zapply.jobs",
    "www.zapply.jobs",
    "jobright.ai",
    "www.jobright.ai",
    "applyguy.ai",
    "www.applyguy.ai",
    "applyguy.com",
    "www.applyguy.com",
    "fromcampustocareer.com",
    "www.fromcampustocareer.com",
}
SOURCE_HOSTS = {
    "github.com",
    "www.github.com",
    "raw.githubusercontent.com",
}


def norm(value: str | None) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def is_http_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def is_direct_application_url(value: str | None) -> bool:
    if not is_http_url(value):
        return False
    host = urlparse(value).netloc.lower()
    return host not in AGGREGATOR_HOSTS and host not in SOURCE_HOSTS


def is_listing_url(value: str | None) -> bool:
    if not is_http_url(value):
        return False
    host = urlparse(value).netloc.lower()
    return host in AGGREGATOR_HOSTS


def applyguy_indexes(payload: dict[str, Any]) -> tuple[dict[tuple[str, str], str], dict[str, list[str]]]:
    exact: dict[tuple[str, str], str] = {}
    by_title: dict[str, list[str]] = {}
    for row in payload.get("jobs", []):
        if not isinstance(row, dict):
            continue
        direct = row.get("listingUrl")
        if not is_direct_application_url(direct):
            continue
        company = compact(row.get("company"))
        title = norm(row.get("title"))
        if company and title:
            exact[(company, title)] = direct
        if title:
            by_title.setdefault(title, []).append(direct)
    return exact, by_title


def choose_applyguy_direct(job: dict[str, Any], exact: dict[tuple[str, str], str], by_title: dict[str, list[str]]) -> str | None:
    title = norm(job.get("title"))
    company = compact(job.get("company"))
    if company and title and (company, title) in exact:
        return exact[(company, title)]
    candidates = list(dict.fromkeys(by_title.get(title, []))) if title else []
    return candidates[0] if len(candidates) == 1 else None


def repair_document(doc: dict[str, Any], applyguy_payload: dict[str, Any] | None = None) -> dict[str, int]:
    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Feed does not contain a jobs list")

    exact: dict[tuple[str, str], str] = {}
    by_title: dict[str, list[str]] = {}
    if applyguy_payload:
        exact, by_title = applyguy_indexes(applyguy_payload)

    stats = {"direct": 0, "listing": 0, "source": 0, "applyguy_repaired": 0, "changed": 0}

    for job in jobs:
        if not isinstance(job, dict):
            continue
        before = (job.get("url"), job.get("listing_url"), job.get("link_kind"))
        source_keys = set(job.get("source_keys") or [])
        current = job.get("url") or ""

        if "applyguy" in source_keys and not is_direct_application_url(current) and exact:
            repaired = choose_applyguy_direct(job, exact, by_title)
            if repaired:
                job["url"] = repaired
                current = repaired
                stats["applyguy_repaired"] += 1

        if is_direct_application_url(current):
            job["link_kind"] = "direct"
            job.pop("listing_url", None)
            stats["direct"] += 1
        else:
            listing = job.get("listing_url") if is_listing_url(job.get("listing_url")) else None
            if not listing and is_listing_url(current):
                listing = current
            job["url"] = ""
            if listing:
                job["listing_url"] = listing
                job["link_kind"] = "listing"
                stats["listing"] += 1
            else:
                job.pop("listing_url", None)
                job["link_kind"] = "source"
                stats["source"] += 1

        after = (job.get("url"), job.get("listing_url"), job.get("link_kind"))
        if before != after:
            stats["changed"] += 1

    return stats


def fetch_applyguy_payload() -> dict[str, Any] | None:
    try:
        response = requests.get(
            APPLYGUY_JSON,
            headers={"User-Agent": "Yartchives/1.0 link-repair"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ApplyGuy feed is not an object")
        return payload
    except Exception as exc:
        print(f"warning: ApplyGuy direct-link enrichment unavailable: {exc}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=str(DEFAULT_PATH))
    parser.add_argument("--offline", action="store_true", help="skip network enrichment and only normalize existing URLs")
    args = parser.parse_args()

    path = Path(args.path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    payload = None if args.offline else fetch_applyguy_payload()
    stats = repair_document(doc, payload)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "Link repair: "
        f"{stats['direct']} direct, {stats['listing']} listing-only, {stats['source']} source-only, "
        f"{stats['applyguy_repaired']} ApplyGuy direct links repaired"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
