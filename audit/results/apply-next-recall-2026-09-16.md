# Apply Next recall audit

Feed snapshot: 2026-09-16T20:53:36.775214Z; inspection cache: 2026-09-16T20:55:17Z.
Audit profile: cs; target term: Summer 2027; visible set: Top 10.

## Funnel

- Full feed: 4,672.
- Relevant: 1,947 retained; 2,725 genuinely outside the selected profile tags.
- Term / eligibility: 1,433 retained; 418 known wrong-term and 96 known-ineligible/unavailable removed.
- Inspection pool: 456 selected; 977 relevant candidates have no inspection candidate mapping.
- Inspection state (eligible candidates): 48 inspected with substantive semantics, 5 inspected but mostly unknown, 398 queued, 5 failed/cooling down, and 0 selected with an unsupported shape.
- Authoritative-only gate: not active; 0 actually excluded solely for lacking authoritative inspection (1,380 would be excluded if such a gate were enabled).
- Ranking: 1,433 ranked; 10 visible and 1,423 below Top 10.

## Conclusion

Current Apply Next does not silently erase metadata-only opportunities: unknown inspection evidence is not a hard mismatch, and metadata-only jobs remain rankable.
The largest inspection-evidence bottleneck is **unsupported_provider_or_source_shape** (977 candidates). This is an evidence-coverage limitation, not an actual recommendation exclusion under current behavior.
The visible-set bottleneck is the deliberate Top 10 cap: 1,423 otherwise-ranked candidates are below it.

Largest unsupported provider/source-shape buckets:
- job-boards.greenhouse.io: 204
- jobs.ashbyhq.com: 151
- lifeattiktok.com: 72
- jobs.lever.co: 56
- source: 46
