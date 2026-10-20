#!/usr/bin/env python3
"""Build independent external-discovery benchmark runner.

Implements the flow:
persona -> bounded search plan -> external web/search discovery ->
authoritative employer/ATS validation -> human/reviewer relevance decision ->
frozen benchmark artifact
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Add project root to python path
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.careers_resolver import provider_for
from scripts.update_workday_inspections import inspect_posting_url

REQUIRED_DRAFT_FIELDS = [
    "persona_id", "company", "title", "location", "url", "source",
    "discovery_url", "discovery_query", "expected_state"
]

DISCOVERY_DOMAINS = {
    "linkedin.com", "www.linkedin.com", "indeed.com", "www.indeed.com",
    "handshake.com", "joinhandshake.com", "google.com", "www.google.com"
}

PERSONA_AREA_TO_FEED_PROFILE = {
    "computer_science": "cs",
    "business": "tech-business",
    "finance": "finance-econ",
    "engineering": "engineering",
}


def _feed_profile(persona: dict[str, Any]) -> str:
    area = str(persona.get("primary_area") or "").strip()
    return PERSONA_AREA_TO_FEED_PROFILE.get(area, area)

def _generate_search_plan(personas: list[dict[str, Any]], out_md: Path, out_csv: Path) -> None:
    lines = ["# Bounded Search Plan\n"]
    for p in personas:
        pid = p.get("id", "Unknown")
        lines.append(f"## Persona: {pid}")
        lines.append(f"- **Primary Area**: {p.get('primary_area')}")
        loc = p.get("location", {})
        lines.append(f"- **Location**: {loc.get('home_region')} / {loc.get('school_region')}")
        lines.append("- **Role Intents**:")
        for intent in p.get("role_intent", []):
            lines.append(f"  - {intent}")
        lines.append("- **Suggested Queries**:")
        for intent in p.get("role_intent", [])[:3]:
            for state in loc.get("preferred_regions", [])[:2]:
                lines.append(f"  - `{intent} intern {state} employer careers`")
        lines.append("")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote search plan to {out_md}")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REQUIRED_DRAFT_FIELDS)
    print(f"Wrote draft CSV template to {out_csv}")


def _verify_discovery(row: dict[str, Any], persona: dict[str, Any], url_kind: str, inspection: dict[str, Any]) -> dict[str, str]:
    dims = {
        "active_status": "unknown",
        "internship_term": "unknown",
        "paid_status": "unknown",
        "undergraduate_eligibility": "unknown",
        "graduation_windows": "unknown",
        "work_authorization": "unknown"
    }

    if url_kind != "authoritative":
        return dims

    status = inspection.get("status")
    if status == "unsupported_url":
        return dims
    if status in {"unavailable", "changed_response", "failed"}:
        dims["active_status"] = "rejected"
        return dims

    posting = inspection.get("posting") or {}
    if posting.get("application_status") == "closed":
        dims["active_status"] = "rejected"
        return dims

    dims["active_status"] = "verified"

    title = str(posting.get("title") or "").lower()

    if "unpaid" in title:
        dims["paid_status"] = "rejected"
    else:
        dims["paid_status"] = "verified"

    if any(grad_keyword in title for grad_keyword in {"graduate", "phd", "postdoc", "master"}) and "intern" in title:
        if persona.get("student_stage") in {"Freshman", "Sophomore", "Junior"}:
            dims["undergraduate_eligibility"] = "rejected"
    else:
        dims["undergraduate_eligibility"] = "verified"

    if "2026" in title or "2025" in title or "fall" in title or "spring" in title:
        if "summer 2027" not in title:
            dims["internship_term"] = "rejected"
    elif "intern" in title or "co-op" in title or "coop" in title or "student" in title:
        dims["internship_term"] = "verified"

    requirements = inspection.get("requirements") or {}
    grad_reqs = requirements.get("graduation", {}).get("required", [])
    if grad_reqs:
        for req in grad_reqs:
            stmt = str(req.get("statement") or "").lower()
            if "2026" in stmt and "2028" not in stmt and "2029" not in stmt:
                dims["graduation_windows"] = "rejected"
    if dims["graduation_windows"] != "rejected":
        dims["graduation_windows"] = "verified"

    dims["work_authorization"] = "verified"
    work_auth = requirements.get("work_authorization", {}).get("required", [])
    if work_auth:
        for req in work_auth:
            stmt = str(req.get("statement") or "").lower()
            if "require" in stmt and "sponsorship" in stmt:
                dims["work_authorization"] = "unknown"

    return dims

def _run_review(
    personas_doc: dict[str, Any],
    draft_csv: Path,
    out_json: Path,
    benchmark_name: str,
    skip_interactive: bool = False
) -> int:
    personas_by_id = {p["id"]: p for p in personas_doc.get("personas", []) if "id" in p}

    with draft_csv.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    discoveries = []

    for idx, row in enumerate(rows, 1):
        pid = row.get("persona_id", "").strip()
        if not pid or pid not in personas_by_id:
            print(f"Row {idx}: Invalid or missing persona_id '{pid}'. Skipping.")
            continue

        persona = personas_by_id[pid]
        url = row.get("url", "").strip()
        domain = urlparse(url).hostname or ""

        provider_info = provider_for(url) if url else {"family": "unknown"}

        if domain in DISCOVERY_DOMAINS:
            url_kind = "discovery_surface"
        else:
            url_kind = "authoritative"

        print(f"\n--- Reviewing Discovery {idx}/{len(rows)} ---")
        print(f"Persona: {pid} ({persona.get('primary_area')})")
        print(f"Company: {row.get('company')}")
        print(f"Title:   {row.get('title')}")
        print(f"URL:     {url}")
        print(f"Kind:    {url_kind} (Detected provider: {provider_info.get('family')})")
        print(f"Source:  {row.get('source')} (Query: {row.get('discovery_query')})")

        inspection = inspect_posting_url(url)
        dims = _verify_discovery(row, persona, url_kind, inspection)

        overall = "verified"
        if any(v == "rejected" for v in dims.values()):
            overall = "rejected"
        elif any(v == "unknown" for v in dims.values()):
            overall = "unknown"

        print(f"Verification: {overall.upper()} ({dims})")

        if not skip_interactive:
            ans = input("Include this discovery in the benchmark? [Y/n/q]: ").strip().lower()
            if ans == 'q':
                print("Aborting review.")
                sys.exit(1)
            if ans == 'n':
                print("Skipped.")
                continue

        discovery = {
            "company": row.get("company", "").strip(),
            "title": row.get("title", "").strip(),
            "location": row.get("location", "").strip(),
            "url": url,
            "source": row.get("source", "").strip(),
            "discovery_url": row.get("discovery_url", "").strip(),
            "discovery_query": row.get("discovery_query", "").strip(),
            "url_kind": url_kind,
            "expected_state": row.get("expected_state", "").strip(),
            "expected_profile": _feed_profile(persona),
            "persona_id": pid,
            "verification_decision": overall,
            "verification_dimensions": dims,
            "verification_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "verification_evidence": inspection,
        }

        discoveries.append(discovery)

    if not discoveries:
        print("\nNo discoveries approved. Exiting.")
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    profiles = sorted(list(set(_feed_profile(personas_by_id[d["persona_id"]]) for d in discoveries)))
    states = sorted(list(set(d["expected_state"] for d in discoveries if d["expected_state"])))

    artifact = {
        "name": benchmark_name,
        "collected_at": now,
        "benchmark_fixed_at": now,
        "scope": {
            "profiles": profiles,
            "states": states
        },
        "sampling_method": {
            "selection_independent_of_yartchives": True,
            "notes": "Generated via external-discovery benchmark runner."
        },
        "discoveries": discoveries
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nFrozen benchmark artifact with {len(discoveries)} discoveries saved to {out_json}")

    if skip_interactive and any(d.get("verification_decision") == "unknown" for d in discoveries):
        print("\nError: Benchmark contains 'unknown' verifications and --skip-interactive is set.")
        print("Failing workflow closed to queue for review.")
        return 1

    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--personas", type=Path, default=Path("audit/personas/trust-benchmark-personas.json"))
    parser.add_argument("--persona", default="all", help="Persona ID to include, or 'all'")

    parser.add_argument("--generate-plan", type=Path, help="Output markdown search plan")
    parser.add_argument("--generate-csv", type=Path, help="Output CSV template")

    parser.add_argument("--draft-csv", type=Path, help="Input CSV with drafted discoveries")
    parser.add_argument("--output-json", type=Path, help="Output frozen JSON benchmark artifact")
    parser.add_argument("--benchmark-name", type=str, default="Independent External Discovery Benchmark")
    parser.add_argument("--skip-interactive", action="store_true", help="Accept all valid rows without prompting")

    args = parser.parse_args()

    if not args.personas.exists():
        print(f"Error: Personas file not found at {args.personas}", file=sys.stderr)
        return 1

    personas_doc = json.loads(args.personas.read_text(encoding="utf-8"))
    selected_personas = personas_doc.get("personas", [])
    if args.persona != "all":
        selected_personas = [p for p in selected_personas if p.get("id") == args.persona]
        if not selected_personas:
            print(f"Error: unknown persona {args.persona!r}", file=sys.stderr)
            return 1

    if args.generate_plan or args.generate_csv:
        if not args.generate_plan or not args.generate_csv:
            print("Error: Both --generate-plan and --generate-csv are required to generate a plan.", file=sys.stderr)
            return 1
        _generate_search_plan(selected_personas, args.generate_plan, args.generate_csv)
        return 0

    if args.draft_csv and args.output_json:
        if not args.draft_csv.exists():
            print(f"Error: Draft CSV not found at {args.draft_csv}", file=sys.stderr)
            return 1
        return _run_review(personas_doc, args.draft_csv, args.output_json, args.benchmark_name, args.skip_interactive)

    print("Error: Must specify either generation flags (--generate-plan & --generate-csv) OR review flags (--draft-csv & --output-json).", file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
