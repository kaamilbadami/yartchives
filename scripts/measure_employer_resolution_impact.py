#!/usr/bin/env python3
"""Measure which unresolved employers account for meaningful benchmark misses.

Attributes unresolved-employer misses to current benchmark/discovery evidence,
ranks unresolved employer/provider families by recoverable-role impact, and
distinguishes missing tenant identity, domain hints, unsupported ATS, and
genuinely unavailable sources.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Important: add project root to python path so scripts.* imports work
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.careers_resolver import provider_for
from scripts.employer_resolution_queue import _hint_identity_status, _url

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Point default audit file to the evaluated coverage file
    parser.add_argument("--audit", type=Path, default=Path("audit/northeast-midatlantic-cs-coverage-2026-09-17.json"))
    parser.add_argument("--universe", type=Path, default=Path("employer_universe.json"))
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    universe = json.loads(args.universe.read_text(encoding="utf-8"))

    employers = {}
    for e in universe.get("employers", []):
        employers[e["name"].casefold()] = e
        for a in e.get("aliases", []):
            employers[a.casefold()] = e

    unresolved_impact: dict[str, dict[str, any]] = {}

    for r in audit.get("results", []):
        if r.get("status") == "already_in_yartchives":
            continue

        company = r.get("company")
        if not company:
            continue

        emp = employers.get(company.casefold())
        if not emp:
            continue

        if emp.get("careers_url"):
            continue # Already resolved

        name = emp["name"]
        if name not in unresolved_impact:
            domains = set()
            for md in emp.get("seed_metadata", {}).values():
                domains.update(md.get("domain_hints", []))
            valid_domains = [d for d in domains if _url(d)]

            statuses = {_hint_identity_status(d) for d in valid_domains}
            families = {provider_for(d)["family"] for d in valid_domains}

            if not families:
                families = {"unknown/none"}

            # Categorize the unresolution reason
            if "tenant" in statuses:
                # Based on the criteria, differentiate unsupported ATS vs genuinely unavailable sources vs ready
                if any(f in {"custom_unknown", "unknown/none"} for f in families):
                    # We have a domain, it's considered tenant, but it's not a known provider pattern, so it's likely a genuinely unavailable source or unsupported ATS.
                    # As we do not know if custom ATS is unsupported or genuinely unavailable (e.g. requires JS/captcha), we classify as unsupported ATS/unavailable.
                    readiness = "unsupported_ats_or_unavailable"
                else:
                    readiness = "ready" # We have a tenant identity on a known provider
            elif "shared_provider" in statuses:
                readiness = "needs_tenant_identity"
            else:
                readiness = "no_domain_hint"

            unresolved_impact[name] = {
                "count": 0,
                "readiness": readiness,
                "families": families,
                "domains": valid_domains
            }

        unresolved_impact[name]["count"] += 1

    sorted_impact = sorted(unresolved_impact.items(), key=lambda x: (-x[1]["count"], x[0]))

    print("Unresolved Employer Impact:")
    print("===========================\n")
    for name, data in sorted_impact:
        families_str = ", ".join(sorted(data["families"]))
        domains_str = ", ".join(sorted(data["domains"])) or "none"
        print(f"Employer: {name}")
        print(f"  Misses: {data['count']}")
        print(f"  Readiness: {data['readiness']}")
        print(f"  Provider Families: {families_str}")
        print(f"  Domain Hints: {domains_str}")
        print()

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
