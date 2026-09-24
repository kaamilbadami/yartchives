#!/usr/bin/env python3
"""Add direct Connecticut CS-relevant employer listings from public Workday APIs.

The broad GitHub internship feeds are useful for discovery, but Connecticut
coverage can be sparse or delayed. This pass queries selected employer career
systems directly, keeps student opportunities in Connecticut that match
CS/technology titles, and merges them into the normalized feed. Direct
employer URLs are preferred over aggregator links.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_feed as bf  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_SOURCES = ROOT / "direct_sources.json"
TIMEOUT = 25
WORKDAY_PAGE_SIZE = 20
MAX_RESULTS_PER_QUERY = 500
STRUCTURAL_SOURCE_STATUSES = {404, 410, 422}


class StructuralSourceError(RuntimeError):
    """An auto-discovered provider endpoint is structurally invalid or gone."""

    def __init__(self, message: str, status_codes: list[int] | None = None):
        super().__init__(message)
        self.status_codes = tuple(status_codes or [])


# Workday search is fuzzy: a query such as "intern software" can return any
# internship at the employer. Require the title itself to carry a strong CS / IT
# signal before assigning the CS profile. This intentionally favors precision;
# source-specific patterns can be added when a legitimate title uses unusual
# wording.
CS_TITLE_PATTERNS = (
    r"\bsoftware\b",
    r"\bcomputer\s+(?:science|engineering)\b",
    r"\bcyber(?:security|\s+security)?\b",
    r"\binformation\s+(?:technology|security)\b",
    r"\bdata\s+(?:engineer(?:ing)?|science|scientist|analytics?)\b",
    r"\bmachine\s+learning\b",
    r"\bartificial\s+intelligence\b",
    r"\bfirmware\b",
    r"\bembedded\b",
    r"\b(?:full[- ]?stack|front[- ]?end|back[- ]?end)\b",
    r"\b(?:database|sql)\b",
    r"\b(?:network|networking)\b",
    r"\b(?:cloud|devops|site reliability)\b",
    r"\b(?:application|web|technology)\s+develop(?:er|ment)\b",
    r"\bprogrammer\b",
    r"\b(?:platform|platforms|systems?|infrastructure)\s+engineer(?:ing)?\b",
    r"(?<!food\s)\b(?:technology|security)\s+(?:intern(?:ship)?|co[- ]?op|analyst|specialist|program)\b",
    r"\b(?:intern(?:ship)?|co[- ]?op)\s+(?:-|in|for)?\s*(?:technology|security)\b",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": bf.USER_AGENT, "Accept": "application/json"})
    return s


def normalize_posted(raw: str | None) -> str:
    text = bf.clean_text(raw).strip()
    text = re.sub(r"^posted\s+", "", text, flags=re.I)
    if text.lower() == "yesterday":
        return "1 day"
    text = re.sub(r"\s+ago$", "", text, flags=re.I)
    return text


def is_student_opportunity(title: str) -> bool:
    return bool(re.search(r"\b(intern(?:ship)?|co[- ]?op|student)\b", title or "", flags=re.I))


def is_cs_relevant_title(title: str, source: dict[str, Any] | None = None) -> bool:
    text = bf.clean_text(title)
    if not text:
        return False

    # "IT" is useful as an acronym but case-insensitive matching would also match
    # the ordinary word "it". Match the uppercase acronym separately.
    if re.search(r"\bIT\b", text):
        return True
    if any(re.search(pattern, text, flags=re.I) for pattern in CS_TITLE_PATTERNS):
        return True

    # Some employers use stable internal program names that do not contain a
    # generic CS keyword. Keep those exceptions explicit in direct_sources.json.
    if source:
        for pattern in source.get("title_allow_patterns", []):
            if re.search(pattern, text, flags=re.I):
                return True
    return False


def is_target_state(location: str, state: str) -> bool:
    if not location or not state:
        return False
    state = state.upper()
    if re.search(rf"\b{re.escape(state)}\b", location, flags=re.I):
        return True
    full_names = [name for name, abbr in bf.STATE_NAMES.items() if abbr == state]
    return any(re.search(rf"\b{re.escape(name)}\b", location, flags=re.I) for name in full_names)


def is_us_location(location: str) -> bool:
    if not location:
        return False
    if bf.extract_states(location):
        return True
    return bool(re.search(
        r"\b(?:United States(?: of America)?|USA|U\.S\.|US Remote|Remote[- ]?US|Remote[- ]?USA)\b",
        location,
        flags=re.I,
    ))


def public_job_url(source: dict[str, Any], external_path: str | None) -> str:
    if not external_path:
        return source.get("homepage", "")
    if external_path.startswith("http://") or external_path.startswith("https://"):
        return external_path
    return source["public_base"].rstrip("/") + "/" + external_path.lstrip("/")


def fetch_workday_source(
    s: requests.Session,
    source: dict[str, Any],
    reference: datetime,
) -> list[dict[str, Any]]:
    if source.get("kind") != "workday":
        raise ValueError(f"Unsupported direct source kind: {source.get('kind')}")

    seen_paths: set[str] = set()
    out: list[dict[str, Any]] = []
    state = str(source.get("state") or "").upper()
    national_scope = str(source.get("scope") or "").casefold() == "us"
    if not state and not national_scope:
        state = "CT"

    successful_terms = 0
    term_errors: list[str] = []
    structural_statuses: list[int] = []
    for term in source.get("search_terms", ["intern"]):
        offset = 0
        try:
            while offset < MAX_RESULTS_PER_QUERY:
                payload = {
                    "appliedFacets": {},
                    "limit": WORKDAY_PAGE_SIZE,
                    "offset": offset,
                    "searchText": term,
                }
                response = s.post(source["api_url"], json=payload, timeout=TIMEOUT)
                response.raise_for_status()
                data = response.json()
                postings = data.get("jobPostings") or []
                if not isinstance(postings, list) or not postings:
                    break

                for item in postings:
                    if not isinstance(item, dict):
                        continue
                    title = bf.clean_text(item.get("title"))
                    location = bf.clean_text(item.get("locationsText")) or "Location not listed"
                    external_path = item.get("externalPath") or ""
                    dedupe_key = external_path or f"{title}|{location}"
                    if dedupe_key in seen_paths:
                        continue
                    if not is_student_opportunity(title):
                        continue
                    if not is_cs_relevant_title(title, source):
                        continue
                    if state:
                        if not is_target_state(location, state):
                            continue
                    elif national_scope and not is_us_location(location):
                        continue

                    posted_raw = normalize_posted(item.get("postedOn"))
                    posted_at = bf.parse_relative_date(posted_raw, reference)
                    date_source = dict(source)
                    date_source["posted_date_provenance"] = "authoritative_employer"
                    job = bf.base_job(
                        company=source["company"],
                        title=title,
                        location=location,
                        url=public_job_url(source, external_path),
                        posted_raw=posted_raw,
                        source=date_source,
                        section=f"Direct employer match: {term}",
                        function_primary="Computer Science / Technology",
                        posted_at=posted_at,
                    )
                    if not job:
                        continue
                    if state and state not in job.get("states", []):
                        job["states"] = sorted(set(job.get("states", [])) | {state})
                    job["direct_employer"] = True
                    out.append(job)
                    seen_paths.add(dedupe_key)

                total = int(data.get("total") or 0)
                offset += len(postings)
                if offset >= total:
                    break
            successful_terms += 1
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            term_errors.append(f"{term}: {type(exc).__name__}: {exc}")
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            if isinstance(status, int) and status in STRUCTURAL_SOURCE_STATUSES:
                structural_statuses.append(status)
            continue

    if successful_terms == 0 and term_errors:
        if len(structural_statuses) == len(term_errors):
            raise StructuralSourceError(
                "all Workday search terms failed with structural HTTP status: " + " | ".join(term_errors),
                structural_statuses,
            )
        raise RuntimeError("all Workday search terms failed: " + " | ".join(term_errors))
    return out


def stable_job_id(job: dict[str, Any]) -> str:
    basis = "|".join((bf.norm(job.get("company")), bf.norm(job.get("title")), bf.norm(job.get("location"))))
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def make_indexes(jobs: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_url: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("id"):
            by_id[job["id"]] = job
        url = bf.canonical_url(job.get("url"))
        if url:
            by_url[url] = job
    return by_id, by_url


def upsert_direct_job(
    jobs: list[dict[str, Any]],
    incoming: dict[str, Any],
    old_jobs_by_id: dict[str, dict[str, Any]],
    reference: datetime,
) -> None:
    by_id, by_url = make_indexes(jobs)
    incoming_id = stable_job_id(incoming)
    incoming_url = bf.canonical_url(incoming.get("url"))
    target = by_url.get(incoming_url) if incoming_url else None
    if target is None:
        target = by_id.get(incoming_id)

    if target is not None:
        bf.merge_job(target, incoming)
        if incoming.get("url"):
            # This pass is explicitly an employer-direct source, so it should beat
            # Indeed/LinkedIn/GitHub/other listing intermediaries as well as the
            # aggregator hosts known by build_feed.py.
            target["url"] = incoming["url"]
        target["direct_employer"] = True
        return

    row = dict(incoming)
    row["source_keys"] = [incoming["source_key"]]
    row["source_names"] = [incoming["source_name"]]
    row["source_urls"] = [incoming["source_url"]]
    for key in ("source_key", "source_name", "source_url", "section", "function_primary"):
        row.pop(key, None)
    row["id"] = incoming_id
    prior = old_jobs_by_id.get(incoming_id) or {}
    row["first_seen"] = prior.get("first_seen") or bf.iso(reference)
    row["last_seen"] = prior.get("last_seen") or bf.iso(reference)
    jobs.append(row)


def carry_failed_source(
    jobs: list[dict[str, Any]],
    old_jobs: list[dict[str, Any]],
    source_key: str,
) -> bool:
    by_id, by_url = make_indexes(jobs)
    carried_any = False
    for old in old_jobs:
        if source_key not in (old.get("source_keys") or []):
            continue
        carried_any = True
        target = by_id.get(old.get("id"))
        if target is None:
            old_url = bf.canonical_url(old.get("url"))
            target = by_url.get(old_url) if old_url else None
        if target is None:
            carried = copy.deepcopy(old)
            carried["carried_forward"] = True
            jobs.append(carried)
            by_id, by_url = make_indexes(jobs)
            continue
        target["source_keys"] = sorted(set(target.get("source_keys", [])) | {source_key})
        target["source_names"] = sorted(set(target.get("source_names", [])) | set(old.get("source_names", [])))
        target["source_urls"] = sorted(set(target.get("source_urls", [])) | set(old.get("source_urls", [])))
        target["profiles"] = sorted(set(target.get("profiles", [])) | set(old.get("profiles", [])))
        if old.get("direct_employer") and old.get("url"):
            target["url"] = old["url"]
            target["direct_employer"] = True
    return carried_any


def stable_projection(doc: dict[str, Any]) -> str:
    jobs = []
    for job in doc.get("jobs", []):
        if not isinstance(job, dict):
            continue
        row = dict(job)
        row.pop("last_seen", None)
        jobs.append(row)
    jobs.sort(key=lambda x: (x.get("id") or "", x.get("url") or ""))
    payload = {
        "jobs": jobs,
        "sources": doc.get("sources", {}),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def enrich_direct_sources(
    doc: dict[str, Any],
    old_doc: dict[str, Any],
    sources: list[dict[str, Any]],
    s: requests.Session,
    reference: datetime,
) -> dict[str, Any]:
    jobs = doc.setdefault("jobs", [])
    health = doc.setdefault("sources", {})
    old_jobs = old_doc.get("jobs", []) if isinstance(old_doc, dict) else []
    old_jobs_by_id = {j.get("id"): j for j in old_jobs if isinstance(j, dict) and j.get("id")}

    for source in sources:
        try:
            direct_jobs = fetch_workday_source(s, source, reference)
            minimum = int(source.get("minimum_expected") or 0)
            if len(direct_jobs) < minimum:
                raise RuntimeError(
                    f"expected at least {minimum} matching student listing(s), got {len(direct_jobs)}"
                )
            for job in direct_jobs:
                upsert_direct_job(jobs, job, old_jobs_by_id, reference)
            health[source["key"]] = {
                "status": "healthy",
                "count": len(direct_jobs),
                "name": source["name"],
                "direct": True,
            }
            scope_label = source.get("state") or ("US" if source.get("scope") == "us" else "configured")
            print(f"{source['name']}: {len(direct_jobs)} direct {scope_label} CS-relevant listing(s)")
        except StructuralSourceError as exc:
            health[source["key"]] = {
                "status": "quarantined",
                "count": 0,
                "name": source["name"],
                "direct": True,
                "auto_discovered": bool(source.get("auto_discovered")),
                "error": f"{type(exc).__name__}: {exc}",
            }
            carry_failed_source(jobs, old_jobs, source["key"])
            print(f"{source['name']}: QUARANTINED: {exc}", file=sys.stderr)
        except Exception as exc:
            health[source["key"]] = {
                "status": "failed",
                "count": 0,
                "name": source["name"],
                "direct": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
            if carry_failed_source(jobs, old_jobs, source["key"]):
                health[source["key"]]["status"] = "degraded"
            print(f"{source['name']}: FAILED: {exc}", file=sys.stderr)

    jobs.sort(
        key=lambda job: (job.get("posted_at") or job.get("first_seen") or "", job.get("id") or ""),
        reverse=True,
    )
    return doc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--old-feed", type=Path)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    args = parser.parse_args()

    doc = json.loads(args.feed.read_text(encoding="utf-8"))
    old_doc: dict[str, Any] = {}
    if args.old_feed and args.old_feed.exists():
        try:
            old_doc = json.loads(args.old_feed.read_text(encoding="utf-8"))
        except Exception:
            old_doc = {}
    if not old_doc:
        old_doc = copy.deepcopy(doc)

    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    reference = now_utc()
    enrich_direct_sources(doc, old_doc, sources, session(), reference)

    if stable_projection(doc) == stable_projection(old_doc):
        # If build_feed.py rewrote only volatile metadata, restore the prior final
        # document so the hourly workflow does not create a no-op commit.
        if args.old_feed and args.old_feed.exists():
            args.feed.write_text(json.dumps(old_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Direct employer coverage unchanged.")
        return 0

    doc["generated_at"] = bf.iso(reference)
    args.feed.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Merged direct employer coverage into {args.feed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
