# External employer seed audit — 2026-09-17

Read-only audit of external employer/ATS seed evidence against the Fortune-backed employer universe on `codex/fortune-500-2026-seed-catalog` at `d2243053f559601eb242c17f760f400751da4482`.

No production employer records were changed.

## Sources

- ResumeAI / State of ATS 2026 canonical CSV: 738 employer rows. This audit only treats rows with `verified=true` and a non-empty `apply_host` as high-confidence employer/host candidates.
- Latmay ATS Career Page URLs v1.1: 69,638 validated canonical career-board URLs across 40 ATS platforms, August 2026 snapshot. It has no authoritative company field, so it is provider/URL evidence only and cannot create employer identities in this audit.

## Results

- Fortune-backed employer universe: **549 employers**
- State of ATS rows: **738**
- State of ATS verified rows with an apply host: **548**
- Verified-host rows matching an existing Yartchives employer: **155**
- Existing employers with no current domain hint that could gain a verified apply host: **147**
- Verified-host rows not matching the current universe: **393 candidate new employers**

The 393 rows are not automatically production-safe. They are high-confidence external seed candidates because the source marks them verified and publishes an apply host; Yartchives should still preserve provenance and validate identity before promotion.

## Provider-family gaps in verified-host evidence

These ATS labels appear in the authoritative verified-host subset but are not currently represented by Yartchives' provider fingerprint families:

- Internal ATS: 11
- Kenexa BrassRing: 6
- USAJobs: 6
- Paradox: 3
- Cornerstone OnDemand: 3
- Oleeo: 2
- BeeSite: 2
- Jobvite: 2
- Workable: 1
- Deel: 1
- Dayforce: 1
- eArcu: 1
- Cegid Talentsoft: 1
- Rippling: 1
- ADP: 1
- SilkRoad: 1
- Teamwork Online: 1

These counts are evidence for prioritization, not a recommendation to implement every platform. Provider work should still be chosen by independent internship-recall impact.

## Large board-index signal

Latmay's 69,638 board URLs span 40 platforms. Its largest platform cohorts include Greenhouse (14,341), Lever (8,540), Workable (7,075), Ashby (5,712), Workday (5,410), BambooHR (3,184), JOIN (2,994), Breezy HR (2,597), Dayforce (2,181), Getro (1,804), iCIMS (1,622), Jobvite (1,139), Rippling (1,276), and others.

Because the board index lacks company metadata, URL slugs are deliberately not treated as employer identities. Its job is to provide second-source board/provider evidence and to expose provider families worth measuring against benchmark misses.

## Repeatable command

```bash
python scripts/external_employer_seed_audit.py \
  employer_universe.json \
  /path/to/state-of-ats-2026/companies.csv \
  --board-dataset /path/to/ats_career_page_urls.csv \
  --json-output audit/external-employer-seed-audit.json \
  --markdown-output audit/external-employer-seed-audit.md
```

## Decision rule

Employer-universe growth is a means, not the product metric. Continue broad seed expansion while it materially improves independent internship benchmark recall. When additional employer cohorts produce little recall gain and misses are dominated by enumeration, classification, deduplication, or freshness, shift engineering effort to those bottlenecks instead.
