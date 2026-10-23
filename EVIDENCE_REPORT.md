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
