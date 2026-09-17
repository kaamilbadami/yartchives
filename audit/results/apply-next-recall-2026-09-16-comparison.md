# Apply Next recall audit: root cause and fix

The audit used the checked-in feed generated at `2026-09-17T03:07:28.101490Z`, the inspection cache updated at `2026-09-17T03:09:22Z`, the repository-safe CS profile, Summer 2027, and Top 10 visibility.

Of 5,226 feed rows, 2,120 carry the CS relevance tag. The term and explicit eligibility gates retain 1,495: 470 known wrong-term rows, 124 graduate-only rows, and 31 authoritatively unavailable postings are removed. No explicit eligibility conflict was weakened.

The inherited authoritative-only gate then removed 915 of those 1,495 otherwise-eligible rows before ranking. After canonical deduplication, only 498 distinct candidates ranked. The hard gate made inspection architecture determine recommendation recall: 640 relevant candidates had no inspection mapping, 255 were queued behind bounded throughput, 14 were failed or cooling down, and six had unsupported URL shapes. The largest evidence bottleneck was the provider/source-shape bucket at 646 candidates, led by source-only links, `lifeattiktok.com`, Lever, SmartRecruiters, and Paylocity.

The generic fix removes only the authoritative-inspection predicate from ranking. It keeps canonical deduplication, explicit wrong-term/graduate/unavailable/authorization/clearance conflicts, scoring, and location preferences intact. The inspection-backed competition context also remains limited to authoritative rows, so metadata-only rows do not manufacture demand evidence.

With the fix, zero candidates are excluded solely for missing authoritative inspection and 1,305 distinct candidates rank—807 more than the baseline. Inspection coverage is still visible as an evidence-quality bottleneck, but unknown evidence no longer acts as a hard mismatch.
