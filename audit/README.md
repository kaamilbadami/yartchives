# Coverage audits

Yartchives uses external job platforms and web search as **audit surfaces**, not as production scrapers. The goal is to sample opportunities that a student could realistically discover elsewhere, compare them against the current Yartchives feed, and turn recurring misses into durable employer/ATS coverage.

## First target: Connecticut Computer Science

Start with a manually collected sample of current CT CS internships from sources such as LinkedIn, Handshake, employer career pages, and normal web search. Prefer the employer/ATS application URL when you can get it.

Create a JSON, JSONL/NDJSON, or CSV file with at least:

- `company`
- `title`
- `location`
- `url`
- `source` — where you discovered it, such as `LinkedIn` or `Handshake`

Optional per-listing fields are `source_key`, `source_url`, `expected_profile` / `expected_profiles`, `expected_state` / `expected_states`, `expected_opportunity_type` / `expected_opportunity_types`, and `expect_default_visible`.

Example JSON:

```json
[
  {
    "company": "Example Company",
    "title": "Software Engineering Intern",
    "location": "Hartford, CT",
    "url": "https://careers.example.com/jobs/12345",
    "source": "LinkedIn"
  }
]
```

Run the CT CS audit with:

```bash
python scripts/coverage_audit.py audit/ct-cs.json \
  --profile cs \
  --state CT \
  --output audit/results/ct-cs.json \
  --markdown-output audit/results/ct-cs.md
```

The command prints the human-readable report as well as optionally writing machine-readable JSON and Markdown files.

## Status meanings

- `already_in_yartchives` — the current feed matches the external opportunity by canonical URL or normalized company/title/location and it is visible under the expected filters.
- `filtered_or_misclassified` — the listing is present but has profile/state/type metadata that would hide it, or the source/direct employer is configured but the listing is absent after ingestion.
- `duplicate_resolution_issue` — the same ATS/listing identifier or a very strong same-employer title/location match exists, but normal deduplication did not resolve it cleanly.
- `employer_exists_but_listing_missing` — Yartchives already has other roles from that employer, but not the audited role.
- `source_not_covered` — the discovery/source host is not currently ingested. For LinkedIn/Handshake-style discovery surfaces, trace the role to the employer ATS rather than scraping the platform.
- `unknown` — there is not enough source/employer information to classify the miss confidently.

## How to use the results

Treat one-off misses as observations, not proof that a source is bad. Recurring misses from the same employer or ATS family are the signal to add a durable direct source or improve a provider adapter. Recurring `filtered_or_misclassified` results should become regression tests before changing classification/filter logic.

Coverage percentages are only meaningful for the external sample you audited. They are not claims that Yartchives contains every internship on the internet.
