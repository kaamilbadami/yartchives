1. **Update `scripts/direct_successfactors.py`**
   - Add a helper function `_is_sso_or_base_domain` that checks if a hostname is an SSO or base SAP domain (e.g. `.accounts.ondemand.com`, `.accounts.cloud.sap`, `.sapsf.com`, etc).
   - In `_successfactors_source`, if the resolved `careers_url` is an SSO or base domain, scan `employer["careers_resolution"]["evidence"]` for the best alternative URL (prioritizing `successfactors provider fingerprint` and score) that is not an SSO or base domain, and use it as the `sitemap_url` and `homepage` origin.

2. **Update `employer_universe.json`**
   - Remove the `provider-lifecycle-overrides` for `gxo-logistics` to restore it to the resolution pool, correctly handling it with the new generic logic without weakening validation. This was done in the previous step during discovery, and the state was already modified.

3. **Update `tests/test_direct_successfactors.py`**
   - Add a test `test_successfactors_source_falls_back_from_sso_domain` that verifies the fallback logic correctly prefers a valid ATS domain from evidence over a 403-inducing SSO base domain.
   - Update `test_successfactors_source_returns_none_when_retired` to use a generic dummy employer ID instead of `gxo-logistics` to prevent collisions.

4. **Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.**
   - Run `run_quality_checks.sh` and make sure it passes.

5. **Submit the change.**
   - Once all tests pass, submit the fix.
