# Coverage audits

Yartchives uses external job platforms and web search as **audit surfaces**, not as production scrapers. The goal is to sample opportunities that a student could realistically discover elsewhere, compare them against the current Yartchives feed, and turn recurring misses into durable employer/ATS coverage.

## Source contribution audit

To measure the current production sources themselves, run:

```bash
python scripts/source_contribution_audit.py \
  --json-output audit/source-contribution.json \
  --markdown-output audit/source-contribution.md
```

This audit reads the production feed's preserved `source_keys`, pre-dedup source
counts, and link-authority labels. It reports removal-based unique contribution,
pairwise overlap, and direct-link quality without changing the feed. Its capture
percentage uses rows accepted by each production adapter as the denominator; it
must not be interpreted as coverage of a platform's private database or of the
wider internship market.

## Single-queue coverage contract

`coverage_contract.json` defines the claim Yartchives is trying to earn: one
discovery queue for current, publicly discoverable US undergraduate CS
internships and co-ops. The claim is gated on independent benchmark size and
geographic breadth, capture and visible recall, authoritative-link rate, feed
and sample freshness, and measured discovery latency.

Run an external audit, then evaluate its machine-readable report:

```bash
python scripts/coverage_audit_runner.py audit/samples/ct-cs-2026-09-16.json \
  --output audit/results/ct-cs.json
python scripts/coverage_contract.py audit/results/ct-cs.json
```

Use `--require-ready` only when the contract should act as a release gate. A
benchmark row may include `first_discovered_at`; latency remains unmeasurable
and the contract remains failed until those timestamps are present.

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

At minimum, each discovery should have `company`, `title`, `location`, `url`, and `source`. Optional per-listing fields are `source_key`, `source_url`, `discovery_url`, `expected_profile` / `expected_profiles`, `expected_state` / `expected_states`, `expected_opportunity_type` / `expected_opportunity_types`, and `expect_default_visible`.

JSONL/NDJSON and CSV are also supported. For those formats, pass profile/state scope on the command line because they do not carry top-level audit metadata.

## No-terminal workflow

A local terminal is not required.

1. In GitHub, copy `audit/samples/ct-cs.example.json` to a dated filename such as `audit/samples/ct-cs-2026-09-16.json`.
2. Replace the example row with the independently discovered current opportunities and commit the file to `main`.
3. The **External coverage audit** GitHub Action starts automatically for the new sample.
4. Open the workflow run and read its **Summary** for the human-readable coverage report and action queue.
5. The run also uploads a 90-day artifact containing the full Markdown report and machine-readable JSON.

You can rerun an existing sample without editing it from **Actions → External coverage audit → Run workflow** and enter the sample path. Because a rerun compares the sample with the feed checked out for that run, keep the sample's `collected_at` date visible when interpreting older samples.

## Command-line workflow

If a terminal is available, a self-describing JSON sample needs no profile/state flags:

```bash
python scripts/coverage_audit.py audit/samples/ct-cs-2026-09-16.json \
  --output audit/results/ct-cs-2026-09-16.json \
  --markdown-output audit/results/ct-cs-2026-09-16.md
```

For CSV/JSONL, or to override a JSON sample's declared scope, pass `--profile cs --state CT`.

## Status meanings

- `already_in_yartchives` — the current feed matches the external opportunity by canonical URL or normalized company/title/location and it is visible under the expected filters.
- `filtered_or_misclassified` — the listing is actually present in the feed but profile/state/type metadata would hide it under the expected filters.
- `duplicate_resolution_issue` — the same ATS/listing identifier or a very strong same-employer title/location match exists, but normal URL/signature matching did not resolve it cleanly.
- `employer_exists_but_listing_missing` — Yartchives already has other roles from that employer, but not the audited role.
- `configured_source_miss` — Yartchives has a configured upstream/direct source that should plausibly cover the role, but the listing is absent after ingestion. This points to freshness, adapter, ingestion, or filtering investigation rather than automatically blaming profile classification.
- `source_not_covered` — the discovery/source host is not currently ingested. For LinkedIn/Handshake-style discovery surfaces, trace the role to the employer ATS rather than scraping the platform.
- `unknown` — there is not enough source/employer information to classify the miss confidently.

Each result also contains a stable `reason_code` so recurring root causes can be counted separately from the broader status.

## Matching notes

Location comparison normalizes superficial U.S. formatting differences such as `Hartford, CT`, `Hartford, Connecticut`, and `Hartford, CT, United States`, and ignores ZIP-code-only differences. This prevents provider formatting from being counted as a false coverage miss without broadening the audit into geographic guessing.

## How to use the results

Treat one-off misses as observations, not proof that a source is bad. Recurring misses from the same employer or ATS family are the signal to add a durable direct source or improve a provider adapter. Recurring `filtered_or_misclassified` results should become regression tests before changing classification/filter logic. Recurring `configured_source_miss` results should be investigated in the ingestion/source pipeline first.

The report records both the external sample's collection time and the Yartchives feed snapshot used for comparison. Coverage percentages are meaningful only for that external sample; they are not claims that Yartchives contains every internship on the internet.
