# Yartchives

**A multi-source opportunity platform I built to make internship and early-career searches more organized and accessible across different fields.**

I got tired of bouncing between separate internship lists, job boards, and spreadsheets — especially once I started looking beyond one narrow type of role. Yartchives pulls public opportunity feeds into one searchable place, normalizes them, removes obvious duplicates, and lets each person filter the same feed around what they actually want.

## What it does

- Aggregates public internship and early-career feeds into one dataset.
- Normalizes company, role, location, date, source, and application links.
- Deduplicates overlapping listings before they ever reach the browser.
- Supports public profiles for Computer Science, **Tech + Business**, Finance/Economics, Mechanical Engineering, Aerospace/Astronautical Engineering, and Electrical/Computer Engineering. Policy/Government and Premed/Health remain internal tags until their dedicated source coverage is strong enough to restore publicly.
- Keeps saved, applied, and hidden listings in the user's browser — no account required.
- Refreshes the feed automatically with GitHub Actions instead of making every visitor scrape every source themselves.
- Keeps the last known data from a source if that source temporarily fails.

## Why the architecture changed

An earlier browser-only prototype fetched and parsed every source on page load. That worked, but it got slow as the number of sources grew. Yartchives now does that work ahead of time in GitHub Actions and serves the frontend one prebuilt `data/listings.json` file. The site stays static and cheap to host while the expensive parsing and deduplication happen off the user's device.

## Sources

Current source adapters include public feeds from Simplify, Zapply, Vansh/CSCareers, SpeedyApply, ApplyGuy, Dreamwork, the Jobright public-sector list, Campus to Career, other public internship trackers, and the official USAJOBS Search API. Each listing keeps source attribution.

Federal opportunity data comes from **USAJOBS.gov**. Yartchives stores normalized discovery metadata only and directs users back to USAJOBS or the listed application destination to view and apply.

> Yartchives does not own or republish employer application content. Listings are discovery metadata and links back to the employer or original public source.

## Local development

```bash
python -m pip install -r requirements.txt
python scripts/build_feed.py
python -m http.server 8000
```

Then open `http://localhost:8000`.

## Workday posting inspection

`scripts/workday_inspector.py` retrieves one authoritative public Workday job
URL through Workday's public CXS JSON detail interface and emits conservative,
evidence-backed structured facts:

```bash
python scripts/workday_inspector.py \
  "https://tenant.wd5.myworkdayjobs.com/en-US/Careers/job/Location/Role_REQ-123"
```

Structured Workday fields supply the posting text, requisition ID, and
locations. Requirement facts retain the posting's normalized wording and are
separated into `required`, `preferred`, and `unspecified` evidence. A field with
no explicit evidence has `classification: "unknown"`; absence is never treated
as eligibility. Retrieval and response-shape failures are returned as structured
inspection statuses. `inspect_listing()` attaches that result to a copy of a
base listing, so a failed inspection does not replace or remove discovery data.

The inspector is intentionally not part of the scoring formula or frontend. It
is the retrieval/normalization boundary for a later Apply Next integration.

## Coverage audits

`scripts/coverage_audit.py` compares a sample of opportunities discovered outside Yartchives against the current feed. It accepts JSON, JSONL, or CSV and produces both machine-readable results and a human-readable action queue. The first intended audit is Connecticut Computer Science coverage using LinkedIn, Handshake, employer sites, and web search as independent discovery surfaces.

Those platforms are used to measure misses, not scraped into the production feed. Recurring misses should be traced to durable employer/ATS sources. A dedicated **External coverage audit** GitHub Action can run a dated sample and publish the report in the Actions summary, so the audit does not require a local terminal. See `audit/README.md` for the sample format and workflow.

## Automatic refreshes

`.github/workflows/update-feed.yml` runs hourly and can also be triggered manually from the Actions tab. If the normalized feed changes, the workflow commits the new `data/listings.json` back to the repository.

## USAJOBS setup

Yartchives supports the official USAJOBS API for federal student/intern opportunities. The workflow reads credentials from repository secrets:

- `USAJOBS_API_KEY`
- `USAJOBS_EMAIL`

The build script queries the `student` hiring path and keeps explicit internship / Pathways / student-trainee opportunities.
