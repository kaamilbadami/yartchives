# Follow-up Report: Largest Generic Miss Category Analysis

## Summary
The coverage audit has been successfully categorized according to the required `miss_category` mapping. The analysis of the benchmark (`audit/northeast-midatlantic-cs-coverage-2026-09-17.json`) indicates that the largest generic miss category is **`source_missing`** with 42 instances.

## Findings
Within the `source_missing` category, the most common URLs point to non-ATS discovery surfaces:
- `www.linkedin.com`: 15 instances
- `www.internships.com`: 4 instances

Additionally, there are several misses from standalone career sites (e.g., `www.textronsystems.com` - 4 instances, `careers.amtrak.com` - 3 instances, `jobs.citizensbank.com` - 3 instances).

## Recommendation for Next Follow-up
As per the `AGENTS.md` guidelines, Yartchives explicitly prohibits using LinkedIn or Handshake as production scraping sources. Thus, we cannot and should not build generic scraper adapters for `linkedin.com` or `internships.com`.

The correct engineering follow-up for these `source_missing` findings is to:
1. Trace the missing roles discovered on LinkedIn and Internships.com back to their authoritative employer Applicant Tracking Systems (ATS).
2. Configure durable direct adapters in `direct_sources.json` for each tracked employer/ATS combination (such as adding direct configurations for Textron Systems, Amtrak, and Citizens).
