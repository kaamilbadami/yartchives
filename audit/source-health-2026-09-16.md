# Yartchives production source-health audit — 2026-09-16

## Scope and evidence

Audited the repository at `origin/main` commit `7e920b3` (`chore: refresh opportunity feed`) without rebuilding, fetching, scraping, or modifying feed/configuration data. Evidence is the checked-in `data/listings.json` snapshot generated at `2026-09-16T14:36:28.319890Z`, plus `sources.json`, `direct_sources.json`, `scripts/build_feed.py`, `scripts/direct_ct_workday.py`, `scripts/audit_feed.py`, and `scripts/validate_feed.py`.

The available source-health schema records `ok`, `configured`, `count`, and `name`; it does not record fetch time, last-success time, latency, response status, or historical runs. “Contribution” below means the number of deduplicated listings whose `source_keys` includes that source. Because one listing can have multiple source keys, contribution counts are not additive.

## Executive findings

- The snapshot contains 5,046 listings, of which 4,625 pass the audit’s default undergraduate-friendly internship/co-op/student filter.
- All 18 sources present in the feed metadata are configured and marked `ok: true`; there are no confirmed source failures or recurring errors in the available snapshot.
- Broad sources dominate the feed: Simplify contributes 1,675 listings, Dreamwork Tech 731, ApplyGuy 654, Zapply 592, SpeedyApply 562, and Dreamwork Business 554.
- The broad backbone does not appear demonstrably degraded from this snapshot alone: the largest sources have substantial yields and 338 listings are represented by multiple upstream sources. A historical comparison is unavailable, so a recent regression cannot be ruled out.
- Direct sources show the clearest configured-but-ineffective signal: Travelers and Avangrid yield zero; Hartford and Allegion yield two and one respectively. They are not confirmed failures because each is marked healthy and all have `minimum_expected: 0`.
- Freshness is only partially observable. The feed generation timestamp is current for the snapshot, but there is no per-source last-success/fetched timestamp. 229 listings lack `posted_at`, limiting listing-level freshness measurement.
- No duplicate job IDs remain after ingestion. Upstream overlap is measurable: 338 listings have two or more source keys; among CS-eligible listings, 231 do. This indicates overlap, but not necessarily a defect.

## Source health and yield

| Source | Configured / `ok` | Feed count | Deduplicated contribution | Unique to source | Assessment |
|---|---:|---:|---:|---:|---|
| Simplify | yes / yes | 1,796 | 1,675 | 1,635 | backbone; high yield, overlap present |
| Dreamwork Tech | yes / yes | 731 | 731 | 642 | backbone; high yield |
| ApplyGuy | yes / yes | 654 | 654 | 493 | backbone; high yield |
| Zapply | yes / yes | 600 | 592 | 565 | backbone; high yield |
| SpeedyApply | yes / yes | 591 | 562 | 402 | backbone; high overlap |
| Dreamwork Business | yes / yes | 556 | 554 | 512 | backbone; high yield |
| Vansh / CSCareers | yes / yes | 265 | 258 | 176 | meaningful yield |
| Summer 2027 Internships | yes / yes | 125 | 125 | 71 | moderate yield |
| Campus to Career | yes / yes | 114 | 114 | 68 | moderate yield; no CS-unique contribution in CS audit |
| Public Sector | yes / yes | 100 | 97 | 97 | narrow/specialized; all contribution unique |
| USAJOBS | yes / yes | 44 | 44 | 44 | small specialized source |
| The Hartford (direct) | yes / yes | 2 | 2 | 0 | unexpectedly tiny; confirmed low yield, not confirmed failure |
| Travelers (direct) | yes / yes | 0 | 0 | 0 | zero yield; configured but ineffective in snapshot |
| Avangrid (direct) | yes / yes | 0 | 0 | 0 | zero yield; configured but ineffective in snapshot |
| Gartner (direct) | yes / yes | 1 | 1 | 1 | unexpectedly tiny; not confirmed failure |
| IAT Insurance Group (direct) | yes / yes | 1 | 1 | 1 | unexpectedly tiny; not confirmed failure |
| RTX / Pratt & Whitney (direct) | yes / yes | 1 | 1 | 1 | unexpectedly tiny; not confirmed failure |
| Allegion / Stanley Access Technologies (direct) | yes / yes | 1 | 1 | 0 | unexpectedly tiny; not confirmed failure |

The “feed count” is the source adapter’s reported output in `data.listings.json`; “contribution” is recalculated from final `source_keys`. Differences reflect deduplication and source-key assignment behavior.

## Freshness and source errors

The only feed-level freshness marker is `generated_at: 2026-09-16T14:36:28.319890Z`. Source metadata has no `fetched_at`, `last_success`, or historical health fields. Therefore:

- Confirmed: the checked-in feed was generated at that timestamp, and every source currently reports `ok: true`.
- Not measurable: source-by-source freshness, time since each source’s last successful fetch, error recurrence, and trend/regression.
- Listing-level limitation: 229 of 5,046 listings have no `posted_at`; age-based audits can only evaluate the remainder.

No `error` field is present for any current source, and `validate_feed.py --strict-sources` passes. This is evidence of no currently recorded failure, not proof that upstream sources have never failed.

## Duplicate and overlap signals

There are zero duplicate listing IDs in the final feed. Across all listings, 338 have two or more upstream `source_keys` (6.7% of the final feed). In the CS-specific audit, 231 of 2,107 eligible CS listings are multi-source (11.0%).

CS contribution/unique counts show the heaviest overlap by non-unique share among major sources: Simplify 1,675/1,635 unique, Dreamwork Tech 731/642, ApplyGuy 654/493, Zapply 592/565, SpeedyApply 562/402, and Dreamwork Business 554/512. These are measurable duplicate/overlap patterns after deduplication, not confirmed source defects. The source-only link fallback is concentrated in Vansh (41), SpeedyApply (14), and ApplyGuy (8), while Public Sector has 97 listing links; this is a link-quality/attribution risk rather than evidence of source-health failure.

## Direct-source assessment

All six configured direct sources are marked healthy. Four yield one or two listings, and two yield zero. Since every direct configuration sets `minimum_expected` to zero, the existing validation cannot flag these as ineffective. The zero-yield Travelers and Avangrid sources are confirmed as low-yield in this snapshot, but their cause is ambiguous: no matching openings, upstream query/filter behavior, or ingestion/API behavior could each explain the result. The one-to-two listing sources are similarly confirmed tiny, not confirmed broken.

## Highest-leverage reliability investigations

1. Add historical per-source run telemetry—fetch timestamp, response/status category, duration, raw count, normalized count, and error history—so freshness regressions and recurring failures can be distinguished from ordinary market variation.
2. Investigate the zero/tiny direct Workday yields for Travelers, Avangrid, Hartford, Gartner, IAT, RTX, and Allegion by comparing raw API result counts, query terms, pagination, and title filters against the final counts; do not infer failure from zero yield alone.
3. Establish source-level yield and overlap baselines for the broad backbone (especially Simplify, Dreamwork Tech, ApplyGuy, SpeedyApply, Zapply, and Dreamwork Business), including alerts for material count drops and unusual duplicate-rate changes.

## Limitations

- This is a single checked-in snapshot; no prior feed snapshots or live re-fetch were used.
- Source-health metadata is binary/current and lacks per-source timestamps, status codes, latency, and historical errors.
- `source_keys` measures attribution after ingestion, not raw upstream row counts or exact duplicate observations.
- Zero/tiny yield may reflect the current market, source-side filtering, or missing matching listings; only the low yield itself is confirmed.
- No LinkedIn or Handshake data was accessed.
