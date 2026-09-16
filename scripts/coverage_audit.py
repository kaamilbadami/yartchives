#!/usr/bin/env python3
"""Compare externally discovered opportunities with the Yartchives feed.

The audit is offline: collect opportunities from LinkedIn, Handshake, web
search, or employer sites, then pass JSON/JSONL/CSV here. This script does not
scrape those discovery surfaces.
"""
from __future__ import annotations

import argparse, csv, json, re, sys
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
    "already_in_yartchives", "filtered_or_misclassified",
    "duplicate_resolution_issue", "employer_exists_but_listing_missing",
    "source_not_covered", "unknown",
)
DISCOVERY_SURFACES = {"linkedin", "handshake", "indeed", "glassdoor", "ziprecruiter"}
ATS_HINTS = ("myworkdayjobs.com", "greenhouse.io", "lever.co", "ashbyhq.com",
             "smartrecruiters.com", "icims.com", "jobvite.com", "oraclecloud.com")


def first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def as_list(value: Any) -> list[str]:
    if value is None: return []
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
    return "|".join((company_key(first(row, "company", "employer", "organization")),
                     norm(first(row, "title", "role", "position")),
                     norm(first(row, "location", "locations"))))


def host(url: str) -> str:
    try: return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception: return ""


def url_identity(url: str) -> tuple[str, str] | None:
    """Conservative provider identity used only to flag probable dedupe issues."""
    if not url: return None
    try: p = urlparse(url)
    except Exception: return None
    h = p.netloc.lower().removeprefix("www.")
    for key, value in parse_qsl(p.query):
        if key.lower() in {"jobid", "job_id", "gh_jid", "jid", "requisitionid", "reqid"} and value:
            return h, f"{key.lower()}={norm(value)}"
    tail = re.sub(r"/+", "/", p.path).rstrip("/").split("/")[-1].lower()
    if h and len(tail) >= 4 and re.search(r"\d", tail): return h, tail
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [dict(x) for x in csv.DictReader(f)]
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        out = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip(): continue
            row = json.loads(line)
            if not isinstance(row, dict): raise ValueError(f"line {n}: expected object")
            out.append(row)
        return out
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list): rows = payload
    elif isinstance(payload, dict):
        rows = next((payload[k] for k in ("discoveries", "jobs", "listings", "opportunities")
                     if isinstance(payload.get(k), list)), None)
        if rows is None: raise ValueError("JSON must be a list or contain discoveries/jobs/listings/opportunities")
    else: raise ValueError("JSON audit input must contain objects")
    if not all(isinstance(x, dict) for x in rows): raise ValueError("every discovery must be an object")
    return [dict(x) for x in rows]


def source_catalog(sources: Path, direct: Path) -> dict[str, set[str]]:
    cat = {"keys": {"usajobs"}, "names": {"usajobs"},
           "hosts": {"usajobs.gov", "data.usajobs.gov"}, "companies": set()}
    for path in (sources, direct):
        if not path.exists(): continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row.get("key"): cat["keys"].add(norm(str(row["key"])))
            if row.get("name"): cat["names"].add(norm(str(row["name"])))
            if row.get("company"): cat["companies"].add(company_key(str(row["company"])))
            for field in ("url", "homepage", "api_url", "public_base"):
                if host(str(row.get(field) or "")): cat["hosts"].add(host(str(row[field])))
    return cat


class Index:
    def __init__(self, jobs: list[dict[str, Any]]):
        self.jobs = jobs; self.urls = defaultdict(list); self.ids = defaultdict(list)
        self.sigs = defaultdict(list); self.companies = defaultdict(list)
        for i, job in enumerate(jobs):
            ck = company_key(str(job.get("company") or ""))
            if ck: self.companies[ck].append(i)
            self.sigs[signature(job)].append(i)
            for value in (job.get("url"), job.get("listing_url"), job.get("apply_url")):
                if not value: continue
                self.urls[canonical_url(str(value))].append(i)
                ident = url_identity(str(value))
                if ident: self.ids[ident].append(i)

    def get(self, ids: list[int]) -> list[dict[str, Any]]:
        return [self.jobs[i] for i in dict.fromkeys(ids)]


def compact(job: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "company", "title", "location", "url", "listing_url", "profiles", "states",
            "opportunity_type", "education_level", "source_keys", "link_kind", "posted_at")
    return {k: job.get(k) for k in keys if job.get(k) not in (None, "", [])}


def expectations(row: dict[str, Any], profiles: list[str], states: list[str]) -> dict[str, Any]:
    raw_visible = row.get("expect_default_visible", True)
    visible = raw_visible.strip().lower() not in {"0", "false", "no", "off"} if isinstance(raw_visible, str) else bool(raw_visible)
    return {
        "profiles": profiles or as_list(row.get("expected_profiles") or row.get("expected_profile")),
        "states": states or as_list(row.get("expected_states") or row.get("expected_state")),
        "opportunity_types": as_list(row.get("expected_opportunity_types") or row.get("expected_opportunity_type")),
        "default_visible": visible,
    }


def surface_issues(job: dict[str, Any], exp: dict[str, Any]) -> list[str]:
    issues = []
    for p in exp["profiles"]:
        if p not in (job.get("profiles") or []): issues.append(f"missing expected profile '{p}'")
    for s in exp["states"]:
        if s not in (job.get("states") or []): issues.append(f"missing expected state '{s}'")
    typ = str(job.get("opportunity_type") or "")
    if exp["opportunity_types"] and typ not in exp["opportunity_types"]:
        issues.append(f"opportunity_type '{typ or 'missing'}' does not match {exp['opportunity_types']}")
    if exp["default_visible"]:
        if job.get("education_level") == "graduate-only": issues.append("graduate-only is hidden by the default undergrad filter")
        if typ and typ not in VISIBLE_TYPES: issues.append(f"opportunity_type '{typ}' is hidden by the default type filter")
    return issues


def similar(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    return SequenceMatcher(a=a, b=b).ratio() if a and b else 0.0


def classify(row: dict[str, Any], idx: Index, cat: dict[str, set[str]], profiles: list[str], states: list[str]) -> dict[str, Any]:
    company = first(row, "company", "employer", "organization"); title = first(row, "title", "role", "position")
    location = first(row, "location", "locations"); url = first(row, "url", "apply_url", "listing_url")
    source = first(row, "source", "source_name", "discovered_via"); exp = expectations(row, profiles, states)
    base = {"company": company, "title": title, "location": location, "url": url, "source": source, "expected": exp}

    exact_ids = []
    if url: exact_ids += idx.urls.get(canonical_url(url), [])
    exact_ids += idx.sigs.get(signature(row), [])
    exact = idx.get(exact_ids)
    if exact:
        job = exact[0]; issues = surface_issues(job, exp)
        if issues:
            return {**base, "status": "filtered_or_misclassified", "confidence": "high", "reason": "; ".join(issues),
                    "matched_job": compact(job), "recommended_action": "Review profile/state/type enrichment or filter metadata."}
        return {**base, "status": "already_in_yartchives", "confidence": "high",
                "reason": "matched by canonical URL or normalized company/title/location", "matched_job": compact(job),
                "recommended_action": "No coverage fix needed."}

    ident = url_identity(url)
    if ident and idx.ids.get(ident):
        job = idx.get(idx.ids[ident])[0]
        return {**base, "status": "duplicate_resolution_issue", "confidence": "high",
                "reason": "same ATS/listing identifier exists but ordinary URL/signature matching failed", "matched_job": compact(job),
                "recommended_action": "Add provider-specific canonicalization/deduplication."}

    ck = company_key(company); employer_jobs = idx.get(idx.companies.get(ck, [])) if ck else []
    if employer_jobs:
        near = [(0.7 * similar(title, str(j.get("title") or "")) + 0.3 * similar(location, str(j.get("location") or "")), j)
                for j in employer_jobs]
        near.sort(key=lambda x: x[0], reverse=True)
        if near and near[0][0] >= 0.88:
            score, job = near[0]
            return {**base, "status": "duplicate_resolution_issue", "confidence": "medium", "match_score": round(score, 3),
                    "reason": "same employer has a very similar title/location", "matched_job": compact(job),
                    "recommended_action": "Verify requisition identity; if the same role, improve normalization."}
        return {**base, "status": "employer_exists_but_listing_missing", "confidence": "high",
                "reason": f"Yartchives has {len(employer_jobs)} listing(s) for this employer but not this role",
                "candidate_jobs": [compact(x) for x in employer_jobs[:3]],
                "recommended_action": "Trace the role to the employer ATS and check source filters or add direct coverage."}

    source_key = norm(first(row, "source_key")); source_name = norm(source)
    if ck and ck in cat["companies"]: covered, why = True, "employer has a configured direct source"
    elif source_key: covered, why = source_key in cat["keys"], f"source_key={source_key}"
    elif source_name and source_name in cat["names"]: covered, why = True, f"source={source_name}"
    elif source_name and any(x in source_name for x in DISCOVERY_SURFACES): covered, why = False, f"discovery surface '{source_name}' is not ingested"
    else:
        h = host(first(row, "source_url", "discovery_url") or url)
        if h in cat["hosts"]: covered, why = True, f"host={h}"
        elif h and any(x in h for x in ATS_HINTS): covered, why = False, f"direct ATS host '{h}' is not configured"
        elif h: covered, why = False, f"listing/source host '{h}' is not configured"
        else: covered, why = None, "no source metadata"

    if covered is True:
        return {**base, "status": "filtered_or_misclassified", "confidence": "medium",
                "reason": f"source appears covered ({why}) but the listing is absent after ingestion",
                "recommended_action": "Inspect source freshness, adapter filters, and enrichment for this listing."}
    if covered is False:
        action = "Trace to the employer career/ATS page and add durable direct coverage if the miss recurs."
        if any(x in source_name for x in DISCOVERY_SURFACES): action += " Keep the discovery platform audit-only rather than scraping it."
        return {**base, "status": "source_not_covered", "confidence": "high", "reason": why, "recommended_action": action}
    return {**base, "status": "unknown", "confidence": "low", "reason": why,
            "recommended_action": "Add company, title, location, direct URL, and discovery source, then rerun."}


def build_report(rows: list[dict[str, Any]], feed_doc: dict[str, Any], jobs: list[dict[str, Any]], cat: dict[str, set[str]], profiles: list[str], states: list[str]) -> dict[str, Any]:
    idx = Index(jobs); results = []
    for n, row in enumerate(rows, 1):
        result = classify(row, idx, cat, profiles, states); result["input_index"] = n; results.append(result)
    counts = Counter(x["status"] for x in results); total = len(results)
    captured = sum(counts[x] for x in ("already_in_yartchives", "filtered_or_misclassified", "duplicate_resolution_issue"))
    by_source = defaultdict(Counter)
    for r in results: by_source[r.get("source") or host(r.get("url") or "") or "unknown"][r["status"]] += 1
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "feed": {"generated_at": feed_doc.get("generated_at"), "content_hash": feed_doc.get("content_hash"), "indexed_jobs": len(jobs)},
            "scope": {"profiles": profiles, "states": states},
            "summary": {"external_listings": total, "captured_or_probably_captured": captured,
                        "visible_under_expected_filters": counts["already_in_yartchives"],
                        "capture_rate": round(captured / total, 4) if total else None,
                        "visible_rate": round(counts["already_in_yartchives"] / total, 4) if total else None,
                        "status_counts": {s: counts[s] for s in STATUSES},
                        "by_source": {k: dict(v) for k, v in sorted(by_source.items())}},
            "results": results}


def markdown(report: dict[str, Any]) -> str:
    s = report["summary"]; scope = report["scope"]
    lines = ["# Yartchives external coverage audit", "", f"Scope: profiles={','.join(scope['profiles']) or 'any'}, states={','.join(scope['states']) or 'any'}", "",
             f"- External listings audited: **{s['external_listings']}**",
             f"- Captured or probably captured: **{s['captured_or_probably_captured']}**" + (f" ({s['capture_rate']:.1%})" if s['capture_rate'] is not None else ""),
             f"- Visible under expected filters: **{s['visible_under_expected_filters']}**" + (f" ({s['visible_rate']:.1%})" if s['visible_rate'] is not None else ""), "", "## Status breakdown", ""]
    lines += [f"- `{x}`: {s['status_counts'][x]}" for x in STATUSES]
    lines += ["", "## Action queue", ""]
    misses = [x for x in report["results"] if x["status"] != "already_in_yartchives"]
    if not misses: lines.append("No misses or filter/classification issues found in this sample.")
    for r in misses:
        label = " — ".join(x for x in (r.get("company"), r.get("title"), r.get("location")) if x) or "Unnamed listing"
        lines += [f"- **{r['status']}**: {label}", f"  - Why: {r['reason']}", f"  - Next: {r['recommended_action']}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("discoveries")
    p.add_argument("--feed", default=str(FEED)); p.add_argument("--sources", default=str(SOURCES)); p.add_argument("--direct-sources", default=str(DIRECT))
    p.add_argument("--profile", action="append", default=[]); p.add_argument("--state", action="append", default=[])
    p.add_argument("--output"); p.add_argument("--markdown-output"); a = p.parse_args()
    feed_doc = json.loads(Path(a.feed).read_text(encoding="utf-8")); jobs = [x for x in feed_doc.get("jobs", []) if isinstance(x, dict)]
    report = build_report(load_rows(Path(a.discoveries)), feed_doc, jobs, source_catalog(Path(a.sources), Path(a.direct_sources)), a.profile, a.state)
    text = markdown(report); print(text, end="")
    if a.output: Path(a.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if a.markdown_output: Path(a.markdown_output).write_text(text, encoding="utf-8")
    return 0

if __name__ == "__main__": raise SystemExit(main())
