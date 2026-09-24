# Yartchives Agent Instructions

These instructions apply to automated coding agents working in this repository.

## Source of truth

- Treat the current GitHub repository and the current `main` branch as the source of truth.
- Inspect the relevant code, tests, workflows, and current data contracts before making changes.
- Do not rely on stale chat context, prior assumptions, or generated artifacts when the repository says otherwise.

## Scope

- Work on one bounded task per issue or assignment.
- Do not opportunistically expand scope into unrelated cleanup.
- If the root cause requires a broader change than the issue describes, explain that in the PR instead of silently widening the patch.

## Engineering priorities

- Prefer root-cause fixes over symptom patches.
- Add or update regression tests for behavioral fixes when practical.
- Prefer scalable source architecture over one-off employer exceptions.
- Broad aggregators are the discovery backbone; direct employer and ATS sources are targeted authoritative gap-fillers.
- Prefer generic ATS/provider-family improvements over adding employers one by one.
- Do not use LinkedIn or Handshake as production scraping sources. They may be used only as discovery or audit surfaces.

## Feed and evidence contracts

- Do not weaken validation, link, eligibility, identity, or evidence contracts merely to make CI pass.
- Preserve the distinction between employer posting pages and verified direct application destinations.
- For Workday, a `direct` link must continue to satisfy the repository's verified direct-link contract; do not relabel ordinary job pages as direct application URLs.
- Preserve stable job identity behavior across feed refreshes.
- Do not change generated data solely to satisfy a brittle test. Fix brittle tests so they assert stable invariants instead.

## Benchmark discipline

- Treat the checked-in Northeast / Mid-Atlantic benchmark as frozen unless the task explicitly calls for changing benchmark membership.
- Improve measured coverage through source, parser, provider, identity, or visibility fixes rather than editing benchmark expectations.
- When diagnosing coverage gaps, distinguish uncovered sources, known-employer missing roles, hidden/presentation issues, provider identity mismatches, and probable duplicates.

## Frontend interaction responsiveness

- For any user action that can perform noticeable synchronous or asynchronous work, update the pending UI before starting that work.
- A DOM mutation is not evidence that the user saw the state. Use the shared `YartchivesUtils.runWithPendingUi(...)` / `waitForBrowserPaint()` primitive so the browser gets a paint boundary before expensive work begins.
- Pending-state regressions must test ordering: pending UI -> paint boundary -> expensive work -> restoration in `finally`. Do not test only that loading text exists somewhere in source.
- Avoid large synchronous work directly inside click handlers. If work remains materially blocking after a paint boundary, chunk it or move it off the main thread rather than hiding the stall with more loading copy.

## Product invariants and semantic contracts

- Treat product invariants as behavior, not implementation names. A signal forbidden from ranking must not affect rank indirectly through a renamed or newly extracted component.
- Ranking code must use the canonical scoring contract and explicit ranking-component whitelist. Do not sum arbitrary component objects.
- Do not introduce a new ranking signal, ranking weight, eligibility rule, persistence semantic, or other product-semantic change as part of a refactor unless the assigned issue explicitly requests that behavior change.
- Any intentional ranking-contract change must update the canonical contract, executable semantic regression tests, and `PRODUCT_INVARIANTS.md` in the same PR.
- Prefer paired/golden behavioral tests that vary exactly one input and assert the user-visible invariant (score, ordering, eligibility, persistence, destination, or deployed behavior), rather than tests that only check a field name or implementation detail.

## Testing

- Run the smallest relevant test set while iterating.
- Before opening a PR for code or workflow changes, run the smallest relevant regression tests locally when practical; the branch workflow will run the canonical targeted phase(s).
- Every relevant non-`main` branch push triggers the existing `Branch preflight` workflow. It selects Python, frontend, and repository-health checks from the changed paths instead of duplicating full PR CI. Do not open a PR until the exact branch head SHA has a successful `Branch preflight / tests` check. If preflight fails, repair the same branch and rerun it before publishing the PR.
- If full CI fails for a pre-existing unrelated reason, document the exact failure and do not disguise it as success.
- Never remove or weaken a failing test without showing why the previous assertion was unstable or incorrect.

## Shipping verification

- A merged frontend change is not considered shipped merely because CI and the merge succeeded.
- The Pages workflow must stamp the exact commit SHA into the built site and verify the live site serves that SHA after deployment.
- Live JS/CSS must be verified against the built artifact so a successful Pages API response cannot hide stale or mismatched frontend assets.
- When reporting user-visible work, distinguish **merged** from **live/verified**. Only call it shipped after the deployment verification step succeeds.

## Git and pull requests

- Work from current `main` on a dedicated branch.
- Keep commits and PRs focused on the assigned task.
- Do not push directly to `main`.
- Open a PR with:
  - the root cause,
  - the change made,
  - tests run,
  - any known risks or follow-up work.
- Do not merge your own PR unless the task explicitly authorizes automated merging.

## Safety and operational behavior

- Avoid exposing secrets or adding credentials to the repository.
- Prefer deterministic, idempotent automation.
- Deduplicate recurring automated issues rather than creating issue spam.
- Do not make expensive network-heavy workflows run more often unless the task specifically requires it.
- Do not wait on unrelated deployments or long-running external processes when the assigned task is complete.

## Product direction

Yartchives should help a student answer: **What should I apply to next?**

Changes should improve trust, coverage, evidence quality, ranking usefulness, reliability, or speed without sacrificing correctness for cosmetic gains.
