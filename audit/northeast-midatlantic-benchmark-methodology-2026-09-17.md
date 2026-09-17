# Northeast / Mid-Atlantic undergraduate CS benchmark methodology

## Objective and freeze order

This benchmark measures Yartchives recall for publicly discoverable,
undergraduate-relevant CS internships and co-ops in CT, NY, NJ, PA, DE, MD,
DC, VA, MA, and RI during the 2026-2027 recruiting cycle. It is not a source
registry and was not derived from the Yartchives feed.

The 142-row benchmark was fixed in commit `622bd9d` before the production feed
was loaded for comparison. Authoritative URL recovery was allowed before that
freeze only when it preserved the already selected opportunity. Yartchives
matches and misses did not affect inclusion.

## Sampling design

The design has two independently collected panels:

1. Preserve the 106-role CT/NY/MD/DC panel dated 2026-09-17 as a frozen legacy
   panel. This keeps the earlier denominator auditable and permits comparison
   with the prior audit.
2. Add an equal quota of six eligible roles in each newly covered state: NJ,
   PA, DE, VA, MA, and RI.

For each supplemental state, ordinary web search was run using these query
families in fixed order: software engineering, data science, cybersecurity,
and information technology. The template was `2027 {query family} intern
{state name} employer careers`. Candidates were considered in search-result
order, round-robin across query families, until the state quota was filled.

An eligible row had to be publicly discoverable, located in the target state,
open or publicly verifiable at collection time, part of the current recruiting
cycle, and relevant to an undergraduate CS or adjacent technical major.
Graduate-only, high-school-only, full-time, nontechnical, closed/unverifiable,
and duplicate requisitions were excluded. No employer could contribute more
than three supplemental roles in one state.

LinkedIn, Indeed, university career pages, and other aggregators are discovery
or audit surfaces only. When an employer or ATS URL was discoverable, it became
the listing URL while the original discovery surface/query remained in
`discovery_url` and `discovery_query`.

## Fixed benchmark profile

- Unique roles: **142**
- State distribution: NY 34, MD 27, DC 25, CT 20, and 6 each in NJ, PA, DE,
  VA, MA, and RI
- Discovery sources: ordinary web search 53, LinkedIn 51, employer/ATS search
  23, Internships.com 11, Indeed 3, major aggregator 1
- URL destinations: 95 direct authoritative postings, 7 authoritative
  search/program pages, 40 discovery-surface URLs
- Explicit discovery URLs: 102 (71.8%)
- Largest employer share: 5/142 (3.5%)
- Largest city share: 34/142 (23.9%, New York)
- Largest ATS family share: recorded in the machine-readable benchmark-quality
  report

All declared constraints pass in
`audit/northeast-midatlantic-benchmark-quality-2026-09-17.json`.

## Production comparison

The fixed benchmark was compared with the production feed snapshot generated
at `2026-09-17T20:10:44.120221Z`.

- Captured or probably captured: **71/142 (50.0%)**
- Visible under expected filters: **49/142 (34.5%)**
- True missing listings: **71/142 (50.0%)**
- Present but filtered/misclassified: **12**
- Duplicate-resolution issues: **10**
- Missing-role reasons: 44 uncovered sources, 25 known-employer missing roles,
  and 2 configured-source listing misses
- Missing by state: CT 10, NY 7, NJ 4, PA 0, DE 6, MD 21, DC 14, VA 2, MA 2,
  RI 5

The coverage contract remains `not_ready_as_only_source`: geographic breadth,
freshness, and link-authority gates pass, while benchmark size, capture,
visible recall, and measurable discovery latency do not.

## Known limitations

- The legacy panel was preserved rather than resampled, so the full benchmark
  is not evenly allocated: the original four jurisdictions contribute 106 of
  142 rows. The supplemental states have small six-role denominators; their
  state percentages have high sampling variance.
- Forty legacy rows lack an explicit `discovery_url`. Their source labels and
  listing URLs remain intact, but their original query/result position cannot
  be reconstructed reliably. No provenance was fabricated after the fact.
- Ordinary search ranking is time-, locale-, and index-dependent. Stored query
  strings make the process repeatable in procedure, not guaranteed to return
  identical result ordering later.
- The benchmark is a public-web recall sample, not a census of all internships.
  Handshake and LinkedIn access constraints, early campus-only recruiting,
  expired postings, and unindexed small employers can create coverage gaps in
  the benchmark frame itself.
- `first_discovered_at` is unavailable, so discovery-latency measurement remains
  unmeasurable. `discovered_at` on supplemental rows records collection time,
  not first public availability.
- Multi-location postings are assigned to the audited in-scope location. Remote
  roles without a concrete in-scope work location were not used to fill quotas.
- Some thin-market DE and RI rows retain discovery/program URLs because a
  stable requisition-level employer URL was not publicly recoverable. They are
  explicitly labeled and count against the authoritative-link rate.

This work changes benchmark/audit artifacts and validation only. It does not
change ingestion, ranking, production source adapters, employer resolution, or
Apply Next behavior.
