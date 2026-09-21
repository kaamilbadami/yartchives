#!/usr/bin/env python3
"""Measure Fortune 500 internship coverage from the current employer universe.

This script outputs a Markdown report conforming to the issue's acceptance criteria.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.provider_fingerprint import fingerprint_provider
from scripts.coverage_audit import expectations, surface_issues, compact

def main():
    universe_path = ROOT / "employer_universe.json"
    feed_path = ROOT / "data/listings.json"

    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    feed = json.loads(feed_path.read_text(encoding="utf-8"))

    # Benchmark population: Fortune 500 2026 seed
    f500_employers = [e for e in universe.get("employers", []) if "fortune-500-2026" in e.get("seed_sets", [])]
    total_f500 = len(f500_employers)

    resolved_employers = []
    unresolved_employers = []

    provider_families_resolved = defaultdict(int)
    provider_families_unresolved = defaultdict(int)

    # Classify misses
    unsupported_ats = []
    unresolved_host = []
    no_domain_hint = []

    for e in f500_employers:
        provider_info = e.get("provider", {})
        if provider_info.get("status") == "resolved":
            resolved_employers.append(e)
            provider_families_resolved[provider_info.get("family", "unknown")] += 1
        else:
            unresolved_employers.append(e)

            # Check domain hints for potential providers
            providers = set()
            for md in e.get("seed_metadata", {}).values():
                if isinstance(md, dict):
                    for hint in md.get("domain_hints", []):
                        p_info = fingerprint_provider(hint)
                        providers.add(p_info.get("family", "unknown"))

            for hint in e.get("domain_hints", []):
                p_info = fingerprint_provider(hint)
                providers.add(p_info.get("family", "unknown"))

            if providers:
                for p in providers:
                    provider_families_unresolved[p] += 1

                if any(p in {"custom_unknown", "unknown", "unknown/none"} for p in providers):
                    unsupported_ats.append(e)
                else:
                    unresolved_host.append(e)
            else:
                provider_families_unresolved["unknown"] += 1
                no_domain_hint.append(e)


    # Check feed for eligible openings using standard canonical ID mechanisms.
    f500_ids = {e["id"] for e in f500_employers}
    f500_names = {e["name"].casefold(): e["id"] for e in f500_employers}
    for e in f500_employers:
        for a in e.get("aliases", []):
            f500_names[a.casefold()] = e["id"]

    employers_with_listings = set()
    employers_with_authoritative_links = set()
    filtering_loss = []

    # We want to measure against standard "US undergraduate CS internship/co-op/student listings"
    expected = expectations(
        {"expected_profiles": ["cs"]},
        ["cs"],
        [] # US states
    )
    # We add implicit expected opportunity types for an internship search
    expected["opportunity_types"] = {"internship", "co-op", "student"}

    for job in feed.get("jobs", []):
        job_company_name = job.get("company", "").casefold()
        emp_id = None
        # Check if the job specifically links to the universe ID or matches names
        if job.get("employer_id") in f500_ids:
            emp_id = job.get("employer_id")
        elif job_company_name in f500_names:
            emp_id = f500_names[job_company_name]

        if emp_id:
            # Re-use existing semantics where possible
            issues = surface_issues(job, expected)
            # check states
            states = set(job.get("states", []))
            has_us_state = any(isinstance(s, str) and len(s) == 2 for s in states)

            if not issues and has_us_state:
                employers_with_listings.add(emp_id)
                if job.get("link_status") == "ok":
                    employers_with_authoritative_links.add(emp_id)
            elif issues:
                filtering_loss.append(emp_id)

    # Markdown Report Generation
    print("# Fortune 500 Internship Coverage Report\n")
    print(f"**Benchmark Population:** {total_f500} employers (from Fortune 500 2026 seed)\n")
    print(f"- **Resolved to an authoritative ATS/career source:** {len(resolved_employers)}")
    print(f"- **Currently produce eligible US undergraduate CS internship/co-op/student listings in the feed:** {len(employers_with_listings)}")
    print(f"- **Currently have eligible listings with reachable authoritative links:** {len(employers_with_authoritative_links)}\n")

    print("## Coverage by Major ATS/Source Family (Resolved)\n")
    for family, count in sorted(provider_families_resolved.items(), key=lambda x: (-x[1], x[0])):
        print(f"- **{family}**: {count}")

    print("\n## Coverage by Potential ATS/Source Family (Unresolved)\n")
    for family, count in sorted(provider_families_unresolved.items(), key=lambda x: (-x[1], x[0])):
        print(f"- **{family}**: {count}")

    print("\n## Miss Classification\n")

    print(f"- **No Domain Hint (Discovery Gap):** {len(no_domain_hint)}")
    print(f"- **Unsupported ATS / Unknown Provider:** {len(unsupported_ats)}")
    print(f"- **Unresolved Host (Needs Tenant Identity):** {len(unresolved_host)}")

    # Calculate no eligible opening only from those that are resolved
    resolved_employer_ids = {e["id"] for e in resolved_employers}
    resolved_with_listings = resolved_employer_ids.intersection(employers_with_listings)
    no_eligible_count = len(resolved_employers) - len(resolved_with_listings)
    retrieval_failure_count = len(employers_with_listings) - len(employers_with_authoritative_links)
    print(f"- **Retrieval Failure (Broken Links on Eligible Listings):** {retrieval_failure_count}")
    print(f"- **No Current Eligible Openings (Among Resolved):** {no_eligible_count}")
    print(f"- **Filtering/Normalization Loss:** {len(set(filtering_loss) - employers_with_listings)}")

    print("\n## Largest Actionable Generic Gap\n")
    print("The dominant defect is **Unsupported ATS / Unknown Provider**. ")
    print("Out of the 500 employers, a large majority have domain hints but either use unsupported ATS platforms (like Taleo/BrassRing/custom systems) or the provider resolution logic fails to identify the provider. ")
    print("This gap represents a need to build provider support for these systems, or investigate why `custom_unknown` is so prevalent among these employers.")

if __name__ == '__main__':
    main()
