# Application-link quality audit — 2026-09-16

## Scope and method

This is an audit of `origin/main` at `8e27ffc` (`data/listings.json` generated
at `2026-09-16T13:36:27.876110Z`).  It measures the feed's stored
`link_kind`, attributes a deduplicated job to every key in `source_keys`, and
inspects the current resolver pipeline (`repair_links.py`, `provider_links.py`,
`jobright_links.py`, and `source_links.py`).  Consequently, source totals below
are attribution totals and can exceed the 5,043 unique listings.

I made read-only checks of the configured public source files and a small set
of employer/ATS pages.  I did not scrape LinkedIn or Handshake, and I did not
modify the feed or any resolver.

`direct` means the repository currently classifies the URL as an employer or
ATS application URL.  It does not mean every one of those pages was freshly
validated: 1,560 direct URLs have `link_status: ok`, 18 are `unknown`, and
3,300 native/direct URLs have no per-link validation record.

## Current result

There are **5,043** listings: **4,878 direct (96.73%)**, 102 listing/
intermediary, and 63 source-only.

| `link_kind` | Count | Share | Meaning in this audit |
| --- | ---: | ---: | --- |
| `direct` | 4,878 | 96.73% | Employer or ATS URL present |
| `listing` | 102 | 2.02% | A specific aggregator listing is retained; no direct URL was safely recovered |
| `source` | 63 | 1.25% | Only source provenance remains; no application URL is exposed |

The pipeline is already doing meaningful generic recovery: 628 current direct
records came from the ApplyGuy data feed, 545 from redirect resolution, 401
from source-feed matching, and four from source-feed recovery.  The remaining
3,300 direct records arrived as direct URLs.

### Attribution by upstream source

| Source key | Direct | Listing | Source | Attributed total | Direct rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| simplify | 1,676 | 0 | 0 | 1,676 | 100.0% |
| dreamwork-tech | 731 | 0 | 0 | 731 | 100.0% |
| applyguy | 643 | 0 | 8 | 651 | 98.8% |
| zapply | 587 | 5 | 0 | 592 | 99.2% |
| speedyapply | 548 | 0 | 14 | 562 | 97.5% |
| dreamwork-business | 554 | 0 | 0 | 554 | 100.0% |
| vansh-cscareers | 217 | 0 | 41 | 258 | 84.1% |
| sndsh | 125 | 0 | 0 | 125 | 100.0% |
| campus-to-career | 114 | 0 | 0 | 114 | 100.0% |
| public-sector | 0 | 97 | 0 | 97 | 0.0% |
| usajobs | 44 | 0 | 0 | 44 | 100.0% |
| direct Connecticut Workday sources (five represented keys) | 6 | 0 | 0 | 6 | 100.0% |

The `public-sector` count is not a claim that its listings are broken: it is a
Jobright-only discovery feed whose retained action is correctly labelled as a
listing link when no authoritative destination can be proved.

### Direct-link ATS distribution

The direct set is predominantly ATS-hosted, not merely employer homepages.

| Identified destination family | Direct listings |
| --- | ---: |
| Workday (`*.myworkdayjobs.com`) | 2,015 |
| Greenhouse | 492 |
| Oracle Recruiting (`*.oraclecloud.com`) | 356 |
| Ashby | 272 |
| iCIMS | 174 |
| Lever | 91 |
| SmartRecruiters | 78 |
| Paylocity | 42 |
| SuccessFactors | 41 |
| UKG/UltiPro | 39 |
| USAJOBS | 44 |
| Other direct employer/ATS families | 1,175 |

This is a positive current finding: **no Oracle link is unresolved** in the
stored feed, despite Oracle being the third-largest identified ATS family.
Workday is also broadly working; only five unresolved Zapply URLs carry a
`workday-...` slug.

## Recurring unresolved groups

| Group / current host | Count | Evidence-backed root cause | ATS family when identifiable | Generic fix feasibility |
| --- | ---: | --- | --- | --- |
| Jobright detail URLs (`jobright.ai/jobs/info/...`) from `public-sector` | 97 | **Verified provider-wide gap.** All 97 retained intermediary links are Jobright. The current `jobright_links.py` first tries a structured detail page and then Jobright's visitor-search response; a live check of the IMEG sample returned `no-match`, even though a matching official page exists. This is a resolver/API-contract or matching-coverage issue, not an employer-specific failure. | Mixed; confirmed Workday for IMEG. The unresolved set cannot be assigned one ATS family from the feed alone. | **High.** Repair the generic Jobright resolver around its current public detail/API contract, retaining exact-ID or unique normalized company/title/location proof. |
| Vansh / CSCareers source-only rows (`github.com/vanshb03/...`) | 41 | **Verified source-state and ambiguity group, not a failed redirect.** The current upstream CNO row, for example, contains `🔒` rather than an Apply link. Re-reading the source with the existing candidate matcher yields 23 records with no candidate and 18 with 13 or 28 title-only candidates; choosing one would be unsafe. | Not determinable for the withheld rows; the ambiguous candidates span Workday, Greenhouse, Ashby, Lever, and others. | Low as a resolver-only change. Preserve withholding; improve source parsing only if it can explicitly recognize closed rows and avoid title-only collisions. |
| SpeedyApply source-only rows (`github.com/speedyapply/...`) | 14 | **Verified ambiguous duplicate-posting group.** Every remaining row has 2–4 direct candidates under the existing scoped match. For example, Raytheon's identical title/location has two distinct current Workday requisitions (`01870236` and `01873970`); EquipmentShare has three. The safe resolver correctly declines to select one. | Mostly Workday; also direct employer, iCIMS, and Greenhouse examples. | Low without a stronger stable key (requisition, posting URL, or source row identity). Do not guess. |
| Zapply listing URLs (`zapply.jobs/l/d/workday-...`) | 5 | **Verified small Workday-slug long tail.** Generic Workday resolution returned no URL for a Thornton Tomasetti sample. Zapply's five residual slugs encode tenant/site/requisition-like pieces, but the encoded provider label is not always the employer's final platform. | Zapply labels all five as Workday. The Equifax `J00178975` sample instead has a current official `careers.equifax.com` posting, so its slug is not sufficient evidence of the final ATS family. | Medium, but low leverage: only five records. A generic requisition-aware discovery fallback could help, provided it requires one exact validated result. |
| ApplyGuy source-only rows (`github.com/ApplyGuy/...`) | 8 | **Verified stale/unavailable source rows.** The current ApplyGuy data lookup supplies no unique direct candidate for these rows. Seven retain a previously validated-dead URL (two iCIMS, four Paylocity, one Datadog); they were deliberately downgraded instead of being presented as direct. | iCIMS and Paylocity for the known-dead URLs; one Greenhouse-derived employer page (Datadog). | Low. The correct general behavior is already to suppress dead links rather than retain them. |

The intermediary-host concentration is therefore unambiguous: **97 Jobright
(95.1% of 102 listing links)** and **five Zapply (4.9%)**.  All 63 source-only
records have GitHub provenance, split 41 Vansh/CSCareers, 14 SpeedyApply, and
eight ApplyGuy.

## Representative traces

These are point-in-time, read-only checks; they establish that a direct page
exists for the example, not that every listing in its group can be safely
recovered.

1. **Jobright → IMEG / Planning Intern / New York, NY** — feed listing:
   `https://jobright.ai/jobs/info/6a8de421cc0cf27068525e33`.  The current
   Jobright visitor-search resolver returned `no-match` for this record.
   However, the matching employer Workday posting is live at
   `https://imeg.wd1.myworkdayjobs.com/en-US/Imeg_Careers/job/Planning-Intern---New-York--NY_R-16669`.
   This verifies an authoritative destination exists and supports a Jobright
   provider-level recovery improvement.

2. **Zapply `workday-...` → Equifax / Data Analytics Intern** — feed listing:
   `https://zapply.jobs/l/d/workday-equifax-ur-external-J00178975`.
   The generic Workday resolver did not resolve it.  Equifax's current official
   posting is
   `https://careers.equifax.com/en/jobs/j00178975/data-analytics-intern/`.
   The requisition matches exactly; this verifies an employer URL exists but
   also shows that a Zapply `workday-` label need not identify the final URL
   family.

3. **SpeedyApply → Raytheon / Software Engineering Co-op — Summer/Fall 2027**
   — the source currently exposes two live Workday links with the same visible
   company, title, and location, requisitions `01870236` and `01873970`.  The
   source-only result is intentional: title/location matching cannot safely
   choose which job was meant.

4. **Vansh / CSCareers → CNO Financial Group / Cyber Security IT Intern** —
   the current source row says `🔒` in the Application/Link cell.  There is no
   direct source URL to recover; this is not evidence that an employer page is
   broken.

## Recommendation: implement next

**Restore generic Jobright authoritative-link recovery.**  It is the single
highest-leverage change because it targets 97 of 165 non-direct listings
(58.8%), whereas the next recoverable-looking group contains only five Zapply
records and the remaining source-only groups are deliberately ambiguous or
closed.

The implementation should update the Jobright public detail/API extraction
contract and accept a URL only when it is either tied to the exact Jobright ID
or is the sole exact normalized company/title/location result, followed by the
existing direct-URL validation.  Do not use employer-specific searches or a
best-guess ATS URL.  Add fixture coverage for the current response shape and
for a Jobright record whose official page is Workday.  This recommendation is
based on the verified IMEG trace; expected recovery yield across all 97 is a
**hypothesis** until the refreshed contract is tested against the full set.

## Limits

- This audit reports the generated snapshot and source files available on
  2026-09-16; listings and third-party pages can change after that point.
- It does not assert that an indirect listing is broken, nor does it treat a
  current `direct` classification as a fresh successful application-flow test.
- Representative public pages were checked manually; LinkedIn and Handshake
  were intentionally not scraped.
- The source-only and Jobright findings favor correctness over coverage: a
  missing unique candidate is insufficient evidence to promote an Apply URL.
