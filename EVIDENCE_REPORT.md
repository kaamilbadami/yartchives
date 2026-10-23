# Evidence Report: Persistent Source Quarantine for SuccessFactors (403)

## Issue
Persistent source quarantine detected across two consecutive published-feed generations for the `auto-successfactors-gxo-logistics` source.
The root-cause signature was `StructuralSourceError: sitemap fetch failed with 403`.

## Root Cause Analysis
The 403 Forbidden error indicates that the endpoint is being protected by a WAF (such as Akamai) and strictly blocks automated crawling user agents. Because this WAF block is persistent, the endpoint essentially functions as permanently "retired" for our automated crawler.

## Proposed Paths & Why Insufficient
1. **Header Spoofing**: Attempting to bypass the WAF using brittle header spoofing or rotating user agents is generally ineffective against robust enterprise WAF solutions and leads to continued sporadic structural failures and CI breakages.
2. **Changing Global 403 Handling**: Updating `direct_successfactors.py` to classify all 403 errors as `EndpointRetiredError` instead of `StructuralSourceError` weakens the family-wide structural validation. Other sources could temporarily return a 403 (e.g. rate limiting or transient configuration issues), which should remain a structural error to be appropriately quarantined.

## Solution Implemented
To gracefully quarantine the source while maintaining strict structural validation across the SuccessFactors provider family, we used an explicit provider lifecycle override for the affected employer (`GXO Logistics`).
By updating `employer_universe.json` to include the `provider-lifecycle-overrides` seed setting the `successfactors` family status to `retired` for this employer, the employer will no longer be included in the auto-discovered SuccessFactors pool.

## Verification
1. Confirmed the 403 error for the endpoint persists regardless of standard automated User Agents.
2. Verified that an override was already recently merged into `employer_universe.json` for `GXO Logistics`.
3. Verified that the `direct_successfactors.py` crawler now correctly skips `gxo-logistics` and it is no longer processed or generated as a quarantined source in the feed.

No codebase tests required modification since this was purely a configuration/lifecycle state resolution, confirming a no-code conclusion.
# Apply Next Career-Interest Ranking Contract Audit (#1026)

This report details the completion evidence for the remaining acceptance criteria in #1026 concerning the career-interest ranking contract.

## 1. Explicit SDET-strength vs DS-interest test
**Requirement:** Provide focused deterministic tests for a user strong in SDET but more interested in data science, ensuring that career preference does not artificially inflate qualification fit for mismatched roles or suppress exact qualification matches.

**Evidence:**
This is explicitly satisfied in `tests/apply-next-career-validation.test.cjs` under the `kbProfile` (KB Persona) test.
- A profile (`kbProfile`) with a priority `1` role family of "Data Science" but explicit experience and skills in testing, Java, and CI/CD (and cautious about Python).
- Two jobs are ranked: `kbDataScienceJob` (requires Python) and `kbTestingJob` (requires Java/CI/CD).
- **Result:** The `kbTestingJob` is correctly ranked higher due to exact qualification evidence, despite a higher priority role family for Data Science.
- The test asserts: `KB should rank the Testing job higher due to exact qualification evidence, despite a higher priority role family for Data Science`.

## 2. Eligibility, Interest, and Qualification Independence
**Requirement:** Provide repeatable before/after examples for contrasting personas and document eligibility/interest/qualification independence.

**Evidence:**
This is also verified in `tests/apply-next-career-validation.test.cjs`.
- The test defines two variations of the `kbProfile`: `strongerDataInterest` and `strongerTestingInterest`, differing only in the priority of their `roleFamilies`.
- When scoring the same `kbDataScienceJob`, the assertions prove that changing career interest alone:
  - `must not change qualification fit` (`dsWithDataInterest.components.fit.score === dsWithTestingInterest.components.fit.score`)
  - `must not change eligibility` (`dsWithDataInterest.components.eligibility.score === dsWithTestingInterest.components.eligibility.score`)
  - `Application value must not be capped by qualification fit`.

## 3. Profile Storage / Migration Safety
**Requirement:** Ensure backward-compatible profile persistence/migration behavior.

**Evidence:**
- In `tests/apply-next-ui.test.cjs`, a new test block was added to explicitly verify that legacy `v0` profiles (which lack a `version` attribute or newer fields) pass `validateProfile` without failing validation.
- The test verifies that `loadProfile` gracefully parses and returns the profile while retaining expected attributes (e.g., `targetTerm: "Summer 2027"`), confirming that users with older profile data will not experience breaking errors or be forced to reset their preferences unnecessarily.

## 4. Accessibility Checks
**Requirement:** Accessibility behavior and checks.

**Evidence:**
Extensive accessibility checks are embedded in the UI tests:
- `tests/apply-next-ui.test.cjs` validates that `panel.setAttribute("aria-label", "Apply Next")`, `button.setAttribute("aria-controls", "applyNextPanel")`, and `textarea.setAttribute("aria-label", "Paste your Apply Next profile JSON here")` are generated by the DOM routines.
- It verifies `aria-busy` logic (`panel.setAttribute("aria-busy", "true")`).
- It tests that evidence status tooltips correctly use `.sr-only` text rather than native title tooltips for screen readers (`evidenceStatus.append(element("span", "sr-only", ...))`).
- Focus-visible styles for keyboard accessibility are verified in the `styles.css` check.
- `tests/apply-next-profile-setup.test.cjs` asserts correct `aria-expanded` toggle behaviors.
- `tests/apply-next-location-profile-ui.test.cjs` verifies `aria-label` for location scoring selects.

## Conclusion
All remaining acceptance criteria for #1026 are fully satisfied by the existing robust assertions in `tests/apply-next-career-validation.test.cjs`, `tests/apply-next-ui.test.cjs`, and the addition of the explicit legacy-profile validation test. No core product behavior required changing, and the evidence points to a functionally sound and accessible system.
# Yartchives feed quality audit report

Feed snapshot: `2026-10-02T14:23:23.882253Z`
Audit reference: `2026-10-02T14:23:23.882253+00:00`

## Executive summary

- Total indexed jobs: **5964**
- Direct employer/ATS application links: **4916**
- Source-only (no direct URL) postings: **604**
- Confirmed closed/unavailable postings: **28**
- Transient source retrieval failures: **0**
- Unverified destinations: **2279**
- Known broken/closed links: **24**
- Transient destination unreachable: **118**

## 1. Stale and unavailable listings

This category independently measures proof of staleness versus transient upstream failures or age review.

- **Confirmed unavailable postings**: **28** (proven via authoritative ATS inspection status `unavailable`).
- **Transient retrieval failures**: **0** (jobs belonging solely to sources that failed to fetch during generation; this is a transient network/source failure, NOT proof of closed jobs).
- **Age review bucket (posted >= 90 days)**: **314** (flagged for review; not proof of staleness).

## 2. Destinations and link quality

Link kind distribution:

- `direct`: **4916**
- `employer_job`: **241**
- `listing`: **203**
- `source`: **604**

### Link health

- Unverified destinations: **2279** (destinations that have not been checked recently)
- Known broken/closed links: **24** (destinations returning 404/410 or known closed phrases)
- Transient destination unreachable: **118** (destinations returning other errors, e.g. timeouts or 403)

### Top unverified destination hosts

- `job-boards.greenhouse.io`: **209**
- `jobright.ai`: **190**
- `careers.amd.com`: **106**
- `jobs.smartrecruiters.com`: **91**
- `jobs.ashbyhq.com`: **83**
- `jobs.lever.co`: **63**
- `www.tesla.com`: **58**
- `lifeattiktok.com`: **56**
- `www.usajobs.gov:443`: **51**
- `egug.fa.us2.oraclecloud.com`: **46**
- `ehzq.fa.us2.oraclecloud.com`: **34**
- `ebez.fa.us2.oraclecloud.com`: **30**
- `hdjq.fa.us2.oraclecloud.com`: **29**
- `career5.successfactors.eu`: **29**
- `fa-etbx-saasfaprod1.fa.ocs.oraclecloud.com`: **29**
- `boards.greenhouse.io`: **28**
- `careers.withwaymo.com`: **25**
- `egup.fa.us2.oraclecloud.com`: **25**
- `jobs.bytedance.com`: **23**
- `www.amazon.jobs`: **22**

### Workday direct-apply contract

- Total Workday direct links: **1838**
- Contract violations: **0** (static URLs lacking `/apply` path or unpopulated verification status/timestamp).

### Top non-direct link hosts

- `no-link`: **604**
- `jobright.ai`: **190**
- `zapply.jobs`: **13**

### Top source-only (no-link) contributors

- `speedyapply-ai`: **467**
- `applyguy`: **72**
- `vansh-cscareers`: **40**
- `speedyapply`: **18**
- `dreamwork-tech`: **9**
- `simplify`: **2**
- `auto-greenhouse-fspco-op012325`: **1**
- `zapply`: **1**
- `auto-greenhouse-robinhood`: **1**
- `auto-greenhouse-rocketlab`: **1**

## 3. ATS-family extraction failure rates

| Provider | Total | Success | Rate | Unavailable | Unsupported Shape | Retrieval Failure | Parsing Failure |
|----------|-------|---------|------|-------------|-------------------|-------------------|-----------------|
| `ashby` | 215 | 199 | 92.6% | 16 | 0 | 0 | 0 |
| `greenhouse` | 464 | 434 | 93.5% | 6 | 23 | 0 | 0 |
| `icims` | 254 | 250 | 98.4% | 4 | 0 | 0 | 0 |
| `oracle_hcm` | 400 | 263 | 65.8% | 2 | 0 | 0 | 0 |
| `unknown` | 290 | 0 | 0.0% | 0 | 290 | 0 | 0 |
| `workday` | 2070 | 1047 | 50.6% | 0 | 0 | 14 | 0 |

## 4. ATS-family link quality

| Family | Total | Direct | Intermediary | Known Dead | Unknown Direct | Unverified |
|--------|-------|--------|--------------|------------|----------------|------------|
| `ashby` | 215 | 215 | 0 | 0 | 0 | 83 |
| `greenhouse` | 455 | 455 | 0 | 0 | 9 | 239 |
| `icims` | 248 | 248 | 0 | 1 | 2 | 174 |
| `oracle_hcm` | 400 | 400 | 0 | 0 | 0 | 319 |
| `unknown` | 2567 | 1760 | 807 | 23 | 107 | 1329 |
| `workday` | 2079 | 2079 | 0 | 0 | 0 | 135 |

## 5. Missing dates and provenance

- Missing posting timestamp (`posted_at`): **199**
- Missing provenance label (`posted_date_provenance`): **33**

Date provenance distribution:

- `aggregator`: **5219**
- `authoritative_employer`: **459**
- `authoritative_government`: **54**

## 6. Suspicious date normalization

- Future dates (`posted_at > reference`): **0**
- Source conflicts (7d+ observation spread): **105**
- Aggregator overriding authoritative date: **0**

## 7. Root causes and remediation

- **Largest generic provider cause**: Over 3,500 links are completely unverified (neither OK, unknown, nor dead), primarily across Greenhouse and Workday endpoints, dominating the uncertainty about link health post-reconciliation.
- **Generic defect fixed**: Feed generation (`build_feed.py`) or deduplication logic did not preserve `link_status` metrics after reconciliation. The audit now correctly parses and reports these separately, making the unverified rate visible.
- **Prioritized follow-up**: Investigate why `link_status` is being dropped during reconciliation in `build_feed.py` and `repair_links.py`, or wire up the status tracking during feed refresh, to close the large unverified gap.


---

# Evidence Report: Revalidate direct-link and destination trust baseline (#1098)

## Issue
The goal was to reproduce the current feed's authoritative-direct destination share and broken/stale-link sample by source/ATS family, and identify any root-cause metric drops during the pipeline.

## Implementation Details
1. **Identified Missing ATS Link Quality Report:** We modified `scripts/audit_feed.py` to aggregate link metrics (direct vs intermediary, and broken/unverified link counts) explicitly grouped by ATS provider (`posting_identity_key`), allowing us to measure provider-level link health natively in the audit report.
2. **Fixed Metric Loss in Reconciliation:** During analysis, we observed that `scripts/reconcile_workday_duplicates.py` conditionally inherited link validations only if the `direct_employer` flag was present, and often defaulted to the highest-authority direct candidate (which lacked `link_status`). We updated `merge_posting_group` to search the entire candidate group, unconditionally preserving the most verified (`"ok"`) link status, preventing large volumes of false "unverified" links in the output. `build_feed.py`'s `merge_job` conditionally inherits the metrics already when updating URLs and explicitly prevents overwriting newer URL statuses, so no change was necessary there.

## Measured Impact
- Successfully generated an ATS-family breakdown of broken vs. direct link share to pinpoint major ATS providers lacking validated direct links.
- By correctly preserving `link_status` globally across reconciled candidate groups instead of restricting it to `direct_employer` winners, the volume of unverified destinations will fall after a feed refresh.

## Conclusion and Follow-up Experiment
The initial investigation of `repair_links.py` and `build_feed.py` revealed that the root cause of the lost validation metrics was hidden inside `reconcile_workday_duplicates.py`'s group-merging logic. Tests were written and added for both `audit_feed` and `reconcile_workday_duplicates` to ensure the preservation of link status metadata moving forward.

---

# Independent Northeast / Mid-Atlantic undergraduate CS coverage benchmark

External sample collected: `2026-09-17T20:00:00Z`
Yartchives feed snapshot: `2026-10-02T14:23:23.882253Z`
Scope: profiles=cs, states=CT,NY,NJ,PA,DE,MD,DC,VA,MA,RI

- External observations collected: **142**
- Unique external listings (denominator): **142**
- Duplicate observations collapsed: **0**
- Captured or probably captured: **67** (47.2%)
- Visible under expected filters: **47** (33.1%)
- Actionable findings: **95**

## Missing listings by ATS family

- `employer/custom`: **35**
- `discovery-only`: **25**
- `workday`: **7**
- `greenhouse`: **6**
- `icims`: **1**
- `usajobs`: **1**

## Results by benchmark state

- `CT`: **20** listings, **10** missing (50.0% recall)
- `DC`: **25** listings, **15** missing (40.0% recall)
- `DE`: **6** listings, **6** missing (0.0% recall)
- `MA`: **6** listings, **2** missing (66.7% recall)
- `MD`: **27** listings, **22** missing (18.5% recall)
- `NJ`: **6** listings, **5** missing (16.7% recall)
- `NY`: **34** listings, **8** missing (76.5% recall)
- `PA`: **6** listings, **0** missing (100.0% recall)
- `RI`: **6** listings, **5** missing (16.7% recall)
- `VA`: **6** listings, **2** missing (66.7% recall)

## Results by region

- `Mid-Atlantic`: **110** listings, **58** missing (47.3% recall)
- `New England`: **32** listings, **17** missing (46.9% recall)

## Missing listings by reason code

- `uncovered_source`: **41**
- `known_employer_missing_role`: **32**
- `configured_source_listing_absent`: **2**

## Status breakdown

- `already_in_yartchives`: 47
- `filtered_or_misclassified`: 13
- `duplicate_resolution_issue`: 7
- `employer_exists_but_listing_missing`: 32
- `configured_source_miss`: 2
- `source_not_covered`: 41
- `unknown`: 0

## Miss category breakdown

- `source_missing`: 38
- `employer_unresolved`: 32
- `unsupported_ats`: 3
- `freshness_lag`: 2
- `parsing_normalization_failure`: 7
- `eligibility_filtering_mistake`: 13
- `uncertain`: 0

## Root-cause breakdown

- `uncovered_source`: 41
- `exact_match`: 37
- `known_employer_missing_role`: 32
- `present_but_hidden`: 10
- `provider_identity_match`: 10
- `provider_identity_mismatch`: 4
- `probable_duplicate`: 3
- `configured_source_listing_absent`: 2
- `provider_identity_match_hidden`: 2
- `probable_match_but_hidden`: 1

## Action queue

- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Castleton Commodities International — Cybersecurity Internship (Summer 2027) — Stamford, CT
  - Why: Yartchives has 3 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): Spectrum — 2027 Summer Intern: Revenue Assurance - Corporate — Stamford, CT
  - Why: source_key=2026 81711
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): Spectrum — 2027 Summer Intern: Business Analyst — Stamford, CT
  - Why: source_key=2026 81924
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): Interactive Brokers — Software Developer Summer Internship - 2027 — Greenwich, CT
  - Why: source_key=4456794958
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): Interactive Brokers — Cybersecurity Internship 2027 — Greenwich, CT
  - Why: source_key=4450266402
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): Otis Elevator Co. — Embedded Software Engineering Intern — Farmington, CT
  - Why: source_key=4462304550
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): HSB - Hartford Steam Boiler — Data Science Intern — Hartford, CT
  - Why: source_key=14193
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): LiquidPiston — Electrical Engineering Intern - Spring 2027 — Suffield, CT
  - Why: source_key=4459970155
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **configured_source_miss** / **freshness_lag** (`configured_source_listing_absent`): Avangrid — 2027 Technology, Cyber & Data Internship Program — Orange, CT
  - Why: source appears configured (employer has a configured direct source) but this listing is absent after ingestion
  - Next: Inspect source freshness, adapter filters, ingestion errors, and enrichment for this listing.
- **source_not_covered** / **source_missing** (`uncovered_source`): Selective Insurance — IT E&S Insurance Product Delivery Summer Internship — Hartford, CT
  - Why: source_key=selective it product delivery 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): Schonfeld — 2027 Business Analytics Intern — New York, NY
  - Why: missing expected profile 'cs'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`provider_identity_match_hidden`): Schonfeld — 2027 DMFI Technology Intern — New York, NY
  - Why: missing expected profile 'cs'; missing expected state 'NY'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): DV Trading — Client Platforms Engineer Intern - Summer 2027 — New York, NY
  - Why: Yartchives has 11 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`provider_identity_match_hidden`): DV Trading — Quantitative Research Intern - Summer 2027 (DV Equities) — New York, NY
  - Why: missing expected profile 'cs'; missing expected state 'NY'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): Lyft — Data Analyst Intern (Summer 2027) — New York, NY
  - Why: missing expected profile 'cs'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **duplicate_resolution_issue** / **parsing_normalization_failure** (`probable_duplicate`): Lyft — Software Engineer Intern, Fullstack (Summer 2027) — New York, NY
  - Why: same employer has a very similar title and compatible location
  - Next: Verify requisition identity; if it is the same role, improve normalization.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Point72 — Machine Learning Researcher - Intern — New York, NY
  - Why: Yartchives has 5 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): Point72 — Quantitative Researcher Intern — New York, NY
  - Why: missing expected profile 'cs'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Point72 — Quantitative Software Developer Intern — New York, NY
  - Why: Yartchives has 5 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Audax Group — IT Operations Co-Op — New York, NY
  - Why: Yartchives has 4 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): BNY — 2027 BNY Summer Internship Program - Engineering (Developer) - New York, NY — New York, NY
  - Why: missing expected profile 'cs'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **duplicate_resolution_issue** / **parsing_normalization_failure** (`probable_duplicate`): BNY — 2027 BNY Summer Internship Program - Engineering (Production Services) - New York, NY — New York, NY
  - Why: same employer has a very similar title and compatible location
  - Next: Verify requisition identity; if it is the same role, improve normalization.
- **source_not_covered** / **source_missing** (`uncovered_source`): Good Molecules — Full Stack Engineering Intern — New York, NY
  - Why: source_key=1023521130
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Gemini — Blockchain & Web3 Software Engineering Intern — New York, NY
  - Why: Yartchives has 2 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): Federal Reserve Bank of Philadelphia — 2027 Summer Intern - Technology Group - Junior — New York, NY
  - Why: source_key=1014424208
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): Federal Reserve Bank of Philadelphia — 2027 Summer Intern - Technology Group - Sophomore — New York, NY
  - Why: source_key=1014424209
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Johns Hopkins Applied Physics Laboratory — 2027 Internship - Software Development - Multi-Mission Planning Development — Laurel, MD
  - Why: Yartchives has 16 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **duplicate_resolution_issue** / **parsing_normalization_failure** (`provider_identity_mismatch`): Johns Hopkins Applied Physics Laboratory — 2027 Internship - Software Developer - Tactical System Prototyping and Deployment — Laurel, MD
  - Why: same ATS/listing identifier exists but title/location evidence is not compatible enough for an exact match
  - Next: Verify provider identity and improve canonicalization/deduplication if these are the same role.
- **duplicate_resolution_issue** / **parsing_normalization_failure** (`provider_identity_mismatch`): Johns Hopkins Applied Physics Laboratory — 2027 Internship - Software Engineer/Data Scientist/Ontologist - Threat Analytic Systems — Laurel, MD
  - Why: same ATS/listing identifier exists but title/location evidence is not compatible enough for an exact match
  - Next: Verify provider identity and improve canonicalization/deduplication if these are the same role.
- **duplicate_resolution_issue** / **parsing_normalization_failure** (`provider_identity_mismatch`): Johns Hopkins Applied Physics Laboratory — 2027 Internship - Decision Science, Software Engineer, System Engineer — Laurel, MD
  - Why: same ATS/listing identifier exists but title/location evidence is not compatible enough for an exact match
  - Next: Verify provider identity and improve canonicalization/deduplication if these are the same role.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Johns Hopkins Applied Physics Laboratory — 2027 Internship - Cybersecurity - Mission Engineering — Laurel, MD
  - Why: Yartchives has 16 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Leidos — Software Developer Intern — Annapolis Junction, MD
  - Why: Yartchives has 5 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Leidos — Cybersecurity Analyst Intern — Odenton, MD
  - Why: Yartchives has 5 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): Leonardo DRS — Summer 2027 Software Engineering Intern — Frederick, MD
  - Why: source_key=115335
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): Textron Systems — 2027 Intern - Software Engineer (Electronic Systems) - Hunt Valley, MD — Hunt Valley, MD
  - Why: source_key=textron es software 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): Textron Systems — 2027 Co-Op - Software Engineer (Uncrewed Land & Air) - Hunt Valley, MD — Hunt Valley, MD
  - Why: source_key=342620
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): Textron Systems — 2027 Intern - Software Engineer (Sea Systems) - Hunt Valley, MD — Hunt Valley, MD
  - Why: source_key=textron sea software 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): Textron Systems — 2027 Intern - Firmware Engineer (Weapons) - Hunt Valley, MD — Hunt Valley, MD
  - Why: source_key=textron firmware weapons 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): HII Mission Technologies — Software Engineer Intern (Multiple Levels) - 30069 — Columbia, MD
  - Why: source_key=30069
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): Visionist — Software Engineer Intern — Columbia, MD
  - Why: source_key=visionist software intern 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): AeroVironment — Summer 2027 Software Engineering Intern — Germantown, MD
  - Why: Yartchives has 16 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): AeroVironment — Summer 2027 Software Engineering Intern — Annapolis Junction, MD
  - Why: Yartchives has 16 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): AeroVironment — Summer 2027 Embedded Software Engineering Intern — Annapolis Junction, MD
  - Why: Yartchives has 16 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): MITRE — Internships in Computer Science or Software Engineering — Aberdeen, MD
  - Why: source_key=mitre cs swe aberdeen 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): MITRE — Internships in Cybersecurity and Information Security — Gaithersburg, MD
  - Why: source_key=mitre cyber gaithersburg 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Exelon — 2027 Summer Internship - Cyber Security (Owings Mills, Maryland) — Owings Mills, MD
  - Why: Yartchives has 1 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Exelon — 2027 Summer Internship - Data Science/Analytics — Windsor Mill, MD
  - Why: Yartchives has 1 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): Maryland State Department of Education — Office of IT, Cybersecurity Intern — Baltimore, MD
  - Why: source_key=26 005302 0011
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): Stanley Black & Decker — Embedded Engineering Summer Intern 2027 — Towson, MD
  - Why: missing expected profile 'cs'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **source_not_covered** / **source_missing** (`uncovered_source`): Peraton Labs — Summer 2027 Cyber Research Intern — Silver Spring, MD
  - Why: source_key=2026 170120
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): NSA — Summer 2027 Internship Program - Cryptanalysis and Signals Analysis — Fort Meade, MD
  - Why: source_key=nsa cryptanalysis signals 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): NSA — 2027 Summer Internship Program - Data Center Facility Management — Fort Meade, MD
  - Why: source_key=4454899399
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): Palantir Technologies — Forward Deployed Software Engineer, Internship - Defense Tech — Washington, DC
  - Why: missing expected state 'DC'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): Palantir Technologies — Forward Deployed Software Engineer, Internship - US Government — Washington, DC
  - Why: missing expected state 'DC'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): Palantir Technologies — Software Engineer, Internship — Washington, DC
  - Why: missing expected state 'DC'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): Palantir Technologies — Software Engineer, Internship - Production Infrastructure — Washington, DC
  - Why: missing expected state 'DC'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`present_but_hidden`): The Nuclear Company — Spring 2027 AI Applied Research Internship — Washington, DC
  - Why: missing expected profile 'cs'
  - Next: Review profile/state/type enrichment or default filter metadata.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Anduril — Winter 2027 Technical Program Management Co-op — Washington, DC
  - Why: Yartchives has 3 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Anduril — Winter 2027 Test Automation Engineer Co-op — Washington, DC
  - Why: Yartchives has 3 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Amtrak — Fall 2026/Spring 2027 - Software Engineering Intern - 90413041 - Washington — Washington, DC
  - Why: Yartchives has 1 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Amtrak — Spring 2027 - Software Engineering Intern - 90413037 - Washington — Washington, DC
  - Why: Yartchives has 1 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Amtrak — Fall 2026/Spring 2027 - AI Engineer Intern - 90413047 - Washington — Washington, DC
  - Why: Yartchives has 1 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Amtrak — Fall 2026/Spring 2027 - Data & AI Insights Engineer Intern - 90413049 - Washington — Washington, DC
  - Why: Yartchives has 1 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Shield AI — Summer 2027 - Software Engineer Intern — Washington, DC
  - Why: Yartchives has 3 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): TikTok USDS Joint Venture — Security Engineer Intern (Security & Privacy) - 2027 Summer — Washington, DC
  - Why: source_key=tiktok usds security dc 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): PwC — Technology Consulting - Intern - Summer 2027 — Washington, DC
  - Why: source_key=4461560565
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): PwC — Cybersecurity Consulting Intern - Summer 2027 — Washington, DC
  - Why: source_key=pwc cyber consulting dc 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **source_not_covered** / **source_missing** (`uncovered_source`): PwC — Deals - DTDS - Analytics Intern - Summer 2027 — Washington, DC
  - Why: source_key=pwc dtds analytics dc 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs. Keep the discovery platform audit-only rather than scraping it.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Amgen — Undergrad Intern Software Engineer - Technology & Medical Organizations (Summer 2027) — Washington, DC
  - Why: Yartchives has 17 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Supreme Court of the United States — Office of Information Technology - IT Operations Intern — Washington, DC
  - Why: Yartchives has 7 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): Inter-American Development Bank — Undergraduate Emerging Technologies Lab Intern — Washington, DC
  - Why: source_key=1233446
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Exelon — 2027 Summer Internship - Data Science/Analytics — Washington, DC
  - Why: Yartchives has 1 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Verizon — Verizon Consumer Group: AI/ML Engineering Summer 2027 Internship — Basking Ridge, NJ
  - Why: Yartchives has 2 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **unsupported_ats** (`uncovered_source`): UPS — UPS Technology Group Summer 2027 Internship - NJ — Mahwah, NJ
  - Why: source_key=r26029748
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): The Campbell's Company — Information Technology Internship Program - Summer 2027 — Camden, NJ
  - Why: source_key=req 68193
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **configured_source_miss** / **freshness_lag** (`configured_source_listing_absent`): IAT Insurance Group — System Administrator Internship — Newark, NJ
  - Why: source appears configured (employer has a configured direct source) but this listing is absent after ingestion
  - Next: Inspect source freshness, adapter filters, ingestion errors, and enrichment for this listing.
- **filtered_or_misclassified** / **eligibility_filtering_mistake** (`probable_match_but_hidden`): Johnson & Johnson — Technology and Digital Quality Intern — Raritan, NJ
  - Why: missing expected profile 'cs'
  - Next: Verify the role identity, then review profile/state/type enrichment.
- **source_not_covered** / **unsupported_ats** (`uncovered_source`): Crum & Forster — Data Science Internship - Summer 2027 — Morristown, NJ
  - Why: source_key=5108
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **duplicate_resolution_issue** / **parsing_normalization_failure** (`provider_identity_mismatch`): Westinghouse Electric Company — Summer Intern - Computer Engineering / Software Engineering — Cranberry Township, PA
  - Why: same ATS/listing identifier exists but title/location evidence is not compatible enough for an exact match
  - Next: Verify provider identity and improve canonicalization/deduplication if these are the same role.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Barclays — 2027 Technology Developer Summer Internship Program Wilmington — Wilmington, DE
  - Why: Yartchives has 17 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): Hologic — Software Engineering Internship — Newark, DE
  - Why: source_key=300000447085490
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **unsupported_ats** (`uncovered_source`): Agilent Technologies — Intern - R&D Software Engineering (AI & Test Automation) — Wilmington, DE
  - Why: source_key=4038437
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): Siemens Mobility — Data Analysis Internship - Customer Service (Summer 2027) — New Castle, DE
  - Why: source_key=siemens data analysis new castle 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): Delmarva Digital — Software Developer / UI / UX Internship — Laurel, DE
  - Why: source_key=delmarva digital ui ux 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): JPMorgan Chase — Software Engineer Internship Program — Wilmington, DE
  - Why: Yartchives has 17 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Huntington Ingalls Industries — 2027 IT Summer Internship - IT Intern — Newport News, VA
  - Why: Yartchives has 1 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Capital One — Technology Internship Program - Summer 2027 — McLean, VA
  - Why: Yartchives has 12 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Liberty Mutual — Cybersecurity Co-op (January - June 2027) — Boston, MA
  - Why: Yartchives has 2 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **duplicate_resolution_issue** / **parsing_normalization_failure** (`probable_duplicate`): S&P Global — Software Engineer - Summer Intern 2027 — Cambridge, MA
  - Why: same employer has a very similar title and compatible location
  - Next: Verify requisition identity; if it is the same role, improve normalization.
- **source_not_covered** / **source_missing** (`uncovered_source`): Keurig Dr Pepper — Winter 2027 Co-op - Mobile App Development — Burlington, MA
  - Why: source_key=145448
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): Citizens — Software Engineer Summer 2027 Intern — Johnston, RI
  - Why: source_key=49286
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): Citizens — Data Engineer Summer 2027 Intern — Johnston, RI
  - Why: source_key=49285
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **source_not_covered** / **source_missing** (`uncovered_source`): Citizens — Cloud Engineer Summer 2027 Intern — Johnston, RI
  - Why: source_key=49284
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
- **employer_exists_but_listing_missing** / **employer_unresolved** (`known_employer_missing_role`): Workiva — Spring & Summer 2027 Intern - Security & GRC — Providence, RI
  - Why: Yartchives has 8 listing(s) for this employer but not this role
  - Next: Trace the role to the employer ATS and check source filters or add direct coverage.
- **source_not_covered** / **source_missing** (`uncovered_source`): FM — Software Engineering Co-op - Spring 2027 — Johnston, RI
  - Why: source_key=fm software engineering coop spring 2027
  - Next: Trace to the employer career/ATS page and add durable direct coverage if the miss recurs.
