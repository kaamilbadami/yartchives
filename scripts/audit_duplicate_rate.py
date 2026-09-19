"""Measure duplicate incidence in current output and identify duplicate families."""

import argparse
import collections
import json
import re
from pathlib import Path

# Add sibling imports for identity logic
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reconcile_workday_duplicates import posting_identity_key

def normalized_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r'[^a-z0-9\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def audit_feed(feed_path: Path):
    with feed_path.open() as f:
        doc = json.load(f)
    jobs = doc.get('jobs', [])

    total_jobs = len(jobs)
    print(f"Total jobs: {total_jobs}")

    # Track exactly by url
    by_exact_url = collections.defaultdict(list)

    # Track by ATS identity
    by_identity = collections.defaultdict(list)

    # Track by semantic signature (company + normalized title)
    by_semantic = collections.defaultdict(list)

    ats_families = collections.defaultdict(int)

    for j in jobs:
        url = j.get('url') or ""
        by_exact_url[url].append(j)

        identity = posting_identity_key(url)
        if identity:
            by_identity[identity].append(j)
            ats_families[identity[0]] += 1

        sig = (j.get('company', '').lower().strip(), normalized_title(j.get('title', '')))
        by_semantic[sig].append(j)

    canonical_dupes = sum(len(g) - 1 for g in by_exact_url.values() if len(g) > 1)
    identity_dupes = sum(len(g) - 1 for g in by_identity.values() if len(g) > 1)
    semantic_dupes = sum(len(g) - 1 for g in by_semantic.values() if len(g) > 1)

    print("\n--- Exact Canonical Duplicates ---")
    print(f"Duplicates by exact URL: {canonical_dupes}")
    print(f"Rate: {canonical_dupes / total_jobs:.2%}")

    print("\n--- Duplicates by Major ATS / Source Family ---")
    print(f"Duplicates by ATS identity key: {identity_dupes}")
    print(f"Rate: {identity_dupes / total_jobs:.2%}")
    for ats, count in sorted(ats_families.items()):
        dupes_in_ats = sum(len(g) - 1 for k, g in by_identity.items() if k[0] == ats and len(g) > 1)
        print(f"  {ats}: {dupes_in_ats} duplicates across {count} total postings")

    print("\n--- Semantic Duplicates (Company + Normalized Title) ---")
    print(f"Likely semantic duplicates: {semantic_dupes}")
    print(f"Rate: {semantic_dupes / total_jobs:.2%}")

    if semantic_dupes > 0:
        print("\nLargest generic semantic duplicate families:")
        sorted_sem = sorted([g for g in by_semantic.values() if len(g) > 1], key=len, reverse=True)
        for i in range(min(5, len(sorted_sem))):
            g = sorted_sem[i]
            print(f"  Group {i+1} ({len(g)} items): {g[0].get('company')} - {g[0].get('title')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=Path("data/listings.json"))
    args = parser.parse_args()
    audit_feed(args.feed)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
