# Coverage audits

Yartchives uses external job platforms and web search as **audit surfaces**, not as production scrapers. The goal is to sample opportunities that a student could realistically discover elsewhere, compare that sample against the current Yartchives feed, and turn recurring misses into durable employer/ATS coverage.

The audit is intentionally sample-based. It measures how well Yartchives covers a specific independently collected sample; it does **not** claim internet-wide completeness.

## First target: Connecticut Computer Science

Start with a fresh sample of current CT CS internships discovered independently through LinkedIn, Handshake, employer career pages, and ordinary web search. Prefer the employer/ATS application URL when you can get it, while keeping `source` as the place where the opportunity was discovered.

The template is `audit/samples/ct-cs.example.json`. A real dated sample should look like this:

```json
{
  "name": "Connecticut Computer Science coverage audit",
  "collected_at": "2026-09-16T12:00:00Z",
  "scope": {
    "profiles": ["cs"],
    "states": ["CT"]
  },
  "discoveries": [
    {
      "company": "Example Company",
      "title": "Software Engineering Intern",
      "location": "Hartford, CT",
      "url": "https://careers.example.com/jobs/12345",
      "source": "LinkedIn",
      "discovery_url": "https://www.linkedin.com/jobs/view/example"
    }
  ]
}
```

At minimum, each discovery should have `company` and `title`. For useful high-confidence matching, also provide `location`, the direct employer/ATS `url`, and `source`. The audit reports sample-quality warnings when those fields are missing and the GitHub workflow rejects samples missing company/title.

Optional per-listing fields are `source_key`, `source_url`, `discovery_url`, `expected_profile` / `expected_profiles`, `expected_state` / `expected_states`, `expected_opportunity_type` / `expected_opportunity_types`, and `expect_default_visible`.

JSONL/NDJSON and CSV are also supported. For those formats, pass profile/state scope on the command line because they do not carry top-level audit metadata.

## What the denominator means

The audit distinguishes **observations** from **unique external listings**. If the same internship is found on LinkedIn, Handshake, and the employer site, those are three observations but normally one unique listing.

Deduplication is conservative:

- exact canonical URLs collapse together;
- the same employer/ATS requisition identifier collapses together;
- discovery-platform listing IDs are not treated as employer requisition IDs;
- normalized company/title/location can merge cross-platform observations when there is no conflicting employer/ATS requisition ID;
- two different authoritative requisition IDs remain separate even when the title and location are identical.

Coverage percentages use the unique-listing denominator so repeated discoveries do not inflate or deflate the overall coverage rate. The report still preserves the discovery surfaces where each listing was observed.

## No-terminal workflow

A local terminal is not required.

1. In GitHub, copy `audit/samples/ct-cs.example.json` to a dated filename such as `audit/samples/ct-cs-2026-09-16.json`.
2. Replace the example row with independently discovered current opportunities and commit the file to `main`.
3. The **External coverage audit** GitHub Action starts automatically for added or modified non-example samples.
4. Open the workflow run and read its **Summary** for coverage metrics, sample-quality warnings, recurring gap clusters, and the prioritized action queue.
5. The run also uploads a 90-day artifact containing the full Markdown report and machine-readable JSON.

Deleting an old sample does not trigger an attempted audit of the deleted file. Pushes containing multiple sample changes are compared from the push's before-SHA to after-SHA, so every added or modified sample in that push is included.

You can rerun an existing sample without editing it from **Actions → External coverage audit → Run workflow** and enter the sample path. Because a rerun compares the historical sample with the feed checked out for that run, keep the sample's `collected_at` date visible when interpreting older samples.

## Command-line workflow

If a terminal is available, a self-describing JSON sample needs no profile/state flags:

```bash
python scripts/coverage_audit.py audit/samples/ct-cs-2026-09-16.json \
  --output audit/results/ct-cs-2026-09-16.json \
  --markdown-output audit/results/ct-cs-2026-09-16.md
```

For CSV/JSONL, or to override a JSON sample's declared scope, pass `--profile cs --state CT`. Use `--strict-sample` to return a non-zero exit code when a row is missing company or title; the GitHub Action enables this automatically.

Output parent directories are created automatically.

## Status meanings

- `already_in_yartchives` — the listing is represented in the feed and visible under the expected filters. Exact canonical-URL matches are highest confidence; normalized company/title/location matches are accepted only when they do not conflict with a different employer/ATS requisition ID.
- `filtered_or_misclassified` — the listing is present in the feed, but profile/state/type/education metadata would hide it under the expected filters.
- `duplicate_resolution_issue` — the listing appears to be represented in the feed, but URL normalization or deduplication did not resolve the two representations cleanly.
- `configured_source_miss` — Yartchives has a configured upstream/direct source that should cover the listing, but the listing is absent. This is separated from metadata/filter problems so missing listings are never counted as captured.
- `employer_exists_but_listing_missing` — Yartchives has other listings for the employer, but there is no evidence that the audited role is represented and no configured-source match explains the miss.
- `source_not_covered` — the employer/ATS/source is not currently covered. LinkedIn/Handshake-style discovery surfaces remain audit-only; trace repeated misses to the employer career/ATS source rather than scraping the discovery platform.
- `unknown` — there is not enough source/employer information to classify the miss confidently.

## Metrics

The machine-readable report currently uses schema version 2 and includes:

- `external_observations` — raw rows in the audit sample;
- `external_unique_listings` — deduplicated unique opportunities used as the denominator;
- `duplicate_observations_collapsed` — observations removed from the denominator as repeats;
- `confirmed_in_feed` — `already_in_yartchives` listings;
- `represented_in_feed` — confirmed listings plus present-but-fixable metadata/dedupe issues;
- `missing_from_feed` — configured-source misses, employer-level misses, uncovered sources, and unknowns;
- `visible_rate` — confirmed-visible listings / unique listings;
- `representation_rate` — represented listings / unique listings;
- per-status counts, per-discovery-source counts, sample-quality issues, and missing-listing gap clusters.

`capture_rate` and `captured_or_probably_captured` remain in the JSON as compatibility aliases for the representation metrics.

## How to use the results

Prioritize the audit queue in this order:

1. **Configured-source misses and filter/classification errors.** These are failures in coverage you already intended to have and usually deserve a regression test or adapter/filter fix.
2. **Repeated uncovered-source or employer-level misses.** A repeated employer or ATS family is evidence that durable direct coverage may be worth adding.
3. **Deduplication issues.** Verify requisition identity before changing normalization; similar titles alone are not enough when authoritative job IDs disagree.
4. **Unknowns.** Improve the audit evidence first by adding the employer URL, source, company, title, and location.

Treat one-off misses as observations, not proof that a source is bad. The report groups repeated missing listings by employer/host so recurring gaps are visible without manually scanning every row.

The report records both the external sample's collection time and the Yartchives feed snapshot used for comparison. Coverage percentages are meaningful only for that external sample and time window; they are not claims that Yartchives contains every internship on the internet.
