import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import subprocess
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.provider_fingerprint import fingerprint_provider

def main():
    feed_path = ROOT / "data" / "listings.json"
    cache_path = ROOT / "data" / "workday-inspections.json"

    if not feed_path.exists() or not cache_path.exists():
        print("Required data files not found.")
        return

    with open(feed_path) as f:
        feed = json.load(f)

    with open(cache_path) as f:
        cache = json.load(f)

    jobs = feed.get("jobs", [])
    listing_index = cache.get("listing_index", {})
    entries = cache.get("entries", {})

    # Pre-attach inspections matching canonical identity lookup
    for job in jobs:
        job_id = str(job.get("id") or "")
        canonical = listing_index.get(job_id)
        if canonical:
            entry = entries.get(canonical)
            if isinstance(entry, dict):
                job["_inspection"] = entry.get("inspection")
        if "_inspection" not in job or job["_inspection"] is None:
            job["_inspection"] = {}

    script = '''
    const fs = require('fs');
    const applyNext = require('./apply-next.js');
    const input = JSON.parse(fs.readFileSync(0, 'utf-8'));
    const jobs = input.jobs;
    const reference = new Date();

    const ranked = applyNext.rankJobs(jobs, {}, reference);

    const output = ranked.map(item => {
        const job = item.job;
        const summary = applyNext.summarizeInspection(job);
        return {
            job: job,
            state: summary.state
        };
    });

    console.log(JSON.stringify(output));
    '''

    process = subprocess.run(
        ["node", "-e", script],
        input=json.dumps({"jobs": jobs}),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=True
    )

    ranked_jobs = json.loads(process.stdout)

    def print_stats(pool_name, pool_jobs):
        total = len(pool_jobs)
        if total == 0:
            print(f"{pool_name}: 0 jobs")
            return

        states = Counter(j.get("state") for j in pool_jobs)
        inspected = states.get("inspected", 0)
        unavailable = states.get("unavailable", 0)
        metadata = states.get("metadata-only", 0)
        unknown = states.get("unknown", 0)

        print(f"=== {pool_name} Coverage ===")
        print(f"Total:       {total}")
        print(f"Inspected:   {inspected} ({inspected/total*100:.1f}%)")
        print(f"Unavailable: {unavailable} ({unavailable/total*100:.1f}%)")
        print(f"Metadata:    {metadata} ({metadata/total*100:.1f}%)")
        print(f"Unknown:     {unknown} ({unknown/total*100:.1f}%)")
        print()

    print_stats("Top 10", ranked_jobs[:10])
    print_stats("Top 50", ranked_jobs[:50])
    print_stats("Full Pool", ranked_jobs)

    metadata_jobs = [j for j in ranked_jobs if j.get("state") == "metadata-only"]
    categories = defaultdict(int)

    for item in metadata_jobs:
        job = item["job"]
        url = job.get("url") or ""
        status = job.get("_inspection", {}).get("status")

        if "jobvite.com" in url or "paylocity.com" in url or "careerpuck.com" in url or "careers.microsoft.com" in url:
            categories["unsupported_provider"] += 1
        elif "greenhouse.io" in url or "jobs.dropbox.com" in url or "gh_jid" in url:
            if "job-boards.eu.greenhouse.io" in url or "jobs.dropbox.com" in url:
                categories["unsupported_source_shape (greenhouse)"] += 1
            else:
                categories[f"other: {status}"] += 1
        elif "careers.principal.com" in url:
            categories["unsupported_source_shape (icims)"] += 1
        elif status == "queued" or status == "retry_cooldown":
            categories["throughput_queue"] += 1
        elif status == "unsupported_url":
            categories["unsupported_source_shape"] += 1
        else:
            if status:
                categories[f"cache_state: {status}"] += 1
            else:
                cache_entry = None
                for key, entry in entries.items():
                    if key in url or url in key:
                        cache_entry = entry
                        break

                if cache_entry:
                    status_cache = cache_entry.get("inspection", {}).get("status")
                    categories[f"cache_state: {status_cache}"] += 1
                else:
                    categories["not_in_cache"] += 1

    provider_counts = Counter()
    for item in metadata_jobs:
        job = item["job"]
        url = job.get("url") or ""
        fingerprint = fingerprint_provider(url)
        family = fingerprint.get("family", "unknown")
        provider_counts[family] += 1

    print("=== Full Pool Metadata-Only by Provider Family ===")
    for family, count in provider_counts.most_common():
        print(f"  {family}: {count}")

    print("\n=== Metadata-only Breakdown by Reason ===")
    for k, v in categories.items():
        print(f"  {k}: {v}")

    print("\nPrioritized Action:")
    if provider_counts:
        top_family = provider_counts.most_common(1)[0][0]
        print(f"The largest actionable gap is '{top_family}'. Extend authoritative inspection coverage to this provider family to improve full-pool quality.")
        print("This prioritized follow-up addresses the bounded generic defect dominating metadata-only coverage.")
    else:
        print("No metadata-only gaps found.")

if __name__ == "__main__":
    main()
