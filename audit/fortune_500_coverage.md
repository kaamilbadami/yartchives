# Fortune 500 Internship Coverage Report

**Benchmark Population:** 500 employers (from Fortune 500 2026 seed)

- **Resolved to an authoritative ATS/career source:** 149
- **Currently produce eligible US undergraduate CS internship/co-op/student listings in the feed:** 88
- **Currently have eligible listings with reachable authoritative links:** 76

## Coverage by Major ATS/Source Family (Resolved)

- **workday**: 86
- **oracle**: 16
- **successfactors**: 12
- **eightfold**: 10
- **icims**: 9
- **smartrecruiters**: 6
- **avature**: 3
- **brassring**: 3
- **greenhouse**: 3
- **phenom**: 1

## Coverage by Potential ATS/Source Family (Unresolved)

- **custom_unknown**: 327
- **unknown**: 24
- **greenhouse**: 1
- **workday**: 1

## Miss Classification

- **No Domain Hint (Discovery Gap):** 24
- **Unsupported ATS / Unknown Provider:** 327
- **Unresolved Host (Needs Tenant Identity):** 0
- **Retrieval Failure (Broken Links on Eligible Listings):** 12
- **No Current Eligible Openings (Among Resolved):** 105
- **Filtering/Normalization Loss:** 71

## Largest Actionable Generic Gap

The dominant defect is **Unsupported ATS / Unknown Provider**.
Out of the 500 employers, a large majority have domain hints but either use unsupported ATS platforms (like Taleo/BrassRing/custom systems) or the provider resolution logic fails to identify the provider.
This gap represents a need to build provider support for these systems, or investigate why `custom_unknown` is so prevalent among these employers.
