#!/usr/bin/env python3
"""Recover, validate, and label application links after the feed is merged.

Upstream aggregators and GitHub repositories are discovery sources, not ideal
application destinations. Yartchives only upgrades a link to "direct" when it
can recover an employer/ATS URL with high confidence. Ambiguous intermediary
pages remain "View listing" rather than guessing at an application URL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_feed as bf  # noqa: E402
from workday_inspector import UnsupportedWorkdayUrl, derive_cxs_endpoint  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_PATH = ROOT / "data" / "listings.json"
SOURCES_PATH = ROOT / "sources.json"
APPLYGUY_JSON = "https://raw.githubusercontent.com/ApplyGuy/2027-Internships/main/data/internships.json"
TIMEOUT = 12
VALIDATION_TTL_HOURS = 24
LINK_VALIDATION_VERSION = 2
MAX_VALIDATIONS_PER_RUN = 750
NETWORK_WORKERS = 24
USER_AGENT = "Yartchives/1.0 link-repair (+https://github.com/kaamilbadami/yartchives)"
VALIDATED_LINK_ORIGINS = {"applyguy-feed", "source-feed", "redirect-resolved"}

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
SOURCE_HOSTS = {"github.com", "www.github.com", "raw.githubusercontent.com"}
DEAD_PAGE_PHRASES = (
    "the page you are looking for doesn't exist",
    "the page you are looking for does not exist",
    "page does not exist",
    "this job is no longer available",
    "this position is no longer available",
    "job is no longer available",
    "job not found",
    "position has been filled",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
    return bool(is_http_url(value) and urlparse(value).netloc.lower() in AGGREGATOR_HOSTS)


def is_workday_job_page(value: str | None) -> bool:
    if not is_http_url(value):
        return False
    parsed = urlparse(str(value))
    host = (parsed.hostname or "").lower()
    path = parsed.path.casefold()
    return bool(
        re.fullmatch(r"[^.]+\.wd\d+\.myworkdayjobs\.com", host)
        and ("/job/" in path or "/details/" in path)
        and not path.rstrip("/").endswith("/apply")
    )


def listing_cache_key(value: str | None) -> str:
    if not is_http_url(value):
        return ""
    parsed = urlparse(value)
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def job_signature(job: dict[str, Any]) -> tuple[str, str, str]:
    return compact(job.get("company")), norm(job.get("title")), norm(job.get("location"))


def company_title_key(job: dict[str, Any]) -> tuple[str, str]:
    return compact(job.get("company")), norm(job.get("title"))


def applyguy_indexes(payload: dict[str, Any]) -> tuple[dict[tuple[str, str], str], dict[str, list[str]]]:
    exact_sets: dict[tuple[str, str], set[str]] = {}
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
            exact_sets.setdefault((company, title), set()).add(direct)
        if title:
            by_title.setdefault(title, []).append(direct)
    exact = {key: next(iter(values)) for key, values in exact_sets.items() if len(values) == 1}
    return exact, by_title


def choose_applyguy_direct(
    job: dict[str, Any],
    exact: dict[tuple[str, str], str],
    by_title: dict[str, list[str]],
) -> str | None:
    title = norm(job.get("title"))
    company = compact(job.get("company"))
    if company and title and (company, title) in exact:
        return exact[(company, title)]
    candidates = list(dict.fromkeys(by_title.get(title, []))) if title else []
    return candidates[0] if len(candidates) == 1 else None


def source_direct_indexes(
    parsed_jobs: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, str], str], dict[tuple[str, str], str]]:
    exact_sets: dict[tuple[str, str, str], set[str]] = {}
    company_title_sets: dict[tuple[str, str], set[str]] = {}
    for job in parsed_jobs:
        if not isinstance(job, dict):
            continue
        direct = job.get("url")
        if not is_direct_application_url(direct):
            continue
        exact_sets.setdefault(job_signature(job), set()).add(direct)
        company_title_sets.setdefault(company_title_key(job), set()).add(direct)
    exact = {key: next(iter(values)) for key, values in exact_sets.items() if len(values) == 1}
    company_title = {
        key: next(iter(values)) for key, values in company_title_sets.items() if len(values) == 1
    }
    return exact, company_title


def choose_source_direct(
    job: dict[str, Any],
    exact: dict[tuple[str, str, str], str],
    company_title: dict[tuple[str, str], str],
) -> str | None:
    return exact.get(job_signature(job)) or company_title.get(company_title_key(job))


def fetch_applyguy_payload() -> dict[str, Any] | None:
    try:
        response = requests.get(APPLYGUY_JSON, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ApplyGuy feed is not an object")
        return payload
    except Exception as exc:
        print(f"warning: ApplyGuy direct-link enrichment unavailable: {exc}", file=sys.stderr)
        return None


def fetch_source_direct_jobs() -> list[dict[str, Any]]:
    """Re-read markdown sources and recover their actual Apply-column URLs.

    SpeedyApply labels that column "Posting", which the generic feed parser did
    not recognize. Normalizing only that header lets us recover its employer
    links while retaining the GitHub repository merely as provenance.
    """
    try:
        sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"warning: source config unavailable for link enrichment: {exc}", file=sys.stderr)
        return []

    reference = now_utc()
    parsed: list[dict[str, Any]] = []
    for source in sources:
        if source.get("kind") != "markdown":
            continue
        try:
            response = requests.get(source["url"], headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            response.raise_for_status()
            text = response.text
            if source.get("key") == "speedyapply":
                text = re.sub(r"\|\s*Posting\s*\|", "| Apply |", text, flags=re.I)
            parsed.extend(bf.parse_markdown(text, source, reference))
        except Exception as exc:
            print(f"warning: direct-link source refresh failed for {source.get('name')}: {exc}", file=sys.stderr)
    return parsed


def old_resolution_cache(old_doc: dict[str, Any]) -> dict[str, str]:
    cache: dict[str, str] = {}
    for job in old_doc.get("jobs", []) if isinstance(old_doc, dict) else []:
        if not isinstance(job, dict):
            continue
        origin = job.get("resolved_from_url")
        direct = job.get("url")
        key = listing_cache_key(origin)
        if key and is_direct_application_url(direct) and job.get("link_status") != "dead":
            cache[key] = direct
    return cache


def candidate_from_zapply_slug(value: str) -> str | None:
    """Infer only ATS formats whose public URL is deterministic from the slug."""
    parsed = urlparse(value)
    if parsed.netloc.lower() not in {"zapply.jobs", "www.zapply.jobs"}:
        return None
    slug = parsed.path.rstrip("/").split("/")[-1]

    match = re.fullmatch(r"greenhouse-(.+)-(\d+)", slug, flags=re.I)
    if match:
        board, job_id = match.groups()
        return f"https://job-boards.greenhouse.io/{board}/jobs/{job_id}"

    match = re.fullmatch(r"ashby-(.+)-([0-9a-fA-F-]{32,36})", slug)
    if match:
        board, job_id = match.groups()
        return f"https://jobs.ashbyhq.com/{board}/{job_id}"

    match = re.fullmatch(r"lever-(.+)-([0-9a-fA-F-]{32,36})", slug)
    if match:
        company, job_id = match.groups()
        return f"https://jobs.lever.co/{company}/{job_id}"

    return None


def validate_candidate_once(value: str | None) -> str | None:
    if not is_direct_application_url(value):
        return None
    try:
        response = requests.get(
            value,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        try:
            if response.status_code in {404, 410}:
                return None
            final = response.url or value
            return final if is_direct_application_url(final) else None
        finally:
            response.close()
    except requests.RequestException:
        return None


def resolve_intermediary_url(value: str) -> str | None:
    """Resolve an intermediary only when the destination is unambiguous.

    Safe cases are a real HTTP redirect from the exact listing URL or a
    deterministic ATS URL encoded in the Zapply slug. We deliberately do not
    scrape a generic aggregator page for the first link that looks like an ATS;
    those pages contain many jobs and doing that can attach the wrong employer's
    application URL to a listing.
    """
    if not is_listing_url(value):
        return None
    try:
        response = requests.get(
            value,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        try:
            if response.status_code not in {404, 410} and response.history:
                final = response.url
                if is_direct_application_url(final):
                    return final
        finally:
            response.close()
    except requests.RequestException:
        pass

    inferred = candidate_from_zapply_slug(value)
    return validate_candidate_once(inferred)


def resolve_listing_urls(urls: list[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    unique = list(dict.fromkeys(url for url in urls if is_listing_url(url)))
    if not unique:
        return resolved
    with ThreadPoolExecutor(max_workers=NETWORK_WORKERS) as pool:
        futures = {pool.submit(resolve_intermediary_url, url): url for url in unique}
        for future in as_completed(futures):
            url = futures[future]
            try:
                direct = future.result()
            except Exception:
                direct = None
            if direct and is_direct_application_url(direct):
                resolved[listing_cache_key(url)] = direct
    return resolved


def repair_document(
    doc: dict[str, Any],
    applyguy_payload: dict[str, Any] | None = None,
    source_exact: dict[tuple[str, str, str], str] | None = None,
    source_company_title: dict[tuple[str, str], str] | None = None,
    resolved_urls: dict[str, str] | None = None,
    old_doc: dict[str, Any] | None = None,
) -> dict[str, int]:
    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Feed does not contain a jobs list")

    apply_exact: dict[tuple[str, str], str] = {}
    apply_by_title: dict[str, list[str]] = {}
    if applyguy_payload:
        apply_exact, apply_by_title = applyguy_indexes(applyguy_payload)

    source_exact = source_exact or {}
    source_company_title = source_company_title or {}
    resolved_urls = resolved_urls or {}
    old_jobs = {
        row.get("id"): row
        for row in (old_doc or {}).get("jobs", [])
        if isinstance(row, dict) and row.get("id")
    }

    stats = {
        "applyguy_repaired": 0,
        "source_repaired": 0,
        "intermediary_resolved": 0,
        "known_dead_suppressed": 0,
        "changed": 0,
    }

    for job in jobs:
        if not isinstance(job, dict):
            continue
        before = (job.get("url"), job.get("listing_url"), job.get("link_kind"), job.get("resolved_from_url"))
        source_keys = set(job.get("source_keys") or [])
        current = job.get("url") or ""
        listing = job.get("listing_url") if is_listing_url(job.get("listing_url")) else None
        if not listing and is_listing_url(current):
            listing = current

        prior = old_jobs.get(job.get("id")) or {}
        if is_direct_application_url(current) and prior.get("url") == current and prior.get("link_status") == "dead":
            current = ""
            job["url"] = ""
            stats["known_dead_suppressed"] += 1

        origin = None
        if not is_direct_application_url(current) and "applyguy" in source_keys and apply_exact:
            repaired = choose_applyguy_direct(job, apply_exact, apply_by_title)
            if repaired:
                current = repaired
                job["url"] = repaired
                origin = "applyguy-feed"
                stats["applyguy_repaired"] += 1

        if not is_direct_application_url(current):
            repaired = choose_source_direct(job, source_exact, source_company_title)
            if repaired:
                current = repaired
                job["url"] = repaired
                origin = "source-feed"
                stats["source_repaired"] += 1

        if not is_direct_application_url(current) and listing:
            repaired = resolved_urls.get(listing_cache_key(listing))
            if repaired and is_direct_application_url(repaired):
                current = repaired
                job["url"] = repaired
                job["resolved_from_url"] = listing
                origin = "redirect-resolved"
                stats["intermediary_resolved"] += 1

        if is_direct_application_url(current):
            job["link_kind"] = "employer_job" if is_workday_job_page(current) else "direct"
            job.pop("listing_url", None)
            if origin:
                job["link_origin"] = origin
            elif prior.get("url") == current and prior.get("link_origin"):
                job["link_origin"] = prior.get("link_origin")
            if prior.get("url") == current:
                for key in ("link_status", "link_checked_at"):
                    if prior.get(key):
                        job[key] = prior[key]
                if prior.get("resolved_from_url") and not job.get("resolved_from_url"):
                    job["resolved_from_url"] = prior["resolved_from_url"]
        else:
            job["url"] = ""
            if listing:
                job["listing_url"] = listing
                job["link_kind"] = "listing"
            else:
                job.pop("listing_url", None)
                job["link_kind"] = "source"

        after = (job.get("url"), job.get("listing_url"), job.get("link_kind"), job.get("resolved_from_url"))
        if before != after:
            stats["changed"] += 1

    return stats


def checked_recently(job: dict[str, Any], reference: datetime) -> bool:
    raw = job.get("link_checked_at")
    if not raw:
        return False
    try:
        checked = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return reference - checked < timedelta(hours=VALIDATION_TTL_HOURS)
    except ValueError:
        return False


def should_validate_direct_link(job: dict[str, Any]) -> bool:
    """Validate only links presented as final application destinations."""
    if job.get("link_kind") != "direct" or not is_direct_application_url(job.get("url")):
        return False
    if job.get("link_origin") in VALIDATED_LINK_ORIGINS:
        return True
    return (
        job.get("opportunity_type") == "internship"
        and "cs" in (job.get("profiles") or [])
    )


def read_html_prefix(response: requests.Response, limit: int = 64_000) -> str:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=16_384):
        if not chunk:
            continue
        remaining = limit - size
        if remaining <= 0:
            break
        chunks.append(chunk[:remaining])
        size += min(len(chunk), remaining)
        if size >= limit:
            break
    encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace")


def validate_workday_url(value: str) -> tuple[str, str] | None:
    """Validate a direct Workday job through the public CXS endpoint.

    Workday's browser shell can return HTTP 200 for stale job slugs. The CXS
    endpoint is the authoritative job resource and reliably distinguishes a
    live posting from a stale path.
    """
    try:
        endpoint = derive_cxs_endpoint(value)
    except UnsupportedWorkdayUrl:
        return None

    try:
        response = requests.get(
            endpoint["endpoint_url"],
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        try:
            if response.status_code in {404, 410}:
                return "dead", value
            if response.status_code in {401, 403, 429} or response.status_code >= 500:
                return "unknown", value
            if not 200 <= response.status_code < 300:
                return "unknown", value
            payload = response.json()
            info = payload.get("jobPostingInfo") if isinstance(payload, dict) else None
            if not isinstance(info, dict):
                return "unknown", value
            if info.get("canApply") is False or info.get("posted") is False:
                return "dead", value
            if not urlparse(value).path.rstrip("/").casefold().endswith("/apply"):
                # A live Workday job page is not a verified application destination.
                # Force provider recovery to resolve the current requisition path.
                return "dead", value
            return "ok", value
        finally:
            response.close()
    except (requests.RequestException, ValueError):
        return "unknown", value


def validate_direct_url(value: str) -> tuple[str, str]:
    """Return (status, final_url), where status is ok, dead, or unknown."""
    workday = validate_workday_url(value)
    if workday is not None:
        return workday
    try:
        response = requests.get(
            value,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        try:
            final = response.url or value
            if response.status_code in {404, 410}:
                return "dead", final
            if response.status_code in {401, 403, 429} or response.status_code >= 500:
                return "unknown", final
            if 200 <= response.status_code < 400:
                if "html" in response.headers.get("content-type", "").lower():
                    snippet = read_html_prefix(response).lower()
                    if any(phrase in snippet for phrase in DEAD_PAGE_PHRASES):
                        return "dead", final
                return "ok", final
            return "unknown", final
        finally:
            response.close()
    except requests.RequestException:
        return "unknown", value


def downgrade_dead_link(job: dict[str, Any]) -> None:
    dead_url = job.get("url") or ""
    if dead_url:
        job["dead_url"] = dead_url
    fallback = job.get("resolved_from_url")
    job["url"] = ""
    if is_listing_url(fallback):
        job["listing_url"] = fallback
        job["link_kind"] = "listing"
    else:
        job.pop("listing_url", None)
        job["link_kind"] = "source"


def validate_repaired_links(doc: dict[str, Any], old_doc: dict[str, Any]) -> dict[str, int]:
    jobs = [job for job in doc.get("jobs", []) if isinstance(job, dict)]
    old_by_id = {
        job.get("id"): job
        for job in old_doc.get("jobs", []) if isinstance(job, dict) and job.get("id")
    }
    reference = now_utc()
    targets: list[dict[str, Any]] = []


    for job in jobs:
        prior = old_by_id.get(job.get("id")) or {}
        if not should_validate_direct_link(job):
            # If we don't validate it, at least carry over the old validation status if the URL hasn't changed
            if prior.get("url") == job.get("url") and prior.get("link_status"):
                job["link_status"] = prior.get("link_status", "unknown")
                if prior.get("link_checked_at"):
                    job["link_checked_at"] = prior.get("link_checked_at")
                if prior.get("link_validation_version"):
                    job["link_validation_version"] = prior.get("link_validation_version")
            continue

        if (
            prior.get("url") == job.get("url")
            and prior.get("link_validation_version") == LINK_VALIDATION_VERSION
            and checked_recently(prior, reference)
        ):

            job["link_status"] = prior.get("link_status", "unknown")
            job["link_checked_at"] = prior.get("link_checked_at")
            job["link_validation_version"] = LINK_VALIDATION_VERSION
            continue
        targets.append(job)

    targets.sort(key=lambda job: ("applyguy" not in set(job.get("source_keys") or []), job.get("id") or ""))
    targets = targets[:MAX_VALIDATIONS_PER_RUN]
    stats = {"checked": 0, "ok": 0, "dead": 0, "unknown": 0}

    with ThreadPoolExecutor(max_workers=NETWORK_WORKERS) as pool:
        futures = {pool.submit(validate_direct_url, job["url"]): job for job in targets}
        for future in as_completed(futures):
            job = futures[future]
            try:
                status, final = future.result()
            except Exception:
                status, final = "unknown", job.get("url") or ""
            stats["checked"] += 1
            stats[status] += 1
            job["link_status"] = status
            job["link_checked_at"] = iso(reference)
            job["link_validation_version"] = LINK_VALIDATION_VERSION
            if status == "dead":
                downgrade_dead_link(job)
            elif is_direct_application_url(final):
                job["url"] = final

    return stats


def count_link_kinds(doc: dict[str, Any]) -> dict[str, int]:
    counts = {"direct": 0, "listing": 0, "source": 0}
    for job in doc.get("jobs", []):
        if isinstance(job, dict) and job.get("link_kind") in counts:
            counts[job["link_kind"]] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=str(DEFAULT_PATH))
    parser.add_argument("--old-feed", type=Path)
    parser.add_argument("--offline", action="store_true", help="skip network enrichment and only normalize existing URLs")
    args = parser.parse_args()

    path = Path(args.path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    old_doc: dict[str, Any] = {}
    if args.old_feed and args.old_feed.exists():
        try:
            old_doc = json.loads(args.old_feed.read_text(encoding="utf-8"))
        except Exception:
            old_doc = {}

    payload = None
    source_exact: dict[tuple[str, str, str], str] = {}
    source_company_title: dict[tuple[str, str], str] = {}
    resolved = old_resolution_cache(old_doc)

    if not args.offline:
        payload = fetch_applyguy_payload()
        source_jobs = fetch_source_direct_jobs()
        source_exact, source_company_title = source_direct_indexes(source_jobs)

        apply_exact, apply_by_title = applyguy_indexes(payload or {})
        unresolved: list[str] = []
        for job in doc.get("jobs", []):
            if not isinstance(job, dict):
                continue
            current = job.get("url") or ""
            listing = job.get("listing_url") if is_listing_url(job.get("listing_url")) else None
            if not listing and is_listing_url(current):
                listing = current
            if not listing or listing_cache_key(listing) in resolved:
                continue
            if "applyguy" in set(job.get("source_keys") or []) and choose_applyguy_direct(job, apply_exact, apply_by_title):
                continue
            if choose_source_direct(job, source_exact, source_company_title):
                continue
            unresolved.append(listing)

        live_resolved = resolve_listing_urls(unresolved)
        resolved.update(live_resolved)
        print(f"Intermediary resolver: {len(live_resolved)} newly resolved; {len(resolved) - len(live_resolved)} cached")

    stats = repair_document(
        doc,
        payload,
        source_exact=source_exact,
        source_company_title=source_company_title,
        resolved_urls=resolved,
        old_doc=old_doc,
    )

    validation = {"checked": 0, "ok": 0, "dead": 0, "unknown": 0}
    if not args.offline:
        validation = validate_repaired_links(doc, old_doc)

    counts = count_link_kinds(doc)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "Link repair: "
        f"{counts['direct']} direct, {counts['listing']} listing-only, {counts['source']} source-only; "
        f"ApplyGuy repaired={stats['applyguy_repaired']}, source-feed repaired={stats['source_repaired']}, "
        f"intermediaries resolved={stats['intermediary_resolved']}"
    )
    print(
        "Link validation: "
        f"checked={validation['checked']}, ok={validation['ok']}, dead={validation['dead']}, unknown={validation['unknown']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
