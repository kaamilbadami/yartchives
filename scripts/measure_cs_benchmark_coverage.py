#!/usr/bin/env python3
"""Measure High-Value CS Employer Benchmark coverage.

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
    cs_benchmark_path = ROOT / "data/employer-seeds/cs-benchmark.json"

    if not cs_benchmark_path.exists():
        print(f"Error: CS Benchmark seed file not found at {cs_benchmark_path}", file=sys.stderr)
        sys.exit(1)

    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    cs_benchmark_seed = json.loads(cs_benchmark_path.read_text(encoding="utf-8"))

    # Benchmark population: CS benchmark seed
    benchmark_employers = []
    for e in universe.get("employers", []):
        if "cs-benchmark" in e.get("seed_sets", []):
            benchmark_employers.append(e)

    total_benchmark = len(benchmark_employers)

    resolved_employers = []
    unresolved_employers = []

    provider_families_resolved = defaultdict(int)
    provider_families_unresolved = defaultdict(int)

    # Classify misses
    unsupported_ats = []
    unresolved_host = []
    no_domain_hint = []
    filtering_loss = []
    retrieval_failure = []

    # Per-employer tracking
    employer_status = {}

    for e in benchmark_employers:
        emp_id = e["id"]
        employer_status[emp_id] = {
            "name": e["name"],
            "authoritative_source_resolution": False,
            "detected_provider_family": "unknown",
            "eligible_listings_count": 0,
            "authoritative_links_count": 0
        }

        provider_info = e.get("provider", {})
        if provider_info.get("status") == "resolved":
            resolved_employers.append(e)
            family = provider_info.get("family", "unknown")
            provider_families_resolved[family] += 1
            employer_status[emp_id]["authoritative_source_resolution"] = True
            employer_status[emp_id]["detected_provider_family"] = family
        else:
            unresolved_employers.append(e)

            # Check domain hints for potential providers
            providers = set()
            for md in e.get("seed_metadata", {}).values():
                if isinstance(md, dict):
                    for hint in md.get("domain_hints", []):
                        # Also check apply_host as hint for state-of-ats
                        p_info = fingerprint_provider(hint)
                        providers.add(p_info.get("family", "unknown"))

            if providers:
                for p in providers:
                    provider_families_unresolved[p] += 1

                # Combine multiple if present
                employer_status[emp_id]["detected_provider_family"] = ", ".join(sorted(providers))

                if any(p in {"custom_unknown", "unknown", "unknown/none"} for p in providers):
                    unsupported_ats.append((e, providers))
                else:
                    unresolved_host.append((e, providers))
            else:
                provider_families_unresolved["unknown"] += 1
                no_domain_hint.append(e)
                employer_status[emp_id]["detected_provider_family"] = "unknown"

    # Check feed for eligible openings using standard canonical ID mechanisms.
    benchmark_ids = {e["id"] for e in benchmark_employers}
    benchmark_names = {e["name"].casefold(): e["id"] for e in benchmark_employers}
    for e in benchmark_employers:
        for a in e.get("aliases", []):
            benchmark_names[a.casefold()] = e["id"]

    employers_with_listings = set()
    employers_with_authoritative_links = set()

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
        if job.get("employer_id") in benchmark_ids:
            emp_id = job.get("employer_id")
        elif job_company_name in benchmark_names:
            emp_id = benchmark_names[job_company_name]

        if emp_id:
            # Re-use existing semantics where possible
            issues = surface_issues(job, expected)
            # check states
            states = set(job.get("states", []))
            has_us_state = any(isinstance(s, str) and len(s) == 2 for s in states)

            if not issues and has_us_state:
                employers_with_listings.add(emp_id)
                employer_status[emp_id]["eligible_listings_count"] += 1
                if job.get("link_status") == "ok":
                    employers_with_authoritative_links.add(emp_id)
                    employer_status[emp_id]["authoritative_links_count"] += 1
            elif issues:
                filtering_loss.append(emp_id)

    # Markdown Report Generation
    print("# High-Value CS Employer Benchmark Coverage Report\n")
    print(f"**Benchmark Population:** {total_benchmark} employers\n")
    print(f"- **Resolved to an authoritative ATS/career source:** {len(resolved_employers)}")
    print(f"- **Currently produce eligible US undergraduate CS internship/co-op/student listings in the feed:** {len(employers_with_listings)}")
    print(f"- **Currently have eligible listings with reachable authoritative links:** {len(employers_with_authoritative_links)}\n")

    print("## Coverage by Major ATS/Source Family (Resolved)\n")
    for family, count in sorted(provider_families_resolved.items(), key=lambda x: (-x[1], x[0])):
        print(f"- **{family}**: {count}")

    print("\n## Miss Classification\n")

    # Calculate misses dynamically
    resolved_employer_ids = {e["id"] for e in resolved_employers}
    resolved_with_listings = resolved_employer_ids.intersection(employers_with_listings)
    no_eligible_count = len(resolved_employers) - len(resolved_with_listings)

    retrieval_failure_count = len(employers_with_listings) - len(employers_with_authoritative_links)

    miss_categories = {
        "Unsupported ATS/Source Family": len(unsupported_ats),
        "Unresolved Host": len(unresolved_host),
        "Retrieval Failure (Broken Links on Eligible Listings)": retrieval_failure_count,
        "No Current Eligible Openings": no_eligible_count,
        "Filtering/Normalization Loss": len(set(filtering_loss) - employers_with_listings),
        "Unknown / No Domain Hint": len(no_domain_hint)
    }

    for name, count in miss_categories.items():
        print(f"- **{name}:** {count}")

    largest_miss_category = max(miss_categories.items(), key=lambda x: x[1])
    largest_miss_source_family = max(provider_families_unresolved.items(), key=lambda x: x[1])

    print(f"\n**Largest recurring miss category:** {largest_miss_category[0]} ({largest_miss_category[1]})")
    print(f"**Largest recurring unresolved source family:** {largest_miss_source_family[0]} ({largest_miss_source_family[1]})")

    print("\n## Per-Employer Status\n")
    print("| Employer | Authoritative Resolution | Source Family | Eligible Listings | Authoritative Apply Links |")
    print("|----------|--------------------------|---------------|-------------------|---------------------------|")
    for emp_id, status in sorted(employer_status.items(), key=lambda x: x[1]["name"].lower()):
        resolution = "Yes" if status["authoritative_source_resolution"] else "No"
        family = status["detected_provider_family"]
        listings = status["eligible_listings_count"]
        links = status["authoritative_links_count"]
        print(f"| {status['name']} | {resolution} | {family} | {listings} | {links} |")

if __name__ == '__main__':
    main()
