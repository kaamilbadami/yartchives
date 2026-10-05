# Evidence Report: Issue #908 - Reduce unresolved provider discovery gaps

## What was tested
I investigated the coverage gap candidate `source-registry:unknown-provider-resolution`, which reports that 348 benchmark employers remain unresolved without a known ATS fingerprint in their current domain hints. I verified the metric generation logic in `scripts/coverage_gap_candidates.py` and the resolution queue logic in `scripts/employer_resolution_queue.py`. I extracted the domain hints for all 348 employers and sampled their resolution using `scripts/careers_resolver.py`.

## Measured before/after impact
- **Before:** 348 unresolved benchmark employers with unknown ATS provider family.
- **After:** 348 unresolved benchmark employers with unknown ATS provider family (no-code conclusion).

## Why the proposed paths are insufficient
The employers forming this gap (e.g., `apple.com`, `abm.com`, `advanceautoparts.com`) only possess generic corporate domain names in their `domain_hints` or `seed_metadata` (such as `apple.com` or `jobs.apple.com` without identifying path footprints). Since `provider_fingerprint.py` maps domain or URL segments to ATS families, it cannot deterministically assign a provider family to a bare corporate domain without crawling the site to discover the actual ATS platform (e.g., crawling `advanceautoparts.com` discovers a Phenom integration).

Therefore, it is logically impossible to reduce this "unknown family" gap via static pattern matching improvements without either:
1. Adding employer-specific exceptions (which is prohibited by the acceptance criteria).
2. Assuming a specific ATS for generic corporate domains (which would cause massive false positives).
3. Pre-crawling these employers and hardcoding their detected ATS URLs into the seed benchmark metadata (which is the job of the `employer_resolution_lifecycle.py` and not a code-level fix).

The logic extracting `domain_hints` in `_hint_families` correctly aggregates from both the root-level employer object and `seed_metadata`. The metric functions as intended by accurately reporting that without crawling, these employers remain completely undiscoverable from their seed hints.

## Smallest concrete follow-up experiment
Run `scripts/employer_resolution_lifecycle.py` with an increased employer budget (e.g., `employer_budget=500`) against the current universe to autonomously crawl and resolve these generic hints into specific ATS platforms, which will then persist the actual provider URL and decrease this gap.
