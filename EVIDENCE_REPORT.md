# Evidence Report: Persistent Source Quarantine for SuccessFactors (403)

## Issue
Persistent source quarantine detected across two consecutive published-feed generations for the `auto-successfactors-american-airlines-group` source.
The root-cause signature was `StructuralSourceError: sitemap fetch failed with 403`.

## Root Cause Analysis
The 403 Forbidden error indicates that the endpoint is being protected by a WAF (such as Akamai) and strictly blocks automated crawling user agents (e.g., `Yartchives/1.0` or `Mozilla/5.0`). Because this WAF block is persistent, the endpoint essentially functions as permanently "retired" for our automated crawler.

## Proposed Paths & Why Insufficient
1. **Header Spoofing**: Attempting to bypass the WAF using brittle header spoofing or rotating user agents is generally ineffective against robust enterprise WAF solutions and leads to continued sporadic structural failures and CI breakages.
2. **Changing Global 403 Handling**: Updating `direct_successfactors.py` to classify all 403 errors as `EndpointRetiredError` instead of `StructuralSourceError` weakens the family-wide structural validation. Other sources could temporarily return a 403 (e.g. rate limiting or transient configuration issues), which should remain a structural error to be appropriately quarantined.

## Solution Implemented
To gracefully quarantine the source while maintaining strict structural validation across the SuccessFactors provider family, we used an explicit provider lifecycle override for the affected employer (`American Airlines Group`).
By updating `employer_universe.json` to include the `provider-lifecycle-overrides` seed setting the `successfactors` family status to `retired` for this employer, the employer will no longer be included in the auto-discovered SuccessFactors pool.

## Verification
1. Confirmed the 403 error for `https://jobs.aa.com/sitemap.xml` persists regardless of standard automated User Agents.
2. Verified that after applying the override (`scripts/refresh_employer_universe.py`), `American Airlines Group` is no longer fetched by the `direct_successfactors.py` crawler.
3. Verified the source is completely removed from the generated feed (`data/listings.json`), thereby resolving the quarantine issue without changing python crawler parser behaviors or weakening structural assertions.

No codebase tests required modification since this was purely a configuration/lifecycle state resolution.
