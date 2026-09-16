#!/usr/bin/env python3
"""Compare externally discovered opportunities with the Yartchives feed.

The audit is offline: collect opportunities from LinkedIn, Handshake, web
search, or employer sites, then pass JSON/JSONL/CSV here. This script does not
scrape those discovery surfaces.
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
    "employer_exists_but_listing_missing",
    "source_not_covered",
    "unknown",
)
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
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in re.split(r"[;,]", str(value)) if x.strip()]


def company_key(value: str) -> str:
    text = norm(value)
    suffix = r"(?:inc|incorporated|llc|ltd|limited|corp|corporation|company|co)"
    while re.search(rf"(?:^|\s){suffix}$", text):
        text = re.sub(rf"(?:^|\s){suffix}$", "", text).strip()
    return text


def signature(row: dict[str, Any]) -> str:
    return "|".join(
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


def url_identity(url: str) -> tuple[str, str] | None:
    """Conservative provider identity used only to flag probable dedupe issues."""
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
                "profiles": as_list(scope.get("profiles") or scope.get("profile")),
                "states": as_list(scope.get("states") or scope.get("state")),
            },
        }
    )
    return metadata, rows


def source_catalog(sources: Path, direct: Path) -> dict[str, set[str]]:
    catalog = {
        "keys": {"usajobs"},
        "names": {"usajobs"},
        "hosts": {"usajobs.gov", "data.usajobs.gov"},
        "companies": set(),
    }
    for path in (sources, direct):
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row.get("key"):
                catalog["keys"].add(norm(str(row["key"])))
            if row.get("name"):
                catalog["names"].add(norm(str(row["name"])))
            if row.get("company"):
                catalog["companies"].add(company_key(str(row["company"])))
            for field in ("url", "homepage", "api_url", "public_base"):
                hostname = host(str(row.get(field) or ""))
                if hostname:
                    catalog["hosts"].add(hostname)
    return catalog


class Index:
    def __init__(self, jobs: list[dict[str, Any]]):
        self.jobs = jobs
        self.urls: defaultdict[str, list[int]] = defaultdict(list)
        self.ids: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
        self.sigs: defaultdict[str, list[int]] = defaultdict(list)
        self.companies: defaultdict[str, list[int]] = defaultdict(list)
        for index, job in enumerate(jobs):
            company = company_key(str(job.get("company") or ""))
            if company:
                self.companies[company].append(index)
            self.sigs[signature(job)].append(index)
            for value in (job.get("url"), job.get("listing_url"), job.get("apply_url")):
                if not value:
                    continue
                self.urls[canonical_url(str(value))].append(index)
                identity = url_identity(str(value))
                if identity:
                    self.ids[identity].append(index)

    def get(self, ids: list[int]) -> list[dict[str, Any]]:
        return [self.jobs[index] for index in dict.fromkeys(ids)]


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
    return {
        "profiles": profiles or as_list(row.get("expected_profiles") or row.get("expected_profile")),
        "states": states or as_list(row.get("expected_states") or row.get("expected_state")),
        "opportunity_types": as_list(
            row.get("expected_opportunity_types") or row.get("expected_opportunity_type")
        ),
        "default_visible": visible,
    }


def surface_issues(job: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    issues = []
    for profile in expected["profiles"]:
        if profile not in (job.get("profiles") or []):
            issues.append(f"missing expected profile '{profile}'")
    for state in expected["states"]:
        if state not in (job.get("states") or []):
            issues.append(f"missing expected state '{state}'")
    opportunity_type = str(job.get("opportunity_type") or "")
    if expected["opportunity_types"] and opportunity_type not in expected["opportunity_types"]:
        issues.append(
            f"opportunity_type '{opportunity_type or 'missing'}' does not match {expected['opportunity_types']}"
        )
    if expected["default_visible"]:
        if job.get("education_level") == "graduate-only":
            issues.append("graduate-only is hidden by the default undergrad filter")
        if opportunity_type and opportunity_type not in VISIBLE_TYPES:
            issues.append(f"opportunity_type '{opportunity_type}' is hidden by the default type filter")
    return issues


def similar(left: str, right: str) -> float:
    left, right = norm(left), norm(right)
    return SequenceMatcher(a=left, b=right).ratio() if left and right else 0.0


def classify(
    row: dict[str, Any],
    index: Index,
    catalog: dict[str, set[str]],
    profiles: list[str],
    states: list[str],
) -> dict[str, Any]:
    company = first(row, "company", "employer", "organization")
    title = first(row, "title", "role", "position")
    location = first(row, "location", "locations")
    url = first(row, "url", "apply_url", "listing_url")
    source = first(row, "source", "source_name", "discovered_via")
    expected = expectations(row, profiles, states)
    base = {
        "company": company,
        "title": title,
        "location": location,
        "url": url,
        "source": source,
        "expected": expected,
    }

    exact_ids: list[int] = []
    if url:
        exact_ids += index.urls.get(canonical_url(url), [])
    exact_ids += index.sigs.get(signature(row), [])
    exact = index.get(exact_ids)
    if exact:
        job = exact[0]
        issues = surface_issues(job, expected)
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
            "reason": "matched by canonical URL or normalized company/title/location",
            "matched_job": compact(job),
            "recommended_action": "No coverage fix needed.",
        }

    identity = url_identity(url)
    if identity and index.ids.get(identity):
        job = index.get(index.ids[identity])[0]
        return {
            **base,
            "status": "duplicate_resolution_issue",
            "confidence": "high",
            "reason": "same ATS/listing identifier exists but ordinary URL/signature matching failed",
            "matched_job": compact(job),
            "recommended_action": "Add provider-specific canonicalization/deduplication.",
        }

    company = company_key(company)
    employer_jobs = index.get(index.companies.get(company, [])) if company else []
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
            return {
                **base,
                "status": "duplicate_resolution_issue",
                "confidence": "medium",
                "match_score": round(score, 3),
                "reason": "same employer has a very similar title/location",
                "matched_job": compact(job),
                "recommended_action": "Verify requisition identity; if the same role, improve normalization.",
            }
        return {
            **base,
            "status": "employer_exists_but_listing_missing",
            "confidence": "high",
            "reason": f"Yartchives has {len(employer_jobs)} listing(s) for this employer but not this role",
            "candidate_jobs": [compact(job) for job in employer_jobs[:3]],
            "recommended_action": "Trace the role to the employer ATS and check source filters or add direct coverage.",
        }

    source_key = norm(first(row, "source_key"))
    source_name = norm(source)
    if company and company in catalog["companies"]:
        covered, why = True, "employer has a configured direct source"
    elif source_key:
        covered, why = source_key in catalog["keys"], f"source_key={source_key}"
    elif source_name and source_name in catalog["names"]:
        covered, why = True, f"source={source_name}"
    elif source_name and any(surface in source_name for surface in DISCOVERY_SURFACES):
        covered, why = False, f"discovery surface '{source_name}' is not ingested"
    else:
        hostname = host(first(row, "source_url", "discovery_url") or url)
        if hostname in catalog["hosts"]:
            covered, why = True, f"host={hostname}"
        elif hostname and any(hint in hostname for hint in ATS_HINTS):
            covered, why = False, f"direct ATS host '{hostname}' is not configured"
        elif hostname:
            covered, why = False, f"listing/source host '{hostname}' is not configured"
        else:
            covered, why = None, "no source metadata"

    if covered is True:
        return {
            **base,
            "status": "filtered_or_misclassified",
            "confidence": "medium",
            "reason": f"source appears covered ({why}) but the listing is absent after ingestion",
            "recommended_action": "Inspect source freshness, adapter filters, and enrichment for this listing.",
        }
    if covered is False:
        action = "Trace to the employer career/ATS page and add durable direct coverage if the miss recurs."
        if any(surface in source_name for surface in DISCOVERY_SURFACES):
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


def build_report(
    rows: list[dict[str, Any]],
    feed_doc: dict[str, Any],
    jobs: list[dict[str, Any]],
    catalog: dict[str, set[str]],
    profiles: list[str],
    states: list[str],
    audit_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = Index(jobs)
    results = []
    for input_index, row in enumerate(rows, 1):
        result = classify(row, index, catalog, profiles, states)
        result["input_index"] = input_index
        results.append(result)

    counts = Counter(result["status"] for result in results)
    total = len(results)
    captured = sum(
        counts[status]
        for status in (
            "already_in_yartchives",
            "filtered_or_misclassified",
            "duplicate_resolution_issue",
        )
    )
    by_source: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        source = result.get("source") or host(result.get("url") or "") or "unknown"
        by_source[source][result["status"]] += 1

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "audit": audit_meta or {},
        "feed": {
            "generated_at": feed_doc.get("generated_at"),
            "content_hash": feed_doc.get("content_hash"),
            "indexed_jobs": len(jobs),
        },
        "scope": {"profiles": profiles, "states": states},
        "summary": {
            "external_listings": total,
            "captured_or_probably_captured": captured,
            "visible_under_expected_filters": counts["already_in_yartchives"],
            "capture_rate": round(captured / total, 4) if total else None,
            "visible_rate": round(counts["already_in_yartchives"] / total, 4) if total else None,
            "status_counts": {status: counts[status] for status in STATUSES},
            "by_source": {key: dict(value) for key, value in sorted(by_source.items())},
        },
        "results": results,
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    scope = report["scope"]
    audit = report.get("audit") or {}
    title = audit.get("name") or "Yartchives external coverage audit"
    lines = [f"# {title}", ""]
    if audit.get("collected_at"):
        lines.append(f"External sample collected: `{audit['collected_at']}`")
    lines += [
        f"Yartchives feed snapshot: `{report['feed'].get('generated_at') or 'unknown'}`",
        f"Scope: profiles={','.join(scope['profiles']) or 'any'}, states={','.join(scope['states']) or 'any'}",
        "",
        f"- External listings audited: **{summary['external_listings']}**",
        f"- Captured or probably captured: **{summary['captured_or_probably_captured']}**"
        + (f" ({summary['capture_rate']:.1%})" if summary["capture_rate"] is not None else ""),
        f"- Visible under expected filters: **{summary['visible_under_expected_filters']}**"
        + (f" ({summary['visible_rate']:.1%})" if summary["visible_rate"] is not None else ""),
        "",
        "## Status breakdown",
        "",
    ]
    lines += [f"- `{status}`: {summary['status_counts'][status]}" for status in STATUSES]
    lines += ["", "## Action queue", ""]
    misses = [result for result in report["results"] if result["status"] != "already_in_yartchives"]
    if not misses:
        lines.append("No misses or filter/classification issues found in this sample.")
    for result in misses:
        label = " — ".join(
            value
            for value in (result.get("company"), result.get("title"), result.get("location"))
            if value
        ) or "Unnamed listing"
        lines += [
            f"- **{result['status']}**: {label}",
            f"  - Why: {result['reason']}",
            f"  - Next: {result['recommended_action']}",
        ]
    return "\n".join(lines) + "\n"


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
    args = parser.parse_args()

    input_path = Path(args.discoveries)
    audit_meta, rows = load_audit_input(input_path)
    metadata_scope = audit_meta.get("scope") or {}
    profiles = args.profile or as_list(metadata_scope.get("profiles"))
    states = args.state or as_list(metadata_scope.get("states"))

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
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
