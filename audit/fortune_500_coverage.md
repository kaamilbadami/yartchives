# Fortune 500 Internship Coverage Report

**Benchmark Population:** 500 employers (from Fortune 500 2026 seed)

- **Resolved to an authoritative ATS/career source:** 120
- **Currently produce eligible US undergraduate CS internship/co-op/student listings in the feed:** 90

## Coverage by Major ATS/Source Family (Resolved)

- **workday**: 81
- **oracle**: 16
- **eightfold**: 9
- **icims**: 8
- **avature**: 3
- **successfactors**: 2
- **phenom**: 1

## Coverage by Potential ATS/Source Family (Unresolved)

- **unknown**: 349
- **custom_unknown**: 10
- **successfactors**: 10
- **smartrecruiters**: 6
- **greenhouse**: 4
- **workday**: 1

## Miss Classification

- **No Domain Hint (Discovery Gap):** 349
- **Unsupported ATS / Unknown Provider:** 10
- **Unresolved Host (Needs Tenant Identity):** 21
- **No Current Eligible Openings (Among Resolved):** 79

## Largest Actionable Generic Gap

The dominant defect is **No Domain Hint (Discovery Gap)**.
Out of the 500 employers, a large majority lack any domain hints or discovery surfaces in `employer_universe.json`.
This gap represents missing seed verification coverage rather than a bug in normalization or provider resolution logic.
