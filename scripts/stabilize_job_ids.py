#!/usr/bin/env python3
"""Keep final feed job IDs stable across harmless metadata and URL-shape drift.

Frontend Saved/Applied/Hidden state is keyed by job.id. This post-processing pass
runs after link recovery and provider reconciliation so the final published feed
uses authoritative posting identity when available and preserves an existing ID
when the same posting can be matched to the previous final feed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Hashable

import build_feed as bf
from reconcile_workday_duplicates import posting_identity_key


def metadata_signature(job: dict[str, Any]) -> tuple[str, str, str]:
    return (
        bf.norm(job.get("company")),
        bf.norm(job.get("title")),
        bf.norm(job.get("location")),
    )


def canonical_listing_url(job: dict[str, Any]) -> str:
    return bf.canonical_url(job.get("url"))


def stable_identity_basis(job: dict[str, Any]) -> str:
    provider = posting_identity_key(job.get("url"))
    if provider:
        return "provider|" + "|".join(provider)
    url = canonical_listing_url(job)
    if url:
        return f"url|{url}"
    return "metadata|" + "|".join(metadata_signature(job))


def deterministic_job_id(job: dict[str, Any]) -> str:
    return hashlib.sha1(stable_identity_basis(job).encode("utf-8")).hexdigest()[:16]


def collision_job_id(job: dict[str, Any], ordinal: int) -> str:
    basis = "|".join((
        stable_identity_basis(job),
        canonical_listing_url(job),
        *metadata_signature(job),
        "collision",
        str(ordinal),
    ))
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def unique_index(
    jobs: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], Hashable | None],
) -> dict[Hashable, dict[str, Any]]:
    grouped: dict[Hashable, list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        key = key_fn(job)
        if key:
            grouped[key].append(job)
    return {key: rows[0] for key, rows in grouped.items() if len(rows) == 1}


def match_prior_job(
    job: dict[str, Any],
    *,
    old_by_provider: dict[Hashable, dict[str, Any]],
    old_by_url: dict[Hashable, dict[str, Any]],
    old_by_signature: dict[Hashable, dict[str, Any]],
) -> dict[str, Any] | None:
    provider = posting_identity_key(job.get("url"))
    if provider and provider in old_by_provider:
        return old_by_provider[provider]

    url = canonical_listing_url(job)
    if url and url in old_by_url:
        return old_by_url[url]

    signature = metadata_signature(job)
    return old_by_signature.get(signature)


def stabilize_jobs(
    jobs: list[dict[str, Any]],
    old_jobs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    old_by_provider = unique_index(old_jobs, lambda job: posting_identity_key(job.get("url")))
    old_by_url = unique_index(old_jobs, lambda job: canonical_listing_url(job) or None)
    old_by_signature = unique_index(old_jobs, metadata_signature)

    preserved = 0
    generated = 0
    used_ids: set[str] = set()
    output: list[dict[str, Any]] = []

    for source in jobs:
        job = dict(source)
        prior = match_prior_job(
            job,
            old_by_provider=old_by_provider,
            old_by_url=old_by_url,
            old_by_signature=old_by_signature,
        )
        prior_id = str(prior.get("id") or "") if prior else ""
        preserved_prior = bool(prior_id and prior_id not in used_ids)
        job_id = prior_id if preserved_prior else deterministic_job_id(job)

        # A broader upstream can legitimately surface multiple current rows that
        # converge on one provider or historical identity. Preserve the historical
        # ID for at most one row, then assign deterministic unique fallbacks rather
        # than failing the entire feed refresh.
        ordinal = 1
        while job_id in used_ids:
            job_id = collision_job_id(job, ordinal)
            ordinal += 1

        job["id"] = job_id
        used_ids.add(job_id)
        if preserved_prior:
            preserved += 1
            if prior.get("first_seen"):
                job["first_seen"] = prior["first_seen"]
        else:
            generated += 1
        output.append(job)

    return output, {"preserved": preserved, "generated": generated, "total": len(output)}


def load_jobs(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), list):
        raise ValueError(f"Expected feed document with jobs array: {path}")
    jobs = [job for job in doc["jobs"] if isinstance(job, dict)]
    return doc, jobs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("feed", type=Path)
    parser.add_argument("--old-feed", type=Path, required=True)
    args = parser.parse_args()

    doc, jobs = load_jobs(args.feed)
    _, old_jobs = load_jobs(args.old_feed)
    stabilized, stats = stabilize_jobs(jobs, old_jobs)
    doc["jobs"] = stabilized
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "Stable job IDs: "
        f"{stats['preserved']} preserved, {stats['generated']} generated, {stats['total']} total"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
