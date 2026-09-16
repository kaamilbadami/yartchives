#!/usr/bin/env python3
"""Compare externally discovered opportunities with the Yartchives feed.

The audit is offline: collect opportunities from LinkedIn, Handshake, web
search, or employer sites, then pass JSON/JSONL/CSV here. Discovery surfaces
are evidence inputs, not production scraping targets.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_feed import canonical_url, norm  # noqa: E402

FEED = ROOT / "data/listings.json"
SOURCES = ROOT / "sources.json"
DIRECT = ROOT / "direct_sources.json"
VISIBLE_TYPES = {"internship", "co-op", "student"}
STATUSES = (
    "already_in_yartchives",
    "filtered_or_misclassified",
    "duplicate_resolution_issue",
    "configured_source_miss",
    "employer_exists_but_listing_missing",
    "source_not_covered",
    "unknown",
)
REPRESENTED_STATUSES = {
    "already_in_yartchives",
    "filtered_or_misclassified",
    "duplicate_resolution_issue",
}
MISSING_STATUSES = set(STATUSES) - REPRESENTED_STATUSES
DISCOVERY_SURFACES = {"linkedin", "handshake", "indeed", "glassdoor", "ziprecruiter"}
ATS_HINTS = (
    "myworkdayjobs.com",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "oraclecloud.com",
)
ACTION_PRIORITY = {
    "configured_source_miss": 1,
    "filtered_or_misclassified": 1,
    "source_not_covered": 2,
    "employer_exists_but_listing_missing": 2,
    "duplicate_resolution_issue": 3,
    "unknown": 4,
    "already_in_yartchives": 9,
}


def first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[;,]", str(value)) if item.strip()]


def normalize_profiles(values: Any) -> list[str]:
    return list(dict.fromkeys(value.strip().lower() for value in as_list(values) if value.strip()))


def normalize_states(values: Any) -> list[str]:
    return list(dict.fromkeys(value.strip().upper() for value in as_list(values) if value.strip()))


def company_key(value: str) -> str:
    text = norm(value)
    suffix = r"(?:inc|incorporated|llc|ltd|limited|corp|corporation|company|co)"
    while re.search(rf"(?:^|\s){suffix}$", text):
        text = re.sub(rf"(?:^|\s){suffix}$", "", text).strip()
    return text


def company_aliases(value: str) -> set[str]:
    """Generate conservative aliases for configured direct-employer labels."""
    raw = re.sub(r"\s*\(direct\)\s*$", "", value or "", flags=re.I).strip()
    if not raw:
        return set()
    aliases = {company_key(raw)}
    for piece in re.split(r"\s+/\s+|\s+\|\s+", raw):
        key = company_key(piece)
        if key:
            aliases.add(key)
    return {alias for alias in aliases if alias}


def signature(row: dict[str, Any]) -> str:
    return "|".join(
        (
            company_key(first(row, "company", "employer", "organization")),
            norm(first(row, "title", "role", "position")),
            norm(first(row, "location", "locations")),
        )
    )


def has_strong_signature(row: dict[str, Any]) -> bool:
    return all(
        (
            company_key(first(row, "company", "employer", "organization")),
            norm(first(row, "title", "role", "position")),
            norm(first(row, "location", "locations")),
        )
    )


def host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_discovery_surface(value: str) -> bool:
    text = norm(value)
    hostname = host(value)
    return any(surface in text or surface in hostname for surface in DISCOVERY_SURFACES)


def url_identity(url: str) -> tuple[str, str] | None:
    """Conservative provider identity used to detect likely requisition matches."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    hostname = parsed.netloc.lower().removeprefix("www.")
    for key, value in parse_qsl(parsed.query):
        if key.lower() in {"jobid", "job_id", "gh_jid", "jid", "requisitionid", "reqid"} and value:
            return hostname, f"{key.lower()}={norm(value)}"
    tail = re.sub(r"/+", "/", parsed.path).rstrip("/").split("/")[-1].lower()
    if hostname and len(tail) >= 4 and re.search(r"\d", tail):
        return hostname, tail
    return None


def authoritative_identity(url: str) -> tuple[str, str] | None:
    if not url or is_discovery_surface(url):
        return None
    return url_identity(url)


def _json_payload(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return [dict(row) for row in csv.DictReader(file)]
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        out = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"line {line_number}: expected object")
            out.append(row)
        return out

    payload = _json_payload(path)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = next(
            (
                payload[key]
                for key in ("discoveries", "jobs", "listings", "opportunities")
                if isinstance(payload.get(key), list)
            ),
            None,
        )
        if rows is None:
            raise ValueError("JSON must be a list or contain discoveries/jobs/listings/opportunities")
    else:
        raise ValueError("JSON audit input must contain objects")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("every discovery must be an object")
    return [dict(row) for row in rows]


def load_audit_input(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load discoveries plus optional audit metadata from a self-describing JSON sample."""
    rows = load_rows(path)
    metadata: dict[str, Any] = {
        "name": "",
        "collected_at": "",
        "notes": "",
        "scope": {"profiles": [], "states": []},
    }
    if path.suffix.lower() != ".json":
        return metadata, rows
    payload = _json_payload(path)
    if not isinstance(payload, dict):
        return metadata, rows

    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    metadata.update(
        {
            "name": first(payload, "name", "audit_name"),
            "collected_at": first(payload, "collected_at", "collection_date", "date"),
            "notes": str(payload.get("notes") or "").strip(),
            "scope": {
                "profiles": normalize_profiles(scope.get("profiles") or scope.get("profile")),
                "states": normalize_states(scope.get("states") or scope.get("state")),
            },
        }
    )
    return metadata, rows


def source_catalog(sources: Path, direct: Path) -> dict[str, set[str]]:
    catalog = {
        "keys": {"usajobs"},
        "names": {"usajobs"},
        "hosts": {"usajobs.gov", "data.usajobs.gov"},
        "source_hosts": {"usajobs.gov", "data.usajobs.gov"},
        "direct_hosts": set(),
        "companies": set(),
        "direct_companies": set(),
    }
    for path, is_direct in ((sources, False), (direct, True)):
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON list")
        for row in payload:
            if not isinstance(row, dict):
                continue
            if row.get("key"):
                catalog["keys"].add(norm(str(row["key"])))
            if row.get("name"):
                name = norm(re.sub(r"\s*\(direct\)\s*$", "", str(row["name"]), flags=re.I))
                if name:
                    catalog["names"].add(name)
            aliases = set()
            if row.get("company"):
                aliases |= company_aliases(str(row["company"]))
            if is_direct and row.get("name"):
                aliases |= company_aliases(str(row["name"]))
            catalog["companies"].update(aliases)
            if is_direct:
                catalog["direct_companies"].update(aliases)
            for field in ("url", "homepage", "api_url", "public_base"):
                hostname = host(str(row.get(field) or ""))
                if not hostname:
                    continue
                catalog["hosts"].add(hostname)
                catalog["direct_hosts" if is_direct else "source_hosts"].add(hostname)
    return catalog


def _catalog_values(catalog: dict[str, set[str]], key: str) -> set[str]:
    value = catalog.get(key)
    return value if isinstance(value, set) else set(value or [])


class Index:
    def __init__(self, jobs: list[dict[str, Any]]):
        self.jobs = jobs
        self.urls: defaultdict[str, list[int]] = defaultdict(list)
        self.ids: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
        self.sigs: defaultdict[str, list[int]] = defaultdict(list)
        self.companies: defaultdict[str, list[int]] = defaultdict(list)
        self.job_ids: dict[int, set[tuple[str, str]]] = defaultdict(set)
        for index, job in enumerate(jobs):
            company = company_key(str(job.get("company") or ""))
            if company:
                self.companies[company].append(index)
            if has_strong_signature(job):
                self.sigs[signature(job)].append(index)
            for value in (job.get("url"), job.get("listing_url"), job.get("apply_url")):
                if not value:
                    continue
                self.urls[canonical_url(str(value))].append(index)
                identity = authoritative_identity(str(value))
                if identity:
                    self.ids[identity].append(index)
                    self.job_ids[index].add(identity)

    def get(self, ids: list[int]) -> list[dict[str, Any]]:
        return [self.jobs[index] for index in dict.fromkeys(ids)]

    def identities(self, job: dict[str, Any]) -> set[tuple[str, str]]:
        out = set()
        for value in (job.get("url"), job.get("listing_url"), job.get("apply_url")):
            identity = authoritative_identity(str(value or ""))
            if identity:
                out.add(identity)
        return out


def compact(job: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "company",
        "title",
        "location",
        "url",
        "listing_url",
        "profiles",
        "states",
        "opportunity_type",
        "education_level",
        "source_keys",
        "link_kind",
        "posted_at",
    )
    return {key: job.get(key) for key in keys if job.get(key) not in (None, "", [])}


def expectations(row: dict[str, Any], profiles: list[str], states: list[str]) -> dict[str, Any]:
    raw_visible = row.get("expect_default_visible", True)
    visible = (
        raw_visible.strip().lower() not in {"0", "false", "no", "off"}
        if isinstance(raw_visible, str)
        else bool(raw_visible)
    )
    expected_profiles = profiles or normalize_profiles(
        row.get("expected_profiles") or row.get("expected_profile")
    )
    expected_states = states or normalize_states(row.get("expected_states") or row.get("expected_state"))
    expected_types = [value.lower() for value in as_list(
        row.get("expected_opportunity_types") or row.get("expected_opportunity_type")
    )]
    return {
        "profiles": expected_profiles,
        "states": expected_states,
        "opportunity_types": expected_types,
        "default_visible": visible,
    }


def surface_issues(job: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    issues = []
    job_profiles = {str(value).lower() for value in (job.get("profiles") or [])}
    job_states = {str(value).upper() for value in (job.get("states") or [])}
    for profile in expected["profiles"]:
        if profile.lower() not in job_profiles:
            issues.append(f"missing expected profile '{profile}'")
    for state in expected["states"]:
        if state.upper() not in job_states:
            issues.append(f"missing expected state '{state}'")
    opportunity_type = str(job.get("opportunity_type") or "").lower()
    if expected["opportunity_types"] and opportunity_type not in expected["opportunity_types"]:
        issues.append(
            f"opportunity_type '{opportunity_type or 'missing'}' does not match {expected['opportunity_types']}"
        )
    if expected["default_visible"]:
        if str(job.get("education_level") or "").lower() == "graduate-only":
            issues.append("graduate-only is hidden by the default undergrad filter")
        if opportunity_type and opportunity_type not in VISIBLE_TYPES:
            issues.append(f"opportunity_type '{opportunity_type}' is hidden by the default type filter")
    return issues


def similar(left: str, right: str) -> float:
    left, right = norm(left), norm(right)
    return SequenceMatcher(a=left, b=right).ratio() if left and right else 0.0


def _best_match(candidates: list[dict[str, Any]], expected: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    scored = sorted((len(surface_issues(job, expected)), pos, job) for pos, job in enumerate(candidates))
    _, _, job = scored[0]
    return job, surface_issues(job, expected)


def source_coverage(
    row: dict[str, Any], catalog: dict[str, set[str]], company: str
) -> tuple[bool | None, str]:
    source = first(row, "source", "source_name", "discovered_via")
    source_name = norm(source)
    source_key = norm(first(row, "source_key"))
    direct_url = first(row, "url", "apply_url", "listing_url")
    direct_host = host(direct_url)
    discovery_url = first(row, "source_url", "discovery_url")
    discovery_host = host(discovery_url)

    if company and company in _catalog_values(catalog, "direct_companies"):
        return True, "employer has a configured direct source"
    if direct_host and direct_host in _catalog_values(catalog, "direct_hosts"):
        return True, f"direct listing host '{direct_host}' is configured"
    if source_key and source_key in _catalog_values(catalog, "keys"):
        return True, f"source_key={source_key} is configured"
    if source_name and source_name in _catalog_values(catalog, "names"):
        return True, f"source={source_name} is configured"
    if direct_host and direct_host in _catalog_values(catalog, "source_hosts"):
        return True, f"listing host '{direct_host}' belongs to a configured upstream source"
    if discovery_host and discovery_host in _catalog_values(catalog, "hosts"):
        return True, f"discovery host '{discovery_host}' is configured"

    if source_name and any(surface in source_name for surface in DISCOVERY_SURFACES):
        return False, f"discovery surface '{source_name}' is audit-only and not ingested"
    if discovery_host and any(surface in discovery_host for surface in DISCOVERY_SURFACES):
        return False, f"discovery surface host '{discovery_host}' is audit-only and not ingested"
    if direct_host and any(hint in direct_host for hint in ATS_HINTS):
        return False, f"direct ATS host '{direct_host}' is not configured"
    if direct_host:
        return False, f"listing host '{direct_host}' is not configured"
    if source_name:
        return False, f"source '{source_name}' is not configured"
    return None, "no source metadata"


def classify(
    row: dict[str, Any],
    index: Index,
    catalog: dict[str, set[str]],
    profiles: list[str],
    states: list[str],
) -> dict[str, Any]:
    company_display = first(row, "company", "employer", "organization")
    title = first(row, "title", "role", "position")
    location = first(row, "location", "locations")
    url = first(row, "url", "apply_url", "listing_url")
    source = first(row, "source", "source_name", "discovered_via")
    observed_sources = as_list(row.get("_audit_observed_sources")) or ([source] if source else [])
    expected = expectations(row, profiles, states)
    base = {
        "company": company_display,
        "title": title,
        "location": location,
        "url": url,
        "source": source,
        "observed_sources": observed_sources,
        "observation_count": int(row.get("_audit_observation_count") or 1),
        "expected": expected,
    }

    exact_url_ids: list[int] = []
    if url:
        exact_url_ids += index.urls.get(canonical_url(url), [])
    if exact_url_ids:
        candidates = index.get(exact_url_ids)
        job, issues = _best_match(candidates, expected)
        if issues:
            return {
                **base,
                "status": "filtered_or_misclassified",
                "confidence": "high",
                "reason": "; ".join(issues),
                "matched_job": compact(job),
                "recommended_action": "Review profile/state/type enrichment or filter metadata.",
            }
        return {
            **base,
            "status": "already_in_yartchives",
            "confidence": "high",
            "reason": "matched by canonical application/listing URL",
            "matched_job": compact(job),
            "recommended_action": "No coverage fix needed.",
        }

    identity = authoritative_identity(url)
    if identity and index.ids.get(identity):
        job = index.get(index.ids[identity])[0]
        issues = surface_issues(job, expected)
        if issues:
            return {
                **base,
                "status": "filtered_or_misclassified",
                "confidence": "high",
                "reason": "; ".join(issues),
                "matched_job": compact(job),
                "recommended_action": "Fix filter/classification metadata; URL normalization also differs.",
            }
        return {
            **base,
            "status": "duplicate_resolution_issue",
            "confidence": "high",
            "reason": "same ATS/requisition identifier exists but canonical URLs differ",
            "matched_job": compact(job),
            "recommended_action": "Add provider-specific canonicalization/deduplication.",
        }

    signature_conflicts: list[dict[str, Any]] = []
    if has_strong_signature(row):
        signature_jobs = index.get(index.sigs.get(signature(row), []))
        compatible = []
        for job in signature_jobs:
            job_ids = index.identities(job)
            if identity and job_ids and identity not in job_ids:
                signature_conflicts.append(job)
            else:
                compatible.append(job)
        if compatible:
            job, issues = _best_match(compatible, expected)
            if issues:
                return {
                    **base,
                    "status": "filtered_or_misclassified",
                    "confidence": "medium",
                    "reason": "; ".join(issues),
                    "matched_job": compact(job),
                    "recommended_action": "Review profile/state/type enrichment or filter metadata.",
                }
            return {
                **base,
                "status": "already_in_yartchives",
                "confidence": "medium",
                "reason": "matched by normalized company/title/location without a conflicting requisition ID",
                "matched_job": compact(job),
                "recommended_action": "No coverage fix needed; retain direct URLs in future samples for stronger matching.",
            }

    company = company_key(company_display)
    employer_jobs = index.get(index.companies.get(company, [])) if company else []
    near: list[tuple[float, dict[str, Any]]] = []
    if employer_jobs:
        near = [
            (
                0.7 * similar(title, str(job.get("title") or ""))
                + 0.3 * similar(location, str(job.get("location") or "")),
                job,
            )
            for job in employer_jobs
        ]
        near.sort(key=lambda item: item[0], reverse=True)
        if near and near[0][0] >= 0.88:
            score, job = near[0]
            job_ids = index.identities(job)
            requisition_conflict = bool(identity and job_ids and identity not in job_ids)
            if not requisition_conflict:
                return {
                    **base,
                    "status": "duplicate_resolution_issue",
                    "confidence": "medium",
                    "match_score": round(score, 3),
                    "reason": "same employer has a very similar title/location without a conflicting requisition ID",
                    "matched_job": compact(job),
                    "recommended_action": "Verify requisition identity; if the same role, improve normalization.",
                }

    covered, why = source_coverage(row, catalog, company)
    candidate_jobs = [compact(job) for _, job in near[:3]] if near else [compact(job) for job in employer_jobs[:3]]
    if covered is True:
        detail = why
        if employer_jobs:
            detail += f"; Yartchives has {len(employer_jobs)} other listing(s) for this employer"
        if signature_conflicts:
            detail += "; a same-title/location feed listing has a different requisition identifier"
        return {
            **base,
            "status": "configured_source_miss",
            "confidence": "high",
            "reason": f"{detail}, but this listing is absent from the feed",
            "candidate_jobs": candidate_jobs,
            "recommended_action": "Inspect adapter search terms, title/location filters, pagination, freshness, and source errors for this configured source.",
        }

    if employer_jobs:
        detail = f"Yartchives has {len(employer_jobs)} listing(s) for this employer but not this role"
        if signature_conflicts:
            detail += "; a same-title/location listing uses a different requisition identifier"
        return {
            **base,
            "status": "employer_exists_but_listing_missing",
            "confidence": "high",
            "reason": detail,
            "candidate_jobs": candidate_jobs,
            "recommended_action": "Trace the role to the employer ATS and determine which upstream or direct source should cover it.",
        }

    if covered is False:
        action = "Trace to the employer career/ATS page and add durable direct coverage if the miss recurs."
        if is_discovery_surface(source) or is_discovery_surface(first(row, "source_url", "discovery_url")):
            action += " Keep the discovery platform audit-only rather than scraping it."
        return {
            **base,
            "status": "source_not_covered",
            "confidence": "high",
            "reason": why,
            "recommended_action": action,
        }

    return {
        **base,
        "status": "unknown",
        "confidence": "low",
        "reason": why,
        "recommended_action": "Add company, title, location, direct URL, and discovery source, then rerun.",
    }


def _row_quality(row: dict[str, Any]) -> tuple[int, int]:
    url = first(row, "url", "apply_url", "listing_url")
    direct_bonus = 3 if url and not is_discovery_surface(url) else 0
    populated = sum(
        bool(first(row, *keys))
        for keys in (
            ("company", "employer", "organization"),
            ("title", "role", "position"),
            ("location", "locations"),
            ("url", "apply_url", "listing_url"),
            ("source", "source_name", "discovered_via"),
        )
    )
    return direct_bonus + populated, len(url)


def dedupe_external_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated discoveries of the same external listing.

    Discovery-platform IDs are not treated as employer requisition IDs. Rows with
    different authoritative employer/ATS IDs are kept separate even when their
    company/title/location text is identical.
    """
    groups: list[dict[str, Any]] = []
    canonical_to_group: dict[str, int] = {}
    identity_to_group: dict[tuple[str, str], int] = {}
    signature_to_groups: defaultdict[str, list[int]] = defaultdict(list)

    for input_index, original in enumerate(rows, 1):
        row = dict(original)
        url = first(row, "url", "apply_url", "listing_url")
        canonical = canonical_url(url) if url else ""
        identity = authoritative_identity(url)
        sig = signature(row) if has_strong_signature(row) else ""

        group_index: int | None = None
        if canonical and canonical in canonical_to_group:
            group_index = canonical_to_group[canonical]
        elif identity and identity in identity_to_group:
            group_index = identity_to_group[identity]
        elif sig:
            for candidate_index in signature_to_groups.get(sig, []):
                candidate_ids = groups[candidate_index]["identities"]
                if identity and candidate_ids and identity not in candidate_ids:
                    continue
                group_index = candidate_index
                break

        if group_index is None:
            group_index = len(groups)
            groups.append(
                {
                    "rows": [],
                    "indices": [],
                    "sources": [],
                    "urls": [],
                    "identities": set(),
                    "signature": sig,
                }
            )
            if sig:
                signature_to_groups[sig].append(group_index)

        group = groups[group_index]
        group["rows"].append(row)
        group["indices"].append(input_index)
        source = first(row, "source", "source_name", "discovered_via")
        if source and source not in group["sources"]:
            group["sources"].append(source)
        if url and url not in group["urls"]:
            group["urls"].append(url)
        if identity:
            group["identities"].add(identity)
        if canonical:
            canonical_to_group[canonical] = group_index
        if identity:
            identity_to_group[identity] = group_index

    out = []
    for group in groups:
        representative = max(group["rows"], key=_row_quality).copy()
        representative["_audit_input_indices"] = group["indices"]
        representative["_audit_observation_count"] = len(group["rows"])
        representative["_audit_observed_sources"] = group["sources"]
        representative["_audit_observation_urls"] = group["urls"]
        out.append(representative)
    return out


def sample_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    for input_index, row in enumerate(rows, 1):
        company = first(row, "company", "employer", "organization")
        title = first(row, "title", "role", "position")
        location = first(row, "location", "locations")
        url = first(row, "url", "apply_url", "listing_url")
        source = first(row, "source", "source_name", "discovered_via")
        if not company:
            issues.append({"input_index": input_index, "severity": "error", "code": "missing_company", "message": "company/employer is missing"})
        if not title:
            issues.append({"input_index": input_index, "severity": "error", "code": "missing_title", "message": "title/role is missing"})
        if not location:
            issues.append({"input_index": input_index, "severity": "warning", "code": "missing_location", "message": "location is missing; fallback matching is weaker"})
        if not url:
            issues.append({"input_index": input_index, "severity": "warning", "code": "missing_url", "message": "direct/listing URL is missing; requisition matching is weaker"})
        elif is_discovery_surface(url):
            issues.append({"input_index": input_index, "severity": "warning", "code": "discovery_url_only", "message": "URL points to a discovery platform; prefer the employer/ATS application URL"})
        if not source:
            issues.append({"input_index": input_index, "severity": "warning", "code": "missing_source", "message": "discovery source is missing"})
    counts = Counter(issue["severity"] for issue in issues)
    return {"error_count": counts["error"], "warning_count": counts["warning"], "issues": issues}


def _gap_clusters(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for result in results:
        if result["status"] not in MISSING_STATUSES:
            continue
        company = company_key(result.get("company") or "")
        hostname = host(result.get("url") or "")
        key = f"company:{company}" if company else f"host:{hostname or 'unknown'}"
        cluster = clusters.setdefault(
            key,
            {
                "key": key,
                "company": result.get("company") or "",
                "host": hostname,
                "count": 0,
                "status_counts": Counter(),
            },
        )
        cluster["count"] += 1
        cluster["status_counts"][result["status"]] += 1
    out = []
    for cluster in clusters.values():
        cluster = dict(cluster)
        cluster["status_counts"] = dict(cluster["status_counts"])
        out.append(cluster)
    out.sort(key=lambda item: (-item["count"], item["key"]))
    return out


def build_report(
    rows: list[dict[str, Any]],
    feed_doc: dict[str, Any],
    jobs: list[dict[str, Any]],
    catalog: dict[str, set[str]],
    profiles: list[str],
    states: list[str],
    audit_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profiles = normalize_profiles(profiles)
    states = normalize_states(states)
    quality = sample_quality(rows)
    unique_rows = dedupe_external_rows(rows)
    index = Index(jobs)
    results = []
    for unique_index, row in enumerate(unique_rows, 1):
        result = classify(row, index, catalog, profiles, states)
        result["unique_index"] = unique_index
        result["input_indices"] = row.get("_audit_input_indices") or [unique_index]
        results.append(result)

    counts = Counter(result["status"] for result in results)
    total = len(results)
    represented = sum(counts[status] for status in REPRESENTED_STATUSES)
    confirmed = counts["already_in_yartchives"]
    missing = sum(counts[status] for status in MISSING_STATUSES)

    observations_by_source = Counter(
        first(row, "source", "source_name", "discovered_via") or host(first(row, "url", "apply_url", "listing_url")) or "unknown"
        for row in rows
    )
    by_source: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        sources = result.get("observed_sources") or [result.get("source") or host(result.get("url") or "") or "unknown"]
        for source in dict.fromkeys(sources):
            by_source[str(source)][result["status"]] += 1

    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "audit": audit_meta or {},
        "feed": {
            "generated_at": feed_doc.get("generated_at"),
            "content_hash": feed_doc.get("content_hash"),
            "indexed_jobs": len(jobs),
        },
        "scope": {"profiles": profiles, "states": states},
        "sample_quality": quality,
        "summary": {
            "external_observations": len(rows),
            "external_unique_listings": total,
            "external_listings": total,
            "duplicate_observations_collapsed": len(rows) - total,
            "confirmed_in_feed": confirmed,
            "represented_in_feed": represented,
            "missing_from_feed": missing,
            "captured_or_probably_captured": represented,
            "visible_under_expected_filters": confirmed,
            "representation_rate": round(represented / total, 4) if total else None,
            "capture_rate": round(represented / total, 4) if total else None,
            "visible_rate": round(confirmed / total, 4) if total else None,
            "status_counts": {status: counts[status] for status in STATUSES},
            "observations_by_source": dict(sorted(observations_by_source.items())),
            "by_source": {key: dict(value) for key, value in sorted(by_source.items())},
            "gap_clusters": _gap_clusters(results),
        },
        "results": results,
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    scope = report["scope"]
    audit = report.get("audit") or {}
    quality = report.get("sample_quality") or {}
    title = audit.get("name") or "Yartchives external coverage audit"
    lines = [f"# {title}", ""]
    if audit.get("collected_at"):
        lines.append(f"External sample collected: `{audit['collected_at']}`")
    lines += [
        f"Yartchives feed snapshot: `{report['feed'].get('generated_at') or 'unknown'}`",
        f"Scope: profiles={','.join(scope['profiles']) or 'any'}, states={','.join(scope['states']) or 'any'}",
        "",
        "## Coverage metrics",
        "",
        f"- External observations: **{summary['external_observations']}**",
        f"- Unique external listings: **{summary['external_unique_listings']}**",
        f"- Duplicate observations collapsed: **{summary['duplicate_observations_collapsed']}**",
        f"- Confirmed visible in Yartchives: **{summary['confirmed_in_feed']}**"
        + (f" ({summary['visible_rate']:.1%})" if summary["visible_rate"] is not None else ""),
        f"- Represented in feed, including fixable metadata/dedupe issues: **{summary['represented_in_feed']}**"
        + (f" ({summary['representation_rate']:.1%})" if summary["representation_rate"] is not None else ""),
        f"- Missing from feed: **{summary['missing_from_feed']}**",
        "",
        "## Status breakdown",
        "",
    ]
    lines += [f"- `{status}`: {summary['status_counts'][status]}" for status in STATUSES]

    lines += ["", "## Sample quality", ""]
    lines.append(
        f"- Errors: **{quality.get('error_count', 0)}**; warnings: **{quality.get('warning_count', 0)}**"
    )
    for issue in (quality.get("issues") or [])[:20]:
        lines.append(
            f"- `{issue['severity']}` input {issue['input_index']} `{issue['code']}`: {issue['message']}"
        )
    if len(quality.get("issues") or []) > 20:
        lines.append(f"- ...and {len(quality['issues']) - 20} more sample-quality issues in JSON output")

    recurring = [cluster for cluster in summary.get("gap_clusters", []) if cluster["count"] >= 2]
    lines += ["", "## Recurring gaps", ""]
    if not recurring:
        lines.append("No repeated missing-listing cluster appears in this sample.")
    else:
        for cluster in recurring[:15]:
            label = cluster.get("company") or cluster.get("host") or cluster["key"]
            statuses = ", ".join(f"{key}={value}" for key, value in sorted(cluster["status_counts"].items()))
            lines.append(f"- **{label}**: {cluster['count']} missing listing(s) ({statuses})")

    lines += ["", "## Action queue", ""]
    misses = [result for result in report["results"] if result["status"] != "already_in_yartchives"]
    misses.sort(key=lambda result: (ACTION_PRIORITY.get(result["status"], 9), result.get("company") or "", result.get("title") or ""))
    if not misses:
        lines.append("No misses or filter/classification issues found in this sample.")
    for result in misses:
        label = " — ".join(
            value
            for value in (result.get("company"), result.get("title"), result.get("location"))
            if value
        ) or "Unnamed listing"
        priority = ACTION_PRIORITY.get(result["status"], 9)
        lines += [
            f"- **P{priority} · {result['status']}**: {label}",
            f"  - Why: {result['reason']}",
            f"  - Next: {result['recommended_action']}",
        ]
    return "\n".join(lines) + "\n"


def _write_text(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("discoveries")
    parser.add_argument("--feed", default=str(FEED))
    parser.add_argument("--sources", default=str(SOURCES))
    parser.add_argument("--direct-sources", default=str(DIRECT))
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--state", action="append", default=[])
    parser.add_argument("--output")
    parser.add_argument("--markdown-output")
    parser.add_argument(
        "--strict-sample",
        action="store_true",
        help="exit non-zero when company/title sample-quality errors are present",
    )
    args = parser.parse_args()

    input_path = Path(args.discoveries)
    audit_meta, rows = load_audit_input(input_path)
    metadata_scope = audit_meta.get("scope") or {}
    profiles = normalize_profiles(args.profile) or normalize_profiles(metadata_scope.get("profiles"))
    states = normalize_states(args.state) or normalize_states(metadata_scope.get("states"))

    feed_doc = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    jobs = [job for job in feed_doc.get("jobs", []) if isinstance(job, dict)]
    report = build_report(
        rows,
        feed_doc,
        jobs,
        source_catalog(Path(args.sources), Path(args.direct_sources)),
        profiles,
        states,
        audit_meta=audit_meta,
    )
    report["input_file"] = str(input_path)

    text = markdown(report)
    print(text, end="")
    if args.output:
        _write_text(args.output, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if args.markdown_output:
        _write_text(args.markdown_output, text)
    if args.strict_sample and report["sample_quality"]["error_count"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
