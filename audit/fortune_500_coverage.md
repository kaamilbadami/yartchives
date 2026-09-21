# Fortune 500 Internship Coverage Report

**Benchmark Population:** 500 employers (from Fortune 500 2026 seed)

- **Resolved to an authoritative ATS/career source:** 126
- **Currently produce eligible US undergraduate CS internship/co-op/student listings in the feed:** 85
- **Currently have eligible listings with reachable authoritative links:** 72

## Coverage by Major ATS/Source Family (Resolved)

- **workday**: 82
- **oracle**: 16
- **eightfold**: 9
- **icims**: 8
- **avature**: 3
- **successfactors**: 3
- **greenhouse**: 2
- **smartrecruiters**: 2
- **phenom**: 1

## Coverage by Potential ATS/Source Family (Unresolved)

- **custom_unknown**: 245
- **unknown**: 126
- **successfactors**: 9
- **smartrecruiters**: 4
- **greenhouse**: 2
- **workday**: 2

## Miss Classification

- **No Domain Hint (Discovery Gap):** 126
- **Unsupported ATS / Unknown Provider:** 245
- **Unresolved Host (Needs Tenant Identity):** 3
- **Retrieval Failure (Broken Links on Eligible Listings):** 13
- **No Current Eligible Openings (Among Resolved):** 85
- **Filtering/Normalization Loss:** 70

## Largest Actionable Generic Gap

The dominant defect is **Unsupported ATS / Unknown Provider**.
Out of the 500 employers, a large majority have domain hints but either use unsupported ATS platforms (like Taleo/BrassRing/custom systems) or the provider resolution logic fails to identify the provider.
This gap represents a need to build provider support for these systems, or investigate why `custom_unknown` is so prevalent among these employers.

## Delta from Previous Report

- **Resolved to an authoritative ATS/career source:** +6 (120 -> 126)
- **Currently produce eligible US undergraduate CS internship/co-op/student listings in the feed:** -5 (90 -> 85)

### Coverage by Major ATS/Source Family (Resolved)
- **workday**: +1 (81 -> 82)
- **successfactors**: +1 (2 -> 3)
- **greenhouse**: +2 (0 -> 2)
- **smartrecruiters**: +2 (0 -> 2)

### Miss Classification
- **No Domain Hint (Discovery Gap):** -223 (349 -> 126)
- **Unsupported ATS / Unknown Provider:** +235 (10 -> 245)
- **Unresolved Host (Needs Tenant Identity):** -18 (21 -> 3)
- **No Current Eligible Openings (Among Resolved):** +6 (79 -> 85)
