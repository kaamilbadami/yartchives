# Yartchives

**A multi-source opportunity platform I built to make internship and early-career searches more organized and accessible across different fields.**

I got tired of bouncing between separate internship lists, job boards, and spreadsheets — especially once I started looking beyond one narrow type of role. Yartchives pulls public opportunity feeds into one searchable place, normalizes them, removes obvious duplicates, and lets each person filter the same feed around what they actually want.

## What it does

- Aggregates public internship and early-career feeds into one dataset.
- Normalizes company, role, location, date, source, and application links.
- Deduplicates overlapping listings before they ever reach the browser.
- Supports profiles for Computer Science, **Tech + Business**, Finance/Economics, Mechanical Engineering, Aerospace/Astronautical Engineering, Electrical Engineering, Policy/Government, and Premed/Health.
- Keeps saved, applied, and hidden listings in the user's browser — no account required.
- Refreshes the feed automatically with GitHub Actions instead of making every visitor scrape every source themselves.
- Keeps the last known data from a source if that source temporarily fails.

## Why the architecture changed

An earlier browser-only prototype fetched and parsed every source on page load. That worked, but it got slow as the number of sources grew. Yartchives now does that work ahead of time in GitHub Actions and serves the frontend one prebuilt `data/listings.json` file. The site stays static and cheap to host while the expensive parsing and deduplication happen off the user's device.

## Sources

Current source adapters include public feeds from Simplify, Zapply, Vansh/CSCareers, SpeedyApply, ApplyGuy, Dreamwork, the Jobright public-sector list, Campus to Career, and other public internship trackers. Each listing keeps source attribution.

The federal adapter uses the official USAJOBS Search API. It is intentionally disabled until `USAJOBS_API_KEY` and `USAJOBS_EMAIL` repository secrets are configured.

> Yartchives does not own or republish employer application content. Listings are discovery metadata and links back to the employer or original public source.

## Local development

```bash
python -m pip install -r requirements.txt
python scripts/build_feed.py
python -m http.server 8000
```

Then open `http://localhost:8000`.

## Automatic refreshes

`.github/workflows/update-feed.yml` runs hourly and can also be triggered manually from the Actions tab. If the normalized feed changes, the workflow commits the new `data/listings.json` back to the repository.

## USAJOBS setup

Yartchives supports the official USAJOBS API for federal student/intern opportunities. Request an API key from the USAJOBS developer portal, then add these repository secrets:

- `USAJOBS_API_KEY`
- `USAJOBS_EMAIL`

The build script queries the `student` hiring path and keeps explicit internship / Pathways / student-trainee opportunities.
