#!/usr/bin/env python3
"""Collapse feed records that resolve to the same authoritative posting.

Broad feeds often publish the same employer job with cosmetic URL or metadata
differences. This pass runs after link recovery, groups records by provider-native
posting identity for supported ATS families, and also collapses exact metadata
copies that converge on the same canonical direct URL for unsupported providers.

The historical filename is retained because the workflow already calls this
entrypoint, but reconciliation is provider-generic.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_feed as bf  # noqa: E402
from greenhouse_inspector import derive_greenhouse_endpoint  # noqa: E402
from icims_inspector import derive_icims_endpoint  # noqa: E402
from workday_inspector import derive_cxs_endpoint  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
LIST_FIELDS = ("source_keys", "source_names", "source_urls", "profiles", "states")
FILL_FIELDS = (
    "salary_min",
    "salary_max",
    "salary_period",
    "remote_type",
    "term",
    "education_level",
    "opportunity_type",
    "link_origin",
    "link_status",
    "link_checked_at",
    "resolved_from_url",
)
PROVIDERS = ("workday", "greenhouse", "icims")
WORKDAY_REQUISITION_SUFFIX = re.compile(r"_((?:[A-Za-z]+-?)?\d{4,})$", flags=re.I)


def workday_canonical_url(url: str | None) -> str | None:
    """Return the authoritative locale/query-independent Workday job URL."""

    if not url:
        return None
    try:
        return derive_cxs_endpoint(str(url))["canonical_job_url"]
    except (ValueError, KeyError, TypeError):
        return None


def workday_requisition_token(job_path: str | None) -> str | None:
    """Extract a stable Workday requisition token from the final URL slug."""

    if not job_path:
        return None
    slug = str(job_path).rstrip("/").rsplit("/", 1)[-1]
    match = WORKDAY_REQUISITION_SUFFIX.search(slug)
    return match.group(1).casefold() if match else None


def workday_identity_key(url: str | None) -> tuple[str, str, str] | None:
    """Return a grouping identity for one Workday posting."""

    if not url:
        return None
    try:
        derived = derive_cxs_endpoint(str(url))
        stable = workday_requisition_token(derived["job_path"])
        path_identity = f"req:{stable}" if stable else f"path:{str(derived['job_path'])}"
        return (
            str(derived["tenant"]).casefold(),
            str(derived["site"]).casefold(),
            path_identity,
        )
    except (ValueError, KeyError, TypeError):
        return None


def greenhouse_canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return derive_greenhouse_endpoint(str(url))["canonical_job_url"]
    except (ValueError, KeyError, TypeError):
        return None


def greenhouse_identity_key(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    try:
        derived = derive_greenhouse_endpoint(str(url))
        return (str(derived["board_token"]).casefold(), str(derived["job_id"]))
    except (ValueError, KeyError, TypeError):
        return None


def icims_canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return derive_icims_endpoint(str(url))["canonical_job_url"]
    except (ValueError, KeyError, TypeError):
        return None


def icims_identity_key(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    try:
        derived = derive_icims_endpoint(str(url))
        return (str(derived["host"]).casefold(), str(derived["job_id"]))
    except (ValueError, KeyError, TypeError):
        return None


def posting_identity_key(url: str | None) -> tuple[str, ...] | None:
    """Return a provider-qualified authoritative posting identity when supported."""

    workday = workday_identity_key(url)
    if workday:
        return ("workday", *workday)
    greenhouse = greenhouse_identity_key(url)
    if greenhouse:
        return ("greenhouse", *greenhouse)
    icims = icims_identity_key(url)
    if icims:
        return ("icims", *icims)
    return None


def canonical_posting_url(url: str | None) -> str | None:
    """Return the provider-native canonical job URL for a supported ATS posting."""

    return workday_canonical_url(url) or greenhouse_canonical_url(url) or icims_canonical_url(url)


def is_verified_workday_apply(job: dict[str, Any]) -> bool:
    """Return whether a record has a validated Workday /apply destination."""

    url = str(job.get("url") or "")
    return bool(
        workday_identity_key(url)
        and job.get("link_kind") == "direct"
        and job.get("link_status") == "ok"
        and str(job.get("link_checked_at") or "").strip()
        and url.rstrip("/").casefold().endswith("/apply")
    )


def reconciled_posting_url(job: dict[str, Any]) -> str | None:
    """Preserve verified Workday Apply destinations; canonicalize everything else."""

    canonical = canonical_posting_url(job.get("url"))
    if canonical and is_verified_workday_apply(job):
        return canonical.rstrip("/") + "/apply"
    return canonical or bf.canonical_url(job.get("url"))


def exact_direct_identity_key(job: dict[str, Any]) -> tuple[str, ...] | None:
    """Identify exact unsupported-provider copies after high-confidence link recovery.

    This deliberately requires both a direct link label and identical normalized
    company/title/location metadata. It prevents a shared employer landing page
    from collapsing distinct roles while still handling duplicate source rows
    that converge on the same recovered application URL.
    """

    if job.get("link_kind") != "direct" or posting_identity_key(job.get("url")):
        return None
    canonical = bf.canonical_url(job.get("url"))
    if not canonical:
        return None
    signature = (
        bf.norm(job.get("company")),
        bf.norm(job.get("title")),
        bf.norm(job.get("location")),
    )
    if not all(signature):
        return None
    return ("direct-url", canonical, *signature)


def authority_rank(job: dict[str, Any]) -> tuple[int, int, int, str, str]:
    """Rank duplicate copies without guessing employer identity from the hostname."""

    return (
        1 if job.get("direct_employer") else 0,
        1 if job.get("link_kind") == "direct" else 0,
        len(job.get("source_keys") or []),
        str(job.get("posted_at") or ""),
        str(job.get("id") or ""),
    )


def _union_values(group: list[dict[str, Any]], field: str) -> list[Any]:
    values: list[Any] = []
    seen: set[str] = set()
    for job in group:
        raw = job.get(field) or []
        if not isinstance(raw, list):
            raw = [raw]
        for value in raw:
            marker = json.dumps(value, sort_keys=True, ensure_ascii=False)
            if marker in seen:
                continue
            seen.add(marker)
            values.append(value)
    try:
        return sorted(values)
    except TypeError:
        return values


def _latest_timestamp_record(group: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    candidates = [job for job in group if job.get(field)]
    if not candidates:
        return None
    return max(candidates, key=lambda job: str(job.get(field) or ""))


def merge_posting_group(canonical_url: str, group: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge one posting group without inventing metadata."""

    winner = max(group, key=authority_rank)
    merged = copy.deepcopy(winner)
    merged["url"] = canonical_url

    if workday_identity_key(canonical_url):
        if canonical_url.rstrip("/").casefold().endswith("/apply"):
            merged["link_kind"] = "direct"
        else:
            merged["link_kind"] = "employer_job"

    for field in LIST_FIELDS:
        merged[field] = _union_values(group, field)

    direct_candidates = [job for job in group if job.get("direct_employer")]
    if direct_candidates:
        direct = max(direct_candidates, key=authority_rank)
        if direct.get("company"):
            merged["company"] = direct["company"]
        if direct.get("title"):
            merged["title"] = direct["title"]
        if direct.get("location"):
            merged["location"] = direct["location"]
        merged["direct_employer"] = True

    first_seen = [str(job.get("first_seen")) for job in group if job.get("first_seen")]
    if first_seen:
        merged["first_seen"] = min(first_seen)
    last_seen = [str(job.get("last_seen")) for job in group if job.get("last_seen")]
    if last_seen:
        merged["last_seen"] = max(last_seen)

    newest = _latest_timestamp_record(group, "posted_at")
    if newest:
        merged["posted_at"] = newest.get("posted_at")
        if newest.get("posted_raw"):
            merged["posted_raw"] = newest.get("posted_raw")

    for field in FILL_FIELDS:
        if merged.get(field) not in (None, "", []):
            continue
        for job in group:
            if job.get(field) not in (None, "", []):
                merged[field] = copy.deepcopy(job[field])
                break

    return merged


def merge_workday_group(canonical_url: str, group: list[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible alias for callers of the former Workday-only helper."""

    return merge_posting_group(canonical_url, group)


def reconcile_jobs(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    posting_groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        identity = posting_identity_key(job.get("url")) or exact_direct_identity_key(job)
        if not identity:
            passthrough.append(copy.deepcopy(job))
            continue
        posting_groups.setdefault(identity, []).append(job)

    reconciled = passthrough
    duplicate_groups = 0
    removed = 0
    provider_postings = {provider: 0 for provider in PROVIDERS}
    direct_url_postings = 0

    for identity, group in posting_groups.items():
        provider = identity[0]
        if provider in provider_postings:
            provider_postings[provider] += 1
        elif provider == "direct-url":
            direct_url_postings += 1
        if len(group) == 1:
            reconciled.append(copy.deepcopy(group[0]))
            continue
        duplicate_groups += 1
        removed += len(group) - 1
        winner = max(group, key=authority_rank)
        canonical = reconciled_posting_url(winner)
        if not canonical:
            reconciled.extend(copy.deepcopy(job) for job in group)
            duplicate_groups -= 1
            removed -= len(group) - 1
            continue
        reconciled.append(merge_posting_group(canonical, group))

    reconciled.sort(
        key=lambda job: (job.get("posted_at") or job.get("first_seen") or "", job.get("id") or ""),
        reverse=True,
    )
    return reconciled, {
        "ats_postings": sum(provider_postings.values()),
        "workday_postings": provider_postings["workday"],
        "greenhouse_postings": provider_postings["greenhouse"],
        "icims_postings": provider_postings["icims"],
        "direct_url_postings": direct_url_postings,
        "duplicate_groups": duplicate_groups,
        "records_removed": removed,
    }


def reconcile_document(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    out = copy.deepcopy(doc) if isinstance(doc, dict) else {"jobs": []}
    jobs = out.get("jobs") if isinstance(out.get("jobs"), list) else []
    reconciled, stats = reconcile_jobs(jobs)
    out["jobs"] = reconciled
    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()

    doc = json.loads(args.feed.read_text(encoding="utf-8"))
    updated, stats = reconcile_document(doc)
    changed = updated.get("jobs") != doc.get("jobs")
    if changed:
        args.feed.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({**stats, "changed": changed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
