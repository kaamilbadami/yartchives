#!/usr/bin/env python3
"""Canonicalize display text and add deterministic feed metadata.

This is the final semantic pass after all upstream feeds/direct sources have
been merged. Keep profile classification conservative: a role should appear in
a profile because the role/function says it belongs there, not because an
upstream repository grouped it under a broad section.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

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
    "speedyapply",
    "applyguy",
    "sndsh",
    "public-sector",
}

# Direct provider-family adapters with strict CS/technology admission filters can
# preserve that provider evidence through this final semantic pass. Broad source
# profile tags are intentionally not trusted here.
STRICT_CS_SOURCE_PREFIXES = (
    "ct-",
    "auto-greenhouse-",
    "auto-icims-",
)

# Upstream repositories use these as visual legends. They are source metadata,
# not part of a company or role name, so Yartchives stores them separately.
SOURCE_MARKERS = {
    "🔥": "source_featured",
    "🎓": "advanced_degree",
    "🔒": "closed",
    "🛂": "no_sponsorship",
    "🇺🇸": "us_citizenship",
}

PROFILE_PATTERNS: dict[str, tuple[str, ...]] = {
    "cs": (
        r"\bsoftware\b",
        r"\bcomputer science\b",
        r"\bmachine learning\b",
        r"\bml engineer(?:ing)?\b",
        r"\bartificial intelligence\b",
        r"\bai[/ -]?ml\b",
        r"\bdata scien(?:ce|tist)\b",
        r"\bdata engineer(?:ing)?\b",
        r"\bcyber(?:security)?\b",
        r"\bsecurity engineer(?:ing)?\b",
        r"\bdevops\b",
        r"\bcloud engineer(?:ing)?\b",
        r"\bback[- ]?end\b",
        r"\bfront[- ]?end\b",
        r"\bfull[- ]?stack\b",
        r"\bsite reliability\b",
        r"\bsre\b",
        r"\bcomputer vision\b",
        r"\bdistributed systems?\b",
        r"\bplatform engineer(?:ing)?\b",
        r"\bapplication developer\b",
        r"\bweb developer\b",
        r"\bprogrammer\b",
        r"\bdatabase\b",
        r"\bsql\b",
        r"\bnetwork (?:engineer(?:ing)?|operations?)\b",
        r"\binformation technology\b",
        r"\bit (?:intern|co[- ]?op|student|analyst|engineer)\b",
    ),
    "tech-business": (
        r"\bproduct management\b",
        r"\bproduct manager\b",
        r"\bproduct analyst\b",
        r"\bproduct operations\b",
        r"\btechnical program manage(?:r|ment)\b",
        r"\bbusiness analyst\b",
        r"\bbusiness systems analyst\b",
        r"\bsystems analyst\b",
        r"\bdata analyst\b",
        r"\bbusiness intelligence\b",
        r"\bbi analyst\b",
        r"\banalytics\b",
        r"\bsolutions? engineer\b",
        r"\bsales engineer\b",
        r"\bsolution consultant\b",
        r"\btechnical consultant\b",
        r"\btechnology consultant\b",
        r"\bimplementation consultant\b",
        r"\btechnology strategy\b",
        r"\bdigital transformation\b",
        r"\binformation systems\b",
        r"\btechnology analyst\b",
        r"\bbusiness operations\b",
        r"\brevenue operations\b",
        r"\bgo[- ]to[- ]market\b",
        r"\bcommercial analytics\b",
        r"\bproduct strategy\b",
        r"\btechnical account\b",
    ),
    "finance-econ": (
        r"\bfinance\b",
        r"\bfinancial\b",
        r"\baccounting\b",
        r"\baudit\b",
        r"\btax\b",
        r"\bactuarial\b",
        r"\bbanking\b",
        r"\binvestment\b",
        r"\bcredit\b",
        r"\btreasury\b",
        r"\bwealth management\b",
        r"\brisk management\b",
        r"\brisk analyst\b",
        r"\bunderwrit(?:ing|er)\b",
        r"\beconomics?\b",
        r"\beconomist\b",
        r"\bcapital markets?\b",
        r"\binsurance\b",
        r"\bprivate equity\b",
        r"\basset management\b",
        r"\bcommercial banking\b",
        r"\bquantitative (?:finance|research|trading)\b",
        r"\bquant (?:research|trading)\b",
    ),
    "mechanical": (
        r"\bmechanical engineer(?:ing)?\b",
        r"\bmanufacturing engineer(?:ing)?\b",
        r"\bmanufacturing\b",
        r"\bcad\b",
        r"\bsolidworks\b",
        r"\bthermal engineer(?:ing)?\b",
        r"\bmaterials? engineer(?:ing)?\b",
        r"\bindustrial engineer(?:ing)?\b",
    ),
    "aero": (
        r"\baerospace\b",
        r"\baeronautical\b",
        r"\bpropulsion\b",
        r"\bflight sciences?\b",
        r"\bflight test\b",
        r"\bspace systems?\b",
        r"\bspacecraft\b",
        r"\borbital\b",
        r"\bavionics\b",
        r"\brocket\b",
        r"\bsatellite(?: systems?| engineer(?:ing)?)?\b",
    ),
    "electrical": (
        r"\belectrical engineer(?:ing)?\b",
        r"\belectronics? engineer(?:ing)?\b",
        r"\bhardware engineer(?:ing)?\b",
        r"\bcomputer engineer(?:ing)?\b",
        r"\bembedded(?: systems?| software)?\b",
        r"\bfirmware\b",
        r"\bfpga\b",
        r"\brf engineer(?:ing)?\b",
        r"\bsemiconductor\b",
        r"\basic\b",
        r"\bpcb\b",
        r"\bpower systems?\b",
        r"\bsignal processing\b",
        r"\bvlsi\b",
        r"\bavionics\b",
    ),
    # Policy and health stay as internal tags for now. The public UI can archive
    # them until Yartchives has dedicated source coverage for these fields.
    "policy": (
        r"\bpublic policy\b",
        r"\bpolicy (?:intern|analyst|fellow)\b",
        r"\bgovernment affairs\b",
        r"\bpublic affairs\b",
        r"\blegislative\b",
        r"\badvocacy\b",
        r"\bcivic engagement\b",
        r"\bgovernment relations\b",
        r"\binternational relations\b",
        r"\beconomic policy\b",
        r"\bresearch (?:and|&) policy\b",
    ),
    "health": (
        r"\bclinical\b",
        r"\bhealthcare\b",
        r"\bhealth care\b",
        r"\bpublic health\b",
        r"\bmedical\b",
        r"\bbiomedical\b",
        r"\bpatient\b",
        r"\bclinical research\b",
        r"\bpharmacy\b",
        r"\bpre[- ]?med\b",
        r"\blife sciences?\b",
        r"\bbiology (?:intern|research)\b",
        r"\blab(?:oratory)? (?:intern|assistant|research)\b",
    ),
}

SECTION_PROFILE_PATTERNS: dict[str, tuple[str, ...]] = {
    "cs": (
        r"^\s*software engineering\s*$",
        r"^\s*(?:data science|machine learning|artificial intelligence|ai/ml)\s*$",
    ),
    "tech-business": (
        r"^\s*product management\s*$",
        r"^\s*(?:business|product) analytics\s*$",
    ),
    "finance-econ": (
        r"^\s*quantitative finance\s*$",
    ),
}

_MECHANICAL_CONTEXT = re.compile(
    r"\b(mechanical|manufactur(?:ing|ability)|industrial|materials?|thermal|cad|solidworks)\b",
    flags=re.I,
)
_TEST_QUALITY = re.compile(r"\b(?:test|quality)(?: engineer(?:ing)?)?\b", flags=re.I)


def extract_source_markers(*values: str | None) -> list[str]:
    found: set[str] = set()
    for value in values:
        raw = value or ""
        for marker, key in SOURCE_MARKERS.items():
            if marker in raw:
                found.add(key)
    return sorted(found)


def clean_display_text(value: str | None) -> str:
    text = value or ""
    for marker in SOURCE_MARKERS:
        text = text.replace(marker, " ")
    text = re.sub(r"\s+", " ", text).strip()

    # Remove Markdown emphasis leaked from source tables, but do not rewrite
    # punctuation inside legitimate names.
    while len(text) >= 4 and (
        (text.startswith("**") and text.endswith("**"))
        or (text.startswith("__") and text.endswith("__"))
    ):
        text = text[2:-2].strip()
    while len(text) >= 2 and (
        (text.startswith("*") and text.endswith("*"))
        or (text.startswith("_") and text.endswith("_"))
    ):
        text = text[1:-1].strip()
    return text


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


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def classify_profiles(job: dict[str, Any]) -> list[str]:
    """Return conservative, role-based profile tags for a merged listing."""
    title = clean_display_text(job.get("title"))
    function_primary = clean_display_text(job.get("function_primary"))
    section = clean_display_text(job.get("section"))

    role_text = " ".join(x for x in (title, function_primary) if x).strip()
    tags: set[str] = set()

    for profile, patterns in PROFILE_PATTERNS.items():
        if _matches_any(role_text, patterns):
            tags.add(profile)

    # "Test Engineer" and "Quality Engineer" are cross-discipline. Only treat
    # them as mechanical when the same role has mechanical/manufacturing context.
    if _TEST_QUALITY.search(role_text) and _MECHANICAL_CONTEXT.search(role_text):
        tags.add("mechanical")

    # Only map a few narrow upstream section names whose meaning is unambiguous.
    # In particular, "Hardware Engineering" is intentionally NOT a section-level
    # Electrical tag; the title/function must independently indicate hardware/EE.
    for profile, patterns in SECTION_PROFILE_PATTERNS.items():
        if _matches_any(section, patterns):
            tags.add(profile)

    # These direct adapters admit rows only after strict CS/technology title
    # filtering. Preserve that provider-family evidence without trusting broad
    # aggregator profile tags or widening global title heuristics.
    if any(
        str(key).startswith(prefix)
        for key in (job.get("source_keys") or [])
        for prefix in STRICT_CS_SOURCE_PREFIXES
    ):
        tags.add("cs")

    if not tags:
        tags.add("general")
    return sorted(tags)


def enrich_document(doc: dict[str, Any]) -> bool:
    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Feed does not contain a jobs list")

    changed = False
    for job in jobs:
        if not isinstance(job, dict):
            continue

        raw_company = job.get("company")
        raw_title = job.get("title")
        markers = sorted(
            set(job.get("source_markers") or [])
            | set(extract_source_markers(raw_company, raw_title))
        )
        company = clean_display_text(raw_company)
        title = clean_display_text(raw_title)

        if job.get("company") != company:
            job["company"] = company
            changed = True
        if job.get("title") != title:
            job["title"] = title
            changed = True
        if markers:
            if job.get("source_markers") != markers:
                job["source_markers"] = markers
                changed = True
        elif "source_markers" in job:
            del job["source_markers"]
            changed = True

        education = classify_education(title)
        if education == "unspecified" and "advanced_degree" in markers:
            education = "graduate-only"
        opportunity_type = classify_opportunity_type(title, job.get("source_keys") or [])
        profiles = classify_profiles(job)

        if job.get("education_level") != education:
            job["education_level"] = education
            changed = True
        if job.get("opportunity_type") != opportunity_type:
            job["opportunity_type"] = opportunity_type
            changed = True
        if job.get("profiles") != profiles:
            job["profiles"] = profiles
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
