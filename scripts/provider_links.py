#!/usr/bin/env python3
"""Recover official application URLs for remaining intermediary listings.

This pass is deliberately provider-specific. It only upgrades a listing when the
upstream identifier can be tied to one official ATS/job URL. Ambiguous results
stay as View listing rather than risking a wrong Apply button.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import repair_links as links  # noqa: E402

TIMEOUT = 12
WORKERS = 14
USER_AGENT = "Yartchives/1.0 provider-link-recovery (+https://github.com/kaamilbadami/yartchives)"
WORKDAY_SHARDS = ("wd1", "wd2", "wd3", "wd5", "wd10", "wd12")
WORKDAY_REQ_RE = re.compile(r"-(JR-?\d+|REQ-?\d+|WD-?\d+|R-?\d+|\d{6,})$", re.I)
DIRECT_WORKDAY_REQ_RE = re.compile(r"(?:_|-)(JR-?\d+|REQ-?\d+|WD-?\d+|R-?\d+|\d{6,})$", re.I)
LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()


def zapply_slug(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.netloc.lower() not in {"zapply.jobs", "www.zapply.jobs"}:
        return ""
    return parsed.path.rstrip("/").split("/")[-1]


def parse_workday_slug(value: str | None) -> tuple[str, str, str] | None:
    slug = zapply_slug(value)
    if not slug.lower().startswith("workday-"):
        return None
    body = slug[len("workday-"):]
    match = WORKDAY_REQ_RE.search(body)
    if not match:
        return None
    req_id = match.group(1)
    prefix = body[: match.start()]
    parts = [part for part in prefix.split("-") if part]
    if len(parts) < 2:
        return None
    tenant = parts[0]
    site_hint = "-".join(parts[1:])
    return tenant, site_hint, req_id


def workday_req_id_from_url(value: str | None) -> str:
    """Extract a requisition-like ID from a direct Workday job URL."""
    if not value:
        return ""
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    if not re.fullmatch(r"[^.]+\.wd\d+\.myworkdayjobs\.com", host):
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return ""
    tail = parts[-1]
    match = DIRECT_WORKDAY_REQ_RE.search(tail)
    return match.group(1) if match else ""


def workday_config_from_url(value: str | None) -> tuple[str, str, str] | None:
    if not value:
        return None
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    match = re.fullmatch(r"([^.]+)\.(wd\d+)\.myworkdayjobs\.com", host)
    if not match:
        return None
    tenant = match.group(1)
    parts = [part for part in parsed.path.split("/") if part]
    if parts and LOCALE_RE.match(parts[0]):
        parts = parts[1:]
    if not parts:
        return None
    try:
        job_i = next(i for i, part in enumerate(parts) if part.lower() == "job")
    except StopIteration:
        return None
    if job_i < 1:
        return None
    site = parts[job_i - 1]
    return tenant, host, site


def build_workday_registry(doc: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    registry: dict[str, set[tuple[str, str]]] = {}
    for job in doc.get("jobs", []):
        if not isinstance(job, dict):
            continue
        config = workday_config_from_url(job.get("url"))
        if not config:
            continue
        tenant, host, site = config
        registry.setdefault(tenant, set()).add((host, site))
    return {tenant: sorted(values) for tenant, values in registry.items()}


def req_compact(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def workday_posting_match(posting: dict[str, Any], req_id: str) -> bool:
    path = str(posting.get("externalPath") or "")
    target = req_compact(req_id)
    if not target or target not in req_compact(path):
        return False
    return True


def query_workday(host: str, tenant: str, site: str, req_id: str) -> str | None:
    endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    try:
        response = requests.post(
            endpoint,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": req_id},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    matches = [
        row for row in payload.get("jobPostings", [])
        if isinstance(row, dict) and workday_posting_match(row, req_id)
    ]
    if len(matches) != 1:
        return None
    external_path = str(matches[0].get("externalPath") or "")
    if not external_path.startswith("/"):
        return None

    candidates = [
        f"https://{host}/{site}{external_path.rstrip('/')}/apply",
        f"https://{host}/en-US/{site}{external_path.rstrip('/')}/apply",
    ]
    for candidate in candidates:
        final = links.validate_candidate_once(candidate)
        if final:
            return final
    return None


def workday_site_variants(site_hint: str) -> list[str]:
    variants = [site_hint, site_hint.replace("-", "_")]
    # A few Workday tenants use title-cased underscore site IDs. This is only a
    # fallback; registry-derived exact site IDs are always attempted first.
    title_underscore = "_".join(part[:1].upper() + part[1:] for part in site_hint.split("-"))
    variants.append(title_underscore)
    return list(dict.fromkeys(v for v in variants if v))


def recover_stale_workday_direct(value: str | None) -> str | None:
    """Recover a canonical live URL for the same Workday requisition."""
    config = workday_config_from_url(value)
    req_id = workday_req_id_from_url(value)
    if not config or not req_id:
        return None
    tenant, host, site = config
    return query_workday(host, tenant, site, req_id)


def resolve_workday(value: str, registry: dict[str, list[tuple[str, str]]]) -> str | None:
    parsed = parse_workday_slug(value)
    if not parsed:
        return None
    tenant, site_hint, req_id = parsed

    configs = list(registry.get(tenant.lower(), []))
    seen = set(configs)
    for shard in WORKDAY_SHARDS:
        host = f"{tenant.lower()}.{shard}.myworkdayjobs.com"
        for site in workday_site_variants(site_hint):
            if (host, site) not in seen:
                configs.append((host, site))
                seen.add((host, site))

    for host, site in configs:
        direct = query_workday(host, tenant.lower(), site, req_id)
        if direct:
            return direct
    return None


def nested_scalars(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            out.extend(nested_scalars(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(nested_scalars(child))
    elif isinstance(value, (str, int, float)):
        out.append(str(value))
    return out


def position_id(position: dict[str, Any]) -> str:
    for key in ("id", "position_id", "positionId", "pid"):
        value = position.get(key)
        if value is not None and re.fullmatch(r"\d{10,}", str(value)):
            return str(value)
    return ""


def resolve_caci(job: dict[str, Any], value: str) -> str | None:
    parsed = parse_workday_slug(value)
    if not parsed or compact(job.get("company")) != "caci":
        return None
    _, _, req_id = parsed
    endpoint = "https://searchcareers.caci.com/api/pcsx/search"
    try:
        response = requests.get(
            endpoint,
            params={"domain": "caci.com", "start": 0, "num": 10, "query": req_id, "location": ""},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    positions = payload.get("positions") or payload.get("results") or []
    exact: list[dict[str, Any]] = []
    target = req_compact(req_id)
    for position in positions:
        if not isinstance(position, dict):
            continue
        scalars = {req_compact(item) for item in nested_scalars(position)}
        if target in scalars:
            exact.append(position)
    if len(exact) != 1:
        return None
    pid = position_id(exact[0])
    if not pid:
        return None
    candidate = f"https://searchcareers.caci.com/careers/job/{pid}?domain=caci.com"
    final = links.validate_candidate_once(candidate)
    return final


def resolve_google(value: str) -> str | None:
    slug = zapply_slug(value)
    match = re.fullmatch(r"google-(\d+)", slug, flags=re.I)
    if not match:
        return None
    return links.validate_candidate_once(
        f"https://www.google.com/about/careers/applications/jobs/results/{match.group(1)}"
    )


def resolve_bytedance(value: str) -> str | None:
    slug = zapply_slug(value)
    match = re.fullmatch(r"bytedance-(\d+)", slug, flags=re.I)
    if not match:
        return None
    job_id = match.group(1)
    for candidate in (
        f"https://jobs.bytedance.com/en/position/{job_id}/detail",
        f"https://jobs.bytedance.com/campus/position/{job_id}/detail",
    ):
        final = links.validate_candidate_once(candidate)
        if final:
            return final
    return None


def resolve_smartrecruiters(value: str) -> str | None:
    slug = zapply_slug(value)
    match = re.fullmatch(r"sr-(.+)-(\d+)", slug, flags=re.I)
    if not match:
        return None
    company, job_id = match.groups()
    candidate = f"https://jobs.smartrecruiters.com/{company}/{job_id}"
    return links.validate_candidate_once(candidate)


STRONG_JOBRIGHT_KEYS = {
    "applyurl", "applicationurl", "externalapplyurl", "originalapplyurl", "directapplyurl",
}
MEDIUM_JOBRIGHT_KEYS = {
    "joburl", "sourceurl", "externalurl", "originalurl", "postingurl",
}


def decoded_url(value: str) -> str:
    text = html.unescape(value)
    text = text.replace("\\/", "/")
    try:
        text = bytes(text, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        pass
    return text


def named_urls_from_object(value: Any, strong: set[str], medium: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            k = re.sub(r"[^a-z0-9]+", "", str(key).lower())
            if isinstance(child, str) and child.startswith(("http://", "https://")):
                if k in STRONG_JOBRIGHT_KEYS and links.is_direct_application_url(child):
                    strong.add(child)
                elif k in MEDIUM_JOBRIGHT_KEYS and links.probable_job_url(child):
                    medium.add(child)
            named_urls_from_object(child, strong, medium)
    elif isinstance(value, list):
        for child in value:
            named_urls_from_object(child, strong, medium)


def jobright_candidates_from_html(text: str) -> list[str]:
    strong: set[str] = set()
    medium: set[str] = set()

    # Parse embedded JSON blobs when possible.
    for raw in re.findall(r"<script[^>]*>(.*?)</script>", text, flags=re.I | re.S):
        raw = raw.strip()
        if not raw or raw[0] not in "[{":
            continue
        try:
            named_urls_from_object(json.loads(raw), strong, medium)
        except (ValueError, TypeError):
            pass

    key_pattern = "|".join(sorted(STRONG_JOBRIGHT_KEYS | MEDIUM_JOBRIGHT_KEYS, key=len, reverse=True))
    for match in re.finditer(
        rf"[\"'](?P<key>{key_pattern})[\"']\s*:\s*[\"'](?P<url>https?:\\?/\\?/[^\"']+)[\"']",
        text,
        flags=re.I,
    ):
        key = re.sub(r"[^a-z0-9]+", "", match.group("key").lower())
        url = decoded_url(match.group("url"))
        if key in STRONG_JOBRIGHT_KEYS and links.is_direct_application_url(url):
            strong.add(url)
        elif key in MEDIUM_JOBRIGHT_KEYS and links.probable_job_url(url):
            medium.add(url)

    if len(strong) == 1:
        return list(strong)
    if len(strong) > 1:
        return []
    return list(medium) if len(medium) == 1 else []


def resolve_jobright(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.netloc.lower() not in {"jobright.ai", "www.jobright.ai"} or "/jobs/info/" not in parsed.path:
        return None
    try:
        response = requests.get(
            value,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return None
        candidates = jobright_candidates_from_html(response.text[:2_000_000])
    except requests.RequestException:
        return None
    if len(candidates) != 1:
        return None
    return links.validate_candidate_once(candidates[0])


def resolve_one(job: dict[str, Any], registry: dict[str, list[tuple[str, str]]]) -> tuple[str, str] | None:
    employer_job_url = job.get("url") or ""
    if job.get("link_kind") == "employer_job" and workday_config_from_url(employer_job_url):
        direct = recover_stale_workday_direct(employer_job_url)
        if direct:
            return direct, "workday-employer-job"

    dead_url = job.get("dead_url") or ""
    if workday_config_from_url(dead_url) and workday_req_id_from_url(dead_url):
        direct = recover_stale_workday_direct(dead_url)
        if direct:
            return direct, "stale-workday-requisition"

    listing = job.get("listing_url") or ""
    if not links.is_listing_url(listing):
        return None

    host = urlparse(listing).netloc.lower()
    direct = None
    origin = ""
    if host in {"zapply.jobs", "www.zapply.jobs"}:
        slug = zapply_slug(listing).lower()
        if slug.startswith("google-"):
            direct, origin = resolve_google(listing), "zapply-google"
        elif slug.startswith("bytedance-"):
            direct, origin = resolve_bytedance(listing), "zapply-bytedance"
        elif slug.startswith("sr-"):
            direct, origin = resolve_smartrecruiters(listing), "zapply-smartrecruiters"
        elif slug.startswith("workday-"):
            direct = resolve_caci(job, listing)
            origin = "zapply-eightfold" if direct else ""
            if not direct:
                direct = resolve_workday(listing, registry)
                origin = "zapply-workday" if direct else ""
    elif host in {"jobright.ai", "www.jobright.ai"}:
        direct, origin = resolve_jobright(listing), "jobright-structured"

    if direct and links.is_direct_application_url(direct):
        return direct, origin
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/listings.json")
    args = parser.parse_args()

    path = Path(args.path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    registry = build_workday_registry(doc)
    targets = [
        job for job in doc.get("jobs", [])
        if isinstance(job, dict)
        and (
            (job.get("link_kind") == "listing" and links.is_listing_url(job.get("listing_url")))
            or (
                job.get("link_kind") == "employer_job"
                and workday_config_from_url(job.get("url"))
            )
            or (
                job.get("link_kind") == "source"
                and workday_config_from_url(job.get("dead_url"))
                and workday_req_id_from_url(job.get("dead_url"))
            )
        )
    ]

    resolved: list[tuple[dict[str, Any], str, str]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(resolve_one, job, registry): job for job in targets}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                print(f"warning: provider resolver failed for {job.get('company')}: {exc}", file=sys.stderr)
                result = None
            if result:
                direct, origin = result
                resolved.append((job, direct, origin))

    by_origin: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for job, direct, origin in resolved:
        listing = job.get("listing_url") or ""
        status, final = links.validate_direct_url(direct)
        if status == "dead":
            continue
        if listing:
            job["resolved_from_url"] = listing
        job["url"] = final if links.is_direct_application_url(final) else direct
        job.pop("listing_url", None)
        job["link_kind"] = "direct"
        job["link_origin"] = origin
        job["link_status"] = status
        job["link_checked_at"] = now
        by_origin[origin] = by_origin.get(origin, 0) + 1

    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    detail = ", ".join(f"{key}={value}" for key, value in sorted(by_origin.items())) or "none"
    print(f"Provider link recovery: {sum(by_origin.values())} upgraded ({detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
