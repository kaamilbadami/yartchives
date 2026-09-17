# Apply Next recall audit

Feed snapshot: 2026-09-17T03:07:28.101490Z; inspection cache: 2026-09-17T03:09:22Z.
Audit profile: cs; target term: Summer 2027; visible set: Top 10.

## Funnel

- Full feed: 5,226.
- Relevant: 2,120 retained; 3,106 genuinely outside the selected profile tags.
- Term / eligibility: 1,495 retained; 470 known wrong-term and 155 known-ineligible/unavailable removed.
- Inspection pool: 855 selected; 640 relevant candidates have no inspection candidate mapping.
- Inspection state (eligible candidates): 472 inspected with substantive semantics, 108 inspected but mostly unknown, 255 queued, 14 failed/cooling down, and 6 selected with an unsupported shape.
- Authoritative-only gate: not active; 0 excluded solely for lacking authoritative inspection (915 would be excluded if such a gate were enabled).
- Ranking: 1,305 ranked; 190 canonical duplicates collapsed and 0 otherwise excluded during ranking; 10 visible and 1,295 below Top 10.

## Conclusion

Current Apply Next does not silently erase metadata-only opportunities: unknown inspection evidence is not a hard mismatch, and metadata-only jobs remain rankable.
The largest inspection-evidence bottleneck is **unsupported_provider_or_source_shape** (646 candidates). This remains an evidence-coverage limitation, but it is not a hard recommendation exclusion.
The visible-set bottleneck is the deliberate Top 10 cap: 1,295 otherwise-ranked candidates are below it.

Largest unsupported provider/source-shape buckets:
- source: 84
- lifeattiktok.com: 72
- jobs.lever.co: 66
- jobs.smartrecruiters.com: 26
- recruiting.paylocity.com: 19
