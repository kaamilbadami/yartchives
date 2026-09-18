# Yartchives Jules review rules

Review the pull request as an independent reviewer. Do not assume that green CI means the change is correct.

## Blocking findings

Treat these as blocking when supported by the diff or repository context:

- The PR changes files unrelated to its stated bounded task without a clear root-cause reason.
- A production behavior fix removes, weakens, bypasses, or rewrites a regression test merely to make CI pass.
- Feed, link, eligibility, identity, or evidence contracts are weakened to accommodate bad data.
- Workday employer posting pages are mislabeled as verified direct application links, or a verified `/apply` destination is lost while retaining `link_kind: direct`.
- Frozen benchmark membership or expected benchmark semantics are changed without the task explicitly requiring a benchmark change.
- LinkedIn or Handshake is introduced as a production scraping source.
- Secrets, credentials, or sensitive tokens are added to tracked files.
- Generated data is edited solely to satisfy a test instead of fixing the source logic or brittle assertion.
- The PR introduces broad employer-specific special cases where a provider-family or generic source fix is appropriate.
- The PR changes workflow permissions, automation triggers, or auto-merge behavior in a way that materially increases risk without an explicit task requirement.

## Scope review

Compare the PR title/body with the actual changed files. Call out scope creep explicitly.

A focused test-only fix may update a test and any directly necessary test contract, but unrelated workflow, application, data, ranking, or source changes require explanation.

## Correctness review

Check for:
- root-cause alignment;
- preservation of existing contracts;
- regression coverage where behavior changes;
- idempotency for automation/data lifecycle code;
- stable behavior as generated datasets grow;
- accidental coupling to mutable global counts or timestamps;
- unsafe fallbacks that silently turn authoritative evidence into metadata.

## Severity

Use BLOCKING only for high-confidence correctness, security, contract, or material scope problems.
Use WARN for plausible risks that deserve human attention but are not clearly merge blockers.
Avoid stylistic nitpicks unless they hide a correctness issue.
