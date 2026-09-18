#!/usr/bin/env python3
"""Run independent ATS collectors concurrently, then merge deterministically."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_feed as bf  # noqa: E402
import direct_ct_workday as workday  # noqa: E402
import direct_greenhouse as greenhouse  # noqa: E402
import direct_icims as icims  # noqa: E402
import direct_oracle as oracle  # noqa: E402

DEFAULT_FEED = SCRIPT_DIR.parent / "data" / "listings.json"
DEFAULT_SOURCES = SCRIPT_DIR.parent / "direct_sources.json"
DEFAULT_UNIVERSE = SCRIPT_DIR.parent / "employer_universe.json"
PROVIDER_ORDER = ("workday", "icims", "greenhouse", "oracle")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _job_indexes(jobs: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_url: dict[str, dict[str, Any]] = {}
    for job in jobs:
        job_id = str(job.get("id") or "")
        if job_id:
            by_id[job_id] = job
        url = bf.canonical_url(job.get("url"))
        if url:
            by_url[url] = job
    return by_id, by_url


def _merge_normalized_job(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for field in ("source_keys", "source_names", "source_urls", "profiles", "states"):
        target[field] = sorted(set(target.get(field) or []) | set(incoming.get(field) or []))

    if incoming.get("direct_employer"):
        target["direct_employer"] = True
        if incoming.get("url"):
            target["url"] = incoming["url"]
        if incoming.get("company"):
            target["company"] = incoming["company"]

    if incoming.get("posted_at") and (
        not target.get("posted_at") or incoming["posted_at"] > target["posted_at"]
    ):
        target["posted_at"] = incoming["posted_at"]
        target["posted_raw"] = incoming.get("posted_raw", "")

    for field in (
        "salary_min", "salary_max", "salary_period", "remote_type", "term",
        "education_level", "opportunity_type", "first_seen", "last_seen",
    ):
        if not target.get(field) and incoming.get(field) is not None:
            target[field] = incoming[field]


def merge_provider_documents(
    base_doc: dict[str, Any],
    provider_docs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    merged = copy.deepcopy(base_doc)
    merged_jobs = merged.setdefault("jobs", [])
    merged_sources = merged.setdefault("sources", {})
    base_sources = base_doc.get("sources", {}) if isinstance(base_doc.get("sources"), dict) else {}

    for provider in PROVIDER_ORDER:
        doc = provider_docs.get(provider)
        if not isinstance(doc, dict):
            continue

        for key, value in (doc.get("sources") or {}).items():
            if key not in base_sources or value != base_sources.get(key):
                merged_sources[key] = copy.deepcopy(value)

        by_id, by_url = _job_indexes(merged_jobs)
        for incoming in doc.get("jobs") or []:
            if not isinstance(incoming, dict):
                continue
            incoming_url = bf.canonical_url(incoming.get("url"))
            target = by_url.get(incoming_url) if incoming_url else None
            if target is None and incoming.get("id"):
                target = by_id.get(str(incoming["id"]))

            if target is None:
                target = copy.deepcopy(incoming)
                merged_jobs.append(target)
            else:
                _merge_normalized_job(target, incoming)

            job_id = str(target.get("id") or "")
            if job_id:
                by_id[job_id] = target
            target_url = bf.canonical_url(target.get("url"))
            if target_url:
                by_url[target_url] = target

    merged_jobs.sort(
        key=lambda job: (job.get("posted_at") or job.get("first_seen") or "", job.get("id") or ""),
        reverse=True,
    )
    return merged


def run_parallel(
    collectors: dict[str, Callable[[], dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(collectors)) as pool:
        futures = {pool.submit(fn): name for name, fn in collectors.items()}
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
    return results


def collect(
    base_doc: dict[str, Any],
    old_doc: dict[str, Any],
    direct_sources: list[dict[str, Any]],
    universe: dict[str, Any],
    reference: datetime,
) -> dict[str, dict[str, Any]]:
    def workday_task() -> dict[str, Any]:
        doc = copy.deepcopy(base_doc)
        workday.enrich_direct_sources(doc, old_doc, direct_sources, workday.session(), reference)
        return doc

    def icims_task() -> dict[str, Any]:
        doc = copy.deepcopy(base_doc)
        icims.enrich(doc, old_doc, icims.retry_session(), reference)
        return doc

    def greenhouse_task() -> dict[str, Any]:
        doc = copy.deepcopy(base_doc)
        greenhouse.enrich(doc, old_doc, greenhouse.retry_session(), reference)
        return doc

    def oracle_task() -> dict[str, Any]:
        doc = copy.deepcopy(base_doc)
        oracle.enrich(doc, old_doc, universe, oracle.retry_session(), reference)
        return doc

    return run_parallel(
        {
            "workday": workday_task,
            "icims": icims_task,
            "greenhouse": greenhouse_task,
            "oracle": oracle_task,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--old-feed", type=Path, required=True)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    args = parser.parse_args()

    base_doc = _load(args.feed)
    old_doc = _load(args.old_feed)
    direct_sources = _load(args.sources)
    universe = _load(args.universe)
    if not isinstance(direct_sources, list):
        raise ValueError("direct source file must contain a list")

    reference = datetime.now(timezone.utc)
    print("ATS collection: Workday, iCIMS, Greenhouse, and Oracle running concurrently")
    provider_docs = collect(base_doc, old_doc, direct_sources, universe, reference)
    merged = merge_provider_documents(base_doc, provider_docs)
    if workday.stable_projection(merged) != workday.stable_projection(base_doc):
        merged["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    counts = ", ".join(
        f"{name}={len((provider_docs.get(name) or {}).get('jobs') or [])}"
        for name in PROVIDER_ORDER
    )
    print(f"ATS collection complete ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
