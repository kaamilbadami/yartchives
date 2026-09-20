import json
from pathlib import Path
from datetime import datetime, timezone
import subprocess
from collections import defaultdict
import re

ROOT = Path(__file__).resolve().parent.parent

def main():
    with open(ROOT / "data" / "listings.json") as f:
        feed = json.load(f)

    jobs = feed.get("jobs", [])

    script = '''
    const fs = require('fs');
    const applyNext = require('./apply-next.js');
    const input = JSON.parse(fs.readFileSync(0, 'utf-8'));
    const jobs = input.jobs;
    const cache = input.cache;
    const reference = new Date();

    // Ensure all jobs have the inspection field
    jobs.forEach(job => {
        job._inspection = applyNext.inspectionForJob(job, cache) || {};
    });

    const ranked = applyNext.rankJobs(jobs, {}, reference);

    console.log(JSON.stringify(ranked.slice(0, 50).map(item => item.job)));
    '''

    with open(ROOT / "data" / "workday-inspections.json") as f:
        cache = json.load(f)

    process = subprocess.run(
        ["node", "-e", script],
        input=json.dumps({"jobs": jobs, "cache": cache}),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=True
    )

    top50 = json.loads(process.stdout)
    top10 = top50[:10]

    print("Top 10:")
    top10_inspected = sum(1 for job in top10 if job.get("_inspection", {}).get("status") == "inspected")
    print(f"Inspected: {top10_inspected}/10")

    print("\nTop 50:")
    top50_inspected = sum(1 for job in top50 if job.get("_inspection", {}).get("status") == "inspected")
    print(f"Inspected: {top50_inspected}/50")

    metadata_only = [job for job in top50 if job.get("_inspection", {}).get("status") != "inspected"]

    print("\nMetadata-only Breakdown:")
    categories = defaultdict(int)
    reasons = []

    for job in metadata_only:
        url = job.get("url") or ""
        status = job.get("_inspection", {}).get("status")

        # Check cache explicitly to get more detailed status if _inspection is empty/None
        url_key = url
        # Simple extraction for some providers to match cache key
        if "?" in url:
            url_key = url.split("?")[0]

        # Actually, let's just use what's in _inspection
        if "jobvite.com" in url or "paylocity.com" in url or "careerpuck.com" in url or "careers.microsoft.com" in url:
            categories["unsupported_provider"] += 1
            reasons.append((job.get("company"), url, "unsupported_provider"))
        elif "greenhouse.io" in url or "jobs.dropbox.com" in url or "gh_jid" in url:
            if "job-boards.eu.greenhouse.io" in url or "jobs.dropbox.com" in url:
                categories["unsupported_source_shape (greenhouse)"] += 1
                reasons.append((job.get("company"), url, "unsupported_source_shape (greenhouse)"))
            else:
                categories[f"other: {status}"] += 1
                reasons.append((job.get("company"), url, f"other: {status}"))
        elif "careers.principal.com" in url:
            categories["unsupported_source_shape (icims)"] += 1
            reasons.append((job.get("company"), url, "unsupported_source_shape (icims)"))
        elif status == "queued" or status == "retry_cooldown":
            categories["throughput_queue"] += 1
            reasons.append((job.get("company"), url, f"queue_status: {status}"))
        elif status == "unsupported_url":
            categories["unsupported_source_shape"] += 1
            reasons.append((job.get("company"), url, "unsupported_url"))
        else:
            # Let's inspect the actual cache for these URLs to find out why they are "other: None"
            cache_entry = None
            for key, entry in cache.get("entries", {}).items():
                if key in url or url in key:
                    cache_entry = entry
                    break

            if cache_entry:
                status_cache = cache_entry.get("inspection", {}).get("status")
                categories[f"cache_state: {status_cache}"] += 1
                reasons.append((job.get("company"), url, f"cache_state: {status_cache}"))
            else:
                categories["not_in_cache"] += 1
                reasons.append((job.get("company"), url, "not_in_cache"))

    for k, v in categories.items():
        print(f"  {k}: {v}")

    print("\nDetailed breakdown of unsupported shapes:")
    for company, url, reason in reasons:
        print(f"  {company}: {url} -> {reason}")

if __name__ == "__main__":
    main()
