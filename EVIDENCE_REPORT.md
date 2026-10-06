# Evidence Report: Issue #964 - Close Applytojob provider-resolution coverage gap

## What was tested
I investigated the reported coverage gap `ats-applytojob:provider-resolution`, which claims 1 benchmark employer has an unresolved provider record but domain evidence fingerprinting as applytojob. I ran `scripts/coverage_gap_candidates.py` to reproduce the gap from current `main` and analyzed the current `employer_universe.json` state.

## Measured before/after impact
- **Before:** 0 unresolved benchmark employers with `applytojob` domain fingerprints on current `main`. The only reported gap is `source-registry:unknown-provider-resolution`.
- **After:** 0 unresolved benchmark employers with `applytojob` domain fingerprints (no-code conclusion).

## Why the proposed paths are insufficient
The gap cannot be reproduced on current `main`. Both benchmark employers with `applytojob` domain hints (`abm-industries` and `aerotech`) have successfully resolved provider records (`"status": "resolved"`). The underlying codebase in `scripts/careers_resolver.py` and `scripts/provider_fingerprint.py` already correctly classifies and resolves `applytojob` domains. The reported gap was likely an artifact of stale data in the data store prior to the most recent automated universe refresh.

## Smallest concrete follow-up experiment
No code changes are necessary for `applytojob`. Future instances of stale resolution data causing false-positive gaps can be mitigated by ensuring `employer_resolution_lifecycle.py` is run frequently enough to keep `employer_universe.json` synchronized with the latest resolver logic before creating autonomous gap tickets.
