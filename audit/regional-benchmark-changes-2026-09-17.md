# Regional benchmark changes — 2026-09-17

## Benchmark

Added `audit/samples/ct-ny-md-dc-cs-2026-09-17.json`, an independently collected public-web benchmark of 106 unique current undergraduate-friendly CS/technology internships, co-ops, and student roles:

| State | Listings |
|---|---:|
| Connecticut | 20 |
| New York | 34 |
| Maryland | 27 |
| Washington, DC | 25 |
| **Total** | **106** |

The sample was collected from employer/ATS search, ordinary web search, LinkedIn, Indeed, Internships.com, and one major aggregator. It includes large and smaller employers and a mix of Greenhouse, Lever, Workday, iCIMS, USAJOBS, Ashby, custom career pages, and discovery-only records. Employer concentration is capped at five rows. Discovery-only URLs are labeled in the input and retain the observed source and requisition key; no row was derived from the Yartchives feed.

`first_discovered_at` is intentionally absent: the available evidence supports collection time and current-posting status, but not a reliable first-discovery timestamp.

## Tooling

- Per-listing `expected_state` / `expected_profile` now overrides multi-state or multi-profile sample scope. This prevents a four-state benchmark from requiring every listing to match all four states.
- Coverage reports now include `by_state`, `missing_by_state`, `missing_by_reason_code`, and `missing_by_discovery_source` summaries.
- ATS classification recognizes SuccessFactors, Taleo, Eightfold, USAJOBS, and an explicit `employer/custom` fallback; discovery-platform URLs are classified as `discovery-only`.
- Added regression coverage for multi-state expectations, regional miss summaries, and the expanded ATS families.

## Generated audit outputs

- `audit/ct-ny-md-dc-cs-coverage-2026-09-17.json`
- `audit/ct-ny-md-dc-cs-coverage-2026-09-17.md`
- `audit/coverage-contract-status-ct-ny-md-dc-2026-09-17.json`
- `audit/coverage-contract-status-ct-ny-md-dc-2026-09-17.md`

The current audit reports 47.2% capture, 30.2% visible-under-expected-filters, and 100.0% authoritative-link rate among captured/probably captured rows. The contract status is `not_ready_as_only_source`: the benchmark-size, geographic-breadth, capture, visible, and latency-measurement gates do not pass. This PR measures those gaps only; it does not change ingestion, ranking, or employer/source coverage.
