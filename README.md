# Yartchives

**A CS-first internship product focused on one question: what should I apply to next?**

Yartchives combines public internship sources into one normalized feed, then uses **Apply Next** to turn that feed into a decision queue instead of another job board to browse. The first beta is intentionally focused on Computer Science students.

## What the beta is trying to solve

Internship search is fragmented across employer sites, aggregators, spreadsheets, and student-maintained lists. Finding roles is only part of the problem; students still have to decide which opportunities are worth their time.

Yartchives is built around that second problem. Apply Next prioritizes known opportunities using profile fit, location preferences, posting evidence, freshness, and other existing ranking signals, while keeping the underlying evidence visible enough to understand the recommendation.

## Current product

- **CS-first beta:** non-CS career areas are being hidden from the initial beta experience while the underlying architecture remains extensible.
- **Apply Next:** a ranked recommendation queue designed to answer why a role is worth applying to and what the biggest concern is.
- **Local application state:** Saved, Applied, and Hidden state stays in the browser; no account is required.
- **Multi-source feed:** public opportunity feeds are normalized, reconciled, deduplicated, and refreshed centrally.
- **Evidence-aware recommendations:** authoritative posting evidence is preferred when available, with uncertainty preserved when it is not.
- **Coverage is measured, not assumed:** Yartchives does not claim to replace every discovery source until its explicit coverage contract is satisfied.

## Live repository status

<!-- yartchives-status:start -->
- **Beta scope:** CS-first
- **Feed refresh:** hourly GitHub Actions pipeline
- **Published listings:** 6,157
- **Distinct source labels:** 0
- **Coverage claim:** not yet certified as a complete single discovery source
<!-- yartchives-status:end -->

The status block above is generated from repository data by the feed workflow. Automation is only allowed to replace text between those markers; the rest of this README is product-owned.

## How the product works

Yartchives collects public opportunity data ahead of time instead of scraping sources in every visitor's browser. The pipeline normalizes role, employer, location, date, provenance, and application destinations; reconciles duplicates; enriches selected listings with authoritative posting evidence; validates the resulting feed; and publishes a static dataset for the frontend.

The frontend then applies the user's browser-local profile and preferences to the known feed. Apply Next ranks those opportunities without claiming that the feed represents the entire internship market.

## Sources and coverage

The project uses broad public aggregators as the discovery backbone and employer/ATS sources as targeted gap-fillers. Current source families include public internship trackers, employer ATS endpoints such as Workday/Greenhouse/iCIMS where supported, and the official USAJOBS Search API.

LinkedIn and Handshake are used as **discovery and audit surfaces**, not production scraping sources.

Federal opportunity data comes from **USAJOBS.gov**. Yartchives stores normalized discovery metadata and directs users to the employer, USAJOBS, or another validated application destination.

> Yartchives does not own employer application content. Listings are discovery metadata and links to the original or validated application destination.

The machine-readable `coverage_contract.json` defines the standard required before Yartchives can claim that a US undergraduate CS student can use it as their only discovery queue. Until those gates pass on a fresh independent benchmark, the product should be described as ranking the opportunities it knows about rather than providing complete market coverage.

## Beta feedback

Feedback provided through the "Submit feedback" action in the Apply Next queue is sent directly to a central serverless receiver (Formspree) configured by the product owner. Responses are minimal, capturing only the recommendation ID, rating, structured reason, optional note, and submission timestamp without including browser-local profile data or application state. The product owner can review submissions via the Formspree dashboard.

## Beta usage analytics

Yartchives sends a privacy-minimized per-session usage summary to the same central receiver so the beta can measure whether the core product flow is actually being used. The tracked event set is intentionally small: site opens, Apply Next opens, first profile creation, recommendation impressions, apply clicks, saves, hides, and submitted recommendation feedback.

Usage analytics do not send search text, profile fields, resume contents, exact location, job IDs, employer names, job titles, application URLs, saved/applied/hidden item IDs, or free-text feedback. Events are batched as counts behind a transient anonymous session ID rather than tied to a user account.

## Development approach

Yartchives is product-directed and heavily AI-assisted in implementation. Product scope, prioritization, beta criteria, and tradeoffs are set by the product owner; coding agents and automated GitHub workflows handle much of the implementation, testing, review routing, and maintenance.

The repository is intentionally structured so agent work remains bounded: issues define acceptance criteria, CI validates exact PR heads, resource locks reduce conflicting concurrent work, and separate automation controls merging.

## Repository map

- `apply-next*.js` / related CSS — Apply Next recommendation and profile experience
- `scripts/build_feed.py` and reconciliation scripts — feed generation and normalization
- `scripts/update_workday_inspections.py` and provider inspectors — bounded authoritative posting inspection
- `coverage_contract.json` and `audit/` — coverage definitions and benchmark evidence
- `data/listings.json` — generated normalized feed
- `.github/workflows/` — feed refresh, quality checks, autonomous dispatch, and merge automation

## Local development

```bash
python -m pip install -r requirements.txt
python scripts/download_latest_feed.py --pages-base https://kaamilbadami.github.io/yartchives
python -m http.server 8000
```

Then open `http://localhost:8000`.

## Automatic refreshes

`.github/workflows/update-feed.yml` runs hourly and can also be triggered manually. It rebuilds and validates the feed, then publishes `data/listings.json` as a versioned GitHub Actions artifact. Bounded inspection refreshes publish their cache separately. Pages deployments hydrate the latest validated artifacts before building, while the checked-in JSON files remain rollback/local-development fallbacks rather than the routine publication transport.
