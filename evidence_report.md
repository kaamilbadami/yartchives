## Concrete evidence
Investigation on current `main` showed that the requested improvement has no evidence-backed, high-leverage implementation left.
The reported gap of 2 Ashby employers was an artifact of stale data in a previous branch/session.

The codebase correctly classifies and resolves Ashby domains, as verified on current `main` using `scripts/coverage_gap_candidates.py`.
There are no benchmark employers with Ashby domains that are currently unresolved in `employer_universe.json`.

Following the precedent set by PR #978 (chore: Confirm iCIMS provider-resolution coverage gap is closed), this task is concluded with no code changes necessary, as the gap is confirmed closed.
