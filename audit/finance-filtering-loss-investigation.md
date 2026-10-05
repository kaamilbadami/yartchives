# Investigation: Finance Benchmark Filtering/Normalization Loss (#905)

## Overview
The Bel Air Finance benchmark on current main reports 1 employer contributing a **Filtering/Normalization Loss** signal. This investigation traces the cause of that signal to determine if there is a generic classification or normalization defect.

## Evidence & Reproduction

1. **Measurement:** Ran `scripts/measure_finance_benchmark_coverage.py`.
   - Found 1 filtering loss among the 6 benchmark employers.
   - Identified the employer as **Constellation Energy** (`constellation-energy`).

2. **Employer State:**
   - Checked `employer_universe.json` and the coverage output.
   - Constellation Energy is currently **unresolved** (`"status": "unresolved"` / `"family": "custom_unknown"`).
   - Because there is no authoritative ATS source resolution, no listings are being ingested from Constellation Energy's official career site.

3. **Listings Analysis:**
   - Inspected `data/listings.json` for jobs associated with `constellation-energy`.
   - Found exactly 4 listings, all originating from a generic discovery surface (`simplify`):
     - `PMO/Data Analyst Intern` (classified as `tech-business`)
     - `IT Data Engineering Intern` (classified as `cs`)
     - `Information Technology Software Development Intern` (classified as `cs`)
     - `Business Performance & Analytics Intern` (classified as `tech-business`)
   - The benchmark expects at least one role with the `finance-econ` profile. Since these IT/Data roles appropriately received `cs` or `tech-business` profiles rather than `finance-econ`, they trigger a validation failure in the benchmark script.

## Conclusion

The filtering loss signal is an artifact of the benchmark evaluating non-finance discovery roles (injected by `simplify`) for an unresolved employer. Because no authoritative source feed is being ingested, no actual finance listings were captured to be misclassified.

**Result:** No generic classification/normalization defect exists. The signal is entirely downstream of missing authoritative source data. Following the resolution guidelines for issue #905, this task is concluded with no product changes, as the issue requires resolving the underlying ATS source integration, not a pipeline patch.

## Next Steps
- Implement an authoritative source integration for Constellation Energy to properly ingest its catalog.
