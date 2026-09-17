# Yartchives source contribution audit

Feed snapshot: `2026-09-17T14:47:19.071885Z`

## Executive summary

- Final canonical jobs: **5248**
- Direct employer/ATS source provenance: **52 (1.0%)**
- Aggregator/list-only provenance: **5196 (99.0%)**
- Direct employer/ATS application links: **5033 (95.9%)**
- Single-source canonical jobs: **4242 (80.8%)**
- Multi-source canonical jobs: **1006 (19.2%)**

The 100% capture figures below mean all rows accepted by the production adapter reached pre-dedup ingestion. They do not claim full coverage of a platform, repository rows the adapter cannot interpret, or the wider internship market.

## Source coverage

| Source | Class | Upstream eligible | Ingested | Final | Coverage | Unique | Unique % feed | Overlap | Direct/ATS links | Confidence |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ApplyGuy (`applyguy`) | broad aggregator | 674 | 674 | 667 | 100.0%* | 267 | 5.1% | 400 | 613 (91.9%) | high |
| Campus to Career (`campus-to-career`) | curated GitHub/list | 114 | 114 | 114 | 100.0%* | 67 | 1.3% | 47 | 114 (100.0%) | high |
| Allegion / Stanley Access Technologies (direct) (`ct-allegion-workday`) | direct employer / ATS | 1 | 1 | 1 | 100.0%* | 0 | 0.0% | 1 | 1 (100.0%) | high |
| Gartner (direct) (`ct-gartner-workday`) | direct employer / ATS | 1 | 1 | 1 | 100.0%* | 1 | 0.0% | 0 | 1 (100.0%) | high |
| The Hartford (direct) (`ct-hartford-workday`) | direct employer / ATS | 2 | 2 | 2 | 100.0%* | 0 | 0.0% | 2 | 2 (100.0%) | high |
| IAT Insurance Group (direct) (`ct-iat-workday`) | direct employer / ATS | 1 | 1 | 1 | 100.0%* | 1 | 0.0% | 0 | 1 (100.0%) | high |
| RTX / Pratt & Whitney (direct) (`ct-rtx-workday`) | direct employer / ATS | 1 | 1 | 1 | 100.0%* | 0 | 0.0% | 1 | 1 (100.0%) | high |
| Dreamwork Business (`dreamwork-business`) | broad aggregator | 587 | 587 | 585 | 100.0%* | 421 | 8.0% | 164 | 585 (100.0%) | high |
| Dreamwork Tech (`dreamwork-tech`) | broad aggregator | 1959 | 1959 | 1957 | 100.0%* | 1204 | 22.9% | 753 | 1956 (99.9%) | high |
| Public Sector (`public-sector`) | aggregator-derived mirror/subset | 100 | 100 | 100 | 100.0%* | 100 | 1.9% | 0 | 0 (0.0%) | high for repository subset; not measurable for Jobright |
| Simplify (`simplify`) | curated GitHub/list | 1861 | 1861 | 1737 | 100.0%* | 1244 | 23.7% | 493 | 1737 (100.0%) | high |
| Summer 2027 Internships (`sndsh`) | curated GitHub/list | 125 | 125 | 125 | 100.0%* | 65 | 1.2% | 60 | 125 (100.0%) | high |
| SpeedyApply (`speedyapply`) | curated GitHub/list | 606 | 606 | 576 | 100.0%* | 227 | 4.3% | 349 | 560 (97.2%) | high |
| USAJOBS (`usajobs`) | direct employer / ATS | 46 | 46 | 46 | 100.0%* | 46 | 0.9% | 0 | 46 (100.0%) | high for API query; broader federal inventory not measured |
| Vansh / CSCareers (`vansh-cscareers`) | curated GitHub/list | 265 | 265 | 255 | 100.0%* | 168 | 3.2% | 87 | 214 (83.9%) | high |
| Zapply (`zapply`) | broad aggregator | 600 | 600 | 588 | 100.0%* | 431 | 8.2% | 157 | 584 (99.3%) | high |

## Largest pairwise overlaps

- `dreamwork-tech` + `simplify`: **372**
- `applyguy` + `dreamwork-tech`: **274**
- `applyguy` + `speedyapply`: **261**
- `dreamwork-tech` + `speedyapply`: **242**
- `applyguy` + `simplify`: **185**
- `simplify` + `speedyapply`: **152**
- `dreamwork-business` + `dreamwork-tech`: **150**
- `dreamwork-tech` + `zapply`: **115**
- `simplify` + `zapply`: **64**
- `dreamwork-business` + `simplify`: **49**
- `dreamwork-tech` + `vansh-cscareers`: **44**
- `applyguy` + `zapply`: **43**
- `campus-to-career` + `sndsh`: **42**
- `simplify` + `vansh-cscareers`: **33**
- `dreamwork-business` + `zapply`: **21**
- `sndsh` + `vansh-cscareers`: **20**
- `dreamwork-tech` + `sndsh`: **15**
- `campus-to-career` + `vansh-cscareers`: **11**
- `speedyapply` + `zapply`: **11**
- `speedyapply` + `vansh-cscareers`: **10**

Configured inputs with zero final contribution: `ct-avangrid-workday`, `ct-travelers-workday`.

## Source scope and link quality

### ApplyGuy (`applyguy`)

Immediate upstream: https://raw.githubusercontent.com/ApplyGuy/2027-Internships/main/README.md

Scope: 2027 internships published in ApplyGuy/2027-Internships. Link buckets: direct_employer_ats=613, unresolved_non_authoritative=54.

### Campus to Career (`campus-to-career`)

Immediate upstream: https://raw.githubusercontent.com/fromcampustocareer/fromcampustocareer-opportunities/main/README.md

Scope: rows in fromcampustocareer/fromcampustocareer-opportunities. Link buckets: direct_employer_ats=114.

### Allegion / Stanley Access Technologies (direct) (`ct-allegion-workday`)

Immediate upstream: https://allegion.wd5.myworkdayjobs.com/wday/cxs/allegion/careers/jobs

Scope: configured employer's CT student opportunities matching the source-specific CS rules. Link buckets: direct_employer_ats=1.

### Gartner (direct) (`ct-gartner-workday`)

Immediate upstream: https://gartner.wd5.myworkdayjobs.com/wday/cxs/gartner/EXT/jobs

Scope: configured employer's CT student opportunities matching the source-specific CS rules. Link buckets: direct_employer_ats=1.

### The Hartford (direct) (`ct-hartford-workday`)

Immediate upstream: https://thehartford.wd5.myworkdayjobs.com/wday/cxs/thehartford/Careers_External/jobs

Scope: configured employer's CT student opportunities matching the source-specific CS rules. Link buckets: direct_employer_ats=2.

### IAT Insurance Group (direct) (`ct-iat-workday`)

Immediate upstream: https://iatinsurancegroup.wd1.myworkdayjobs.com/wday/cxs/iatinsurancegroup/iat/jobs

Scope: configured employer's CT student opportunities matching the source-specific CS rules. Link buckets: direct_employer_ats=1.

### RTX / Pratt & Whitney (direct) (`ct-rtx-workday`)

Immediate upstream: https://globalhr.wd5.myworkdayjobs.com/wday/cxs/globalhr/rec_rtx_ext_gateway/jobs

Scope: configured employer's CT student opportunities matching the source-specific CS rules. Link buckets: direct_employer_ats=1.

### Dreamwork Business (`dreamwork-business`)

Immediate upstream: https://raw.githubusercontent.com/dreamworkhq/Open-Tech-Internships-2027/main/data/business-listings.json

Scope: 2027 business internships in Dreamwork's public JSON feed. Link buckets: direct_employer_ats=585.

### Dreamwork Tech (`dreamwork-tech`)

Immediate upstream: https://raw.githubusercontent.com/dreamworkhq/Open-Tech-Internships-2027/main/data/listings.json

Scope: 2027 technology internships in Dreamwork's public JSON feed. Link buckets: direct_employer_ats=1956, unresolved_non_authoritative=1.

### Public Sector (`public-sector`)

Immediate upstream: https://raw.githubusercontent.com/jobright-ai/2026-Public-Sector-Internship/master/README.md

Scope: rows in jobright-ai/2026-Public-Sector-Internship; broader Jobright inventory is not measurable. Link buckets: aggregator_intermediary=100.

### Simplify (`simplify`)

Immediate upstream: https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/README.md

Scope: 2027 internships published in SimplifyJobs/Summer2027-Internships. Link buckets: direct_employer_ats=1737.

### Summer 2027 Internships (`sndsh`)

Immediate upstream: https://raw.githubusercontent.com/sndsh404/summer-2027-internships/main/README.md

Scope: 2027 internships published in sndsh404/summer-2027-internships. Link buckets: direct_employer_ats=125.

### SpeedyApply (`speedyapply`)

Immediate upstream: https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/README.md

Scope: 2027 SWE college jobs published in speedyapply/2027-SWE-College-Jobs. Link buckets: direct_employer_ats=560, unresolved_non_authoritative=16.

### USAJOBS (`usajobs`)

Immediate upstream: https://data.usajobs.gov/api/Search

Scope: USAJOBS student hiring-path results from the prior 60 days matching explicit student/intern terms. Link buckets: direct_employer_ats=46.

### Vansh / CSCareers (`vansh-cscareers`)

Immediate upstream: https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/README.md

Scope: 2027 internships published in vanshb03/Summer2027-Internships. Link buckets: direct_employer_ats=214, unresolved_non_authoritative=41.

### Zapply (`zapply`)

Immediate upstream: https://raw.githubusercontent.com/zapplyjobs/Internships-2027/main/README.md

Scope: 2027 internships published in Zapply's GitHub README. Link buckets: aggregator_intermediary=4, direct_employer_ats=584.

## Interpretation and gaps

- **Source capture gap:** no loss is visible between adapter-eligible rows and ingestion in this snapshot. This does not test rows the adapter failed to recognize, so repository/API raw-universe capture remains a verification gap unless separately inventoried.
- **Market coverage gap:** not measurable from these overlapping aggregators and lists. No market-wide denominator is available.
- **Verification gap:** records in `aggregator_intermediary` or `unresolved_non_authoritative` link buckets still lack a direct authoritative application destination.
- **Mirror warning:** `public-sector` is the public `jobright-ai/2026-Public-Sector-Internship` repository only. Its coverage must not be described as coverage of Jobright's full database.

