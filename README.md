# Yartchives

**A CS-first internship product focused on one question: what should I apply to next?**

Yartchives combines public internship sources into one normalized feed, then uses **Apply Next** to turn that feed into a ranked decision queue instead of another job board to browse.

[**Live Demo**](https://kaamilbadami.github.io/yartchives) · [**How Apply Next works**](#apply-next)

## Why I built it

Internship search is fragmented across employer sites, aggregators, spreadsheets, and student-maintained lists. Finding roles is only part of the problem; students still have to decide which opportunities are actually worth their time.

Yartchives is built around that second problem: collect known opportunities centrally, preserve the evidence behind them, and rank them against a student's preferences so the product can answer **what should I apply to next?**

## What it does

### Apply Next

Apply Next turns the feed into a recommendation queue rather than a search result list. It uses the user's browser-local profile and preferences together with posting freshness, location fit, authoritative posting evidence, and other ranking signals to prioritize opportunities.

Recommendations are designed to surface both **why a role is worth considering** and the **largest concern or uncertainty** instead of presenting an unexplained score.

### Unified internship feed

Yartchives collects public opportunity data ahead of time instead of scraping sources in each visitor's browser. The pipeline normalizes role, employer, location, dates, provenance, and application destinations across multiple source families.

### Evidence-aware recommendations

When available, Yartchives enriches discovered listings with evidence from authoritative employer or ATS postings. Uncertainty is preserved when authoritative evidence is unavailable rather than silently treated as verified.

### Local application tracking

Saved, Applied, and Hidden state stays in the browser. No account is required for the core beta experience.

## How it works

```text
Public feeds · ATS platforms · USAJOBS
                  ↓
               Ingestion
                  ↓
       Normalize + reconcile + dedupe
                  ↓
       Authoritative posting inspection
                  ↓
          Validation / quality gates
                  ↓
          Versioned static feed
                  ↓
          Apply Next ranking
                  ↓
        GitHub Pages frontend
```

The data pipeline normalizes heterogeneous listings, reconciles duplicates, enriches selected roles with authoritative posting evidence, validates the result, and publishes a static dataset for the frontend.

The frontend then applies browser-local profile and preference data to that validated feed and ranks opportunities without requiring a user account or sending profile data through the ingestion pipeline.

## Technical highlights

- **Multi-source ingestion:** broad public aggregators provide the discovery backbone, while employer and ATS sources are used as targeted gap-fillers.
- **Normalization and reconciliation:** heterogeneous source records are mapped into a shared schema, reconciled across sources, and deduplicated before publication.
- **Authoritative-source enrichment:** selected listings can be inspected against employer or ATS postings to improve confidence in role details and application destinations.
- **Recommendation ranking:** Apply Next combines profile fit, location preferences, freshness, posting evidence, and other ranking dimensions into a prioritized queue.
- **Scheduled data pipeline:** GitHub Actions refreshes and validates feed artifacts on a recurring schedule instead of rebuilding the dataset in each client.
- **Quality gates and CI:** feed validation, tests, workflow checks, and exact-PR-head validation protect generated data and application behavior before changes land.
- **Privacy-conscious analytics:** beta usage and recommendation feedback are collected as minimal aggregate/session-level signals without sending profile fields, resumes, searches, exact locations, or local application history.
- **Browser-local state:** user preferences and Saved / Applied / Hidden state remain local to the client for the core experience.

## Architecture / repository map

- `apply-next*.js` and related CSS — recommendation ranking, presentation, profile, location, and Apply Next interaction logic
- `scripts/build_feed.py` and reconciliation scripts — feed generation, normalization, and source reconciliation
- provider inspection scripts such as `scripts/update_workday_inspections.py` — bounded authoritative posting enrichment
- `data/listings.json` — generated normalized feed used as a local/rollback fallback
- `coverage_contract.json` and `audit/` — explicit coverage requirements and benchmark evidence
- `.github/workflows/` — feed refreshes, validation, deployment, autonomous task dispatch, and merge automation
- `app.js`, `ui.js`, `ux.js`, and related styles — static frontend application shell and interactions

## Engineering & reliability

Yartchives treats feed generation as a data pipeline rather than a collection of client-side scrapers. Generated artifacts are validated before publication, and deployments hydrate the latest validated feed artifact while checked-in data remains available as a fallback for rollback and local development.

The repository also uses bounded automation for maintenance and implementation work: issues define acceptance criteria, CI validates the exact code being merged, resource locks reduce conflicting concurrent work, and merge automation is separated from implementation.

### Live repository status

<!-- yartchives-status:start -->
- **Beta scope:** CS-first
- **Feed refresh:** hourly GitHub Actions pipeline
- **Published listings:** 6,196
- **Distinct source labels:** 0
- **Coverage claim:** not yet certified as a complete single discovery source
<!-- yartchives-status:end -->

This block is generated from repository data by the feed workflow. Automation is restricted to replacing the text between the markers above.

## Sources and coverage

The first beta is intentionally focused on Computer Science students, while the underlying ingestion and ranking architecture is designed to remain extensible.

Broad public aggregators are the discovery backbone. Employer and ATS sources such as Workday, Greenhouse, and iCIMS are targeted gap-fillers where supported, and federal opportunity data comes from the official USAJOBS Search API.

LinkedIn and Handshake are used as **discovery and audit surfaces**, not production scraping sources.

Yartchives does not claim to represent the entire internship market. The machine-readable `coverage_contract.json` defines the evidence required before the product can make stronger coverage claims; until those gates pass on an independent benchmark, Apply Next should be understood as ranking the opportunities Yartchives currently knows about.

> Yartchives does not own employer application content. Listings are discovery metadata and links to the original or another validated application destination.

## Development workflow

Yartchives uses AI-assisted development alongside automated GitHub workflows. I define product scope, architecture, acceptance criteria, prioritization, and engineering tradeoffs; coding agents assist with bounded implementation and maintenance tasks, while CI and repository automation validate and coordinate changes.

This workflow is designed to keep automated work reviewable: tasks are scoped through issues, concurrent changes are constrained with resource locks, tests run against exact PR heads, and merging is controlled separately from implementation.

## Local development

```bash
python -m pip install -r requirements.txt
python scripts/download_latest_feed.py --pages-base https://kaamilbadami.github.io/yartchives
python -m http.server 8000
```

Then open `http://localhost:8000`.

## Automatic refreshes

`.github/workflows/update-feed.yml` runs hourly and can also be triggered manually. It rebuilds and validates the feed, then publishes `data/listings.json` as a versioned GitHub Actions artifact. Bounded inspection refreshes publish their cache separately. Pages deployments hydrate the latest validated artifacts before building, while the checked-in JSON files remain rollback/local-development fallbacks rather than the routine publication transport.
