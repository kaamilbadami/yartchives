# Yartchives feed quality audit report

Feed snapshot: `2026-09-18T11:29:19.618406Z`
Audit reference: `2026-09-18T11:29:19.618406+00:00`

## Executive summary

- Total indexed jobs: **5915**
- Direct employer/ATS application links: **5178**
- Source-only (no direct URL) postings: **623**
- Confirmed closed/unavailable postings: **48**
- Transient source retrieval failures: **0**

## 1. Stale and unavailable listings

This category independently measures proof of staleness versus transient upstream failures or age review.

- **Confirmed unavailable postings**: **48** (proven via authoritative ATS inspection status `unavailable`).
- **Transient retrieval failures**: **0** (jobs belonging solely to sources that failed to fetch during generation; this is a transient network/source failure, NOT proof of closed jobs).
- **Age review bucket (posted >= 90 days)**: **297** (flagged for review; not proof of staleness).

## 2. Destinations and link quality

Link kind distribution:

- `direct`: **5178**
- `listing`: **114**
- `source`: **623**

### Workday direct-apply contract

- Total Workday direct links: **1922**
- Contract violations: **1822** (static URLs lacking `/apply` path or unpopulated verification status/timestamp).

### Top non-direct link hosts

- `no-link`: **623**
- `jobright.ai`: **98**
- `zapply.jobs`: **16**

### Top source-only (no-link) contributors

- `speedyapply-ai`: **425**
- `applyguy`: **128**
- `vansh-cscareers`: **40**
- `speedyapply`: **21**
- `dreamwork-tech`: **13**
- `zapply`: **5**
- `simplify`: **3**
- `us-feed-workday-walmart-walmartexternal`: **1**
- `us-feed-workday-cox-cox-external-career-site-1`: **1**
- `us-feed-workday-cibc-search`: **1**

## 3. Missing dates and provenance

- Missing posting timestamp (`posted_at`): **162**
- Missing provenance label (`posted_date_provenance`): **5753**

Date provenance distribution:

- *(none)*

## 4. Suspicious date normalization

- Future dates (`posted_at > reference`): **0**
- Source conflicts (7d+ observation spread): **0**
- Aggregator overriding authoritative date: **0**

## 5. Root causes and remediation

- **Largest generic provider cause**: Workday direct-apply contract violations (static URLs from aggregators lack verification timestamps and `/apply` target paths until validated through Workday inspectors).
- **Generic defect fixed**: `build_feed.py` date merging was updated to enforce provenance hierarchy (`authoritative_employer` / `authoritative_government` > `aggregator`), preventing aggregator timestamps from overwriting authoritative dates during deduplication.
- **Prioritized follow-up**: Extend static Workday link repair workflows and resolve source-only/no-link postings from aggregator lists.
