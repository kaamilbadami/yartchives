# Apply Next recall audit

Feed snapshot: 2026-09-17T02:53:17.304905Z; inspection cache: 2026-09-17T02:55:09Z.
Audit profile: cs; target term: Summer 2027; visible set: Top 10.

## Funnel

- Full feed: 5,225.
- Relevant: 2,120 retained; 3,105 genuinely outside the selected profile tags.
- Term / eligibility: 1,496 retained; 470 known wrong-term and 154 known-ineligible/unavailable removed.
- Inspection pool: 856 selected; 640 relevant candidates have no inspection candidate mapping.
- Inspection state (eligible candidates): 461 inspected with substantive semantics, 102 inspected but mostly unknown, 273 queued, 13 failed/cooling down, and 7 selected with an unsupported shape.
- Authoritative-only gate: modeled baseline; 933 excluded solely for lacking authoritative inspection (933 would be excluded if such a gate were enabled).
- Ranking: 481 ranked; 82 canonical duplicates collapsed and 0 otherwise excluded during ranking; 10 visible and 471 below Top 10.

## Conclusion

This baseline models the authoritative-only behavior inherited from main before the fix; metadata-only candidates are removed before ranking.
The largest inspection-evidence bottleneck is **unsupported_provider_or_source_shape** (647 candidates). Because the authoritative-only gate is active, this evidence limitation contributes directly to recommendation loss.
The visible-set bottleneck is the deliberate Top 10 cap: 471 otherwise-ranked candidates are below it.

Largest unsupported provider/source-shape buckets:
- source: 84
- lifeattiktok.com: 72
- jobs.lever.co: 66
- jobs.smartrecruiters.com: 26
- recruiting.paylocity.com: 19
