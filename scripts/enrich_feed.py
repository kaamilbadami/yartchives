#!/usr/bin/env python3
"""Add deterministic student-level and opportunity-type metadata to the feed."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "listings.json"

# These upstream repositories explicitly identify themselves as internship feeds.
# If a row has a generic title such as "Summer Analyst", preserve it in the
# internships view instead of hiding it merely because the word "intern" is absent.
INTERNSHIP_FEED_KEYS = {
    "dreamwork-tech",
    "dreamwork-business",
    "zapply",
    "simplify",
    "vansh-cscareers",
    "applyguy",
    "sndsh",
    "public-sector",
}


def classify_education(title: str | None) -> str:
    raw = title or ""
    lower = raw.lower()
    has_undergrad = bool(
        re.search(r"\b(undergrad(?:uate)?|bachelor(?:'s|s)?|associate(?:'s|s)? degree|freshman|sophomore|junior)\b", lower)
        or re.search(r"(?:^|[\s,(\/])B\.?S\.?(?=$|[\s,)/])", raw, flags=re.I)
        or re.search(r"(?:^|[\s,(\/])B\.?A\.?(?=$|[\s,)/])", raw, flags=re.I)
    )
    has_graduate = bool(
        re.search(r"\b(ph\.?d\.?|doctoral|doctorate|master(?:'s|s)?(?: degree)?|graduate student|graduate internship|mba|juris doctor)\b", raw, flags=re.I)
        or re.search(r"(?:^|[\s,(\/])M\.?S\.?(?=$|[\s,)/])", raw, flags=re.I)
        or re.search(r"(?:^|[\s,(\/])M\.?A\.?(?=$|[\s,)/])", raw, flags=re.I)
        or re.search(r"(?:^|[\s,(\/])J\.?D\.?(?=$|[\s,)/])", raw, flags=re.I)
    )
    if has_undergrad:
        return "undergrad"
    if has_graduate:
        return "graduate-only"
    return "unspecified"


def classify_opportunity_type(title: str | None, source_keys: list[str] | None = None) -> str:
    text = (title or "").lower()
    if re.search(r"\b(co[- ]?op|cooperative education)\b", text):
        return "co-op"
    if re.search(r"\b(intern|internship|student trainee|pathways)\b", text):
        return "internship"
    if re.search(r"\b(fellow|fellowship)\b", text):
        return "fellowship"
    if re.search(r"\b(research assistant|research program|research experience)\b", text):
        return "research"
    if re.search(r"\bstudent\b", text):
        return "student"
    if any(key in INTERNSHIP_FEED_KEYS for key in (source_keys or [])):
        return "internship"
    return "other"


def enrich_document(doc: dict[str, Any]) -> bool:
    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Feed does not contain a jobs list")

    changed = False
    for job in jobs:
        if not isinstance(job, dict):
            continue
        education = classify_education(job.get("title"))
        opportunity_type = classify_opportunity_type(job.get("title"), job.get("source_keys") or [])
        if job.get("education_level") != education:
            job["education_level"] = education
            changed = True
        if job.get("opportunity_type") != opportunity_type:
            job["opportunity_type"] = opportunity_type
            changed = True
    return changed


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    doc = json.loads(path.read_text(encoding="utf-8"))
    changed = enrich_document(doc)
    if changed:
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Enriched {len(doc.get('jobs', []))} listings in {path}")
    else:
        print("Feed enrichment already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
