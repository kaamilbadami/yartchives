# Decoupled Feed Publication Architecture

## Objective

Yartchives currently publishes refreshed runtime feed data by committing generated `data/listings.json` and `data/workday-inspections.json` back to the Git `main` branch. This tightly couples data freshness to source-control commits, causing merge conflicts, slow Git operations, and leaving the user-visible feed stale if the final Git push fails. The goal is to choose the lowest-complexity decoupled feed publication architecture that preserves the existing GitHub Pages deployment model while decoupling data generation from Git commits.

## Architecture Evaluation

We evaluated three potential architectures for decoupling feed publication:

### 1. Keep Git-backed Publication (Further Isolation)
This approach would involve committing the generated feed to an isolated orphan branch (e.g., `gh-pages-data` or `feed-runtime`) rather than `main`.

*   **Freshness Reliability:** Medium. It avoids conflicts with `main` source code, but large diffs can still cause GitHub API timeouts, and race conditions between concurrent feed updates can still lead to Git push failures.
*   **Failure Isolation:** High. Failures would not break the `main` branch, but could leave the isolated data branch in an inconsistent state.
*   **Implementation Complexity:** Low. We already use Git commits; it just requires changing the target branch.
*   **Cache Busting:** Relies on arbitrary query string timestamps or frontend logic.
*   **Rollback/Versioning:** Native to Git (using `git revert` or resetting to a previous commit).
*   **Local Development:** High. Local developers can easily check out the data branch to test the latest data locally.
*   **Observability/Debuggability:** Medium. Git history is accessible, but viewing large JSON diffs is difficult.
*   **Operational/Cost Burden:** Zero financial cost, but operational overhead of managing large Git repositories and potential API limits remains.

### 2. GitHub-Native Artifact/Static Publication
In this architecture, the `update-feed.yml` GitHub Action generates the feed JSON files and uploads them directly as GitHub Actions Workflow Artifacts. The deployment workflow (`deploy-pages.yml`) consumes these artifacts and deploys them to GitHub Pages alongside the static frontend.

*   **Freshness Reliability:** High. Artifact upload and Pages deployment are atomic and not subject to Git merge conflicts or push race conditions.
*   **Failure Isolation:** High. A failed feed pipeline simply results in no artifact being published; the existing deployed GitHub Pages site continues serving the last known-good version.
*   **Implementation Complexity:** Low to Medium. Requires modifying `update-feed.yml` to use `actions/upload-artifact` instead of `git commit`, and adjusting `deploy-pages.yml` to download the latest artifact before building the `_site` directory.
*   **Cache Busting:** High. GitHub Pages handles cache headers, and we can leverage the existing `__YARTCHIVES_BUILD_SHA__` injected into `index.html` to reference the artifact version, guaranteeing the frontend requests the correct cache-busted file.
*   **Rollback/Versioning:** Medium. Rollbacks involve re-running a previous deployment workflow in GitHub Actions or using the GitHub Deployments UI.
*   **Local Development:** Medium. Developers would need a script to download the latest feed artifact from the GitHub API, rather than just running `git pull`.
*   **Observability/Debuggability:** High. Artifacts for each workflow run are preserved and can be downloaded directly from the GitHub Actions UI.
*   **Operational/Cost Burden:** Zero financial cost (included in GitHub Actions limits), completely removes Git history bloat.

### 3. External Object/Blob Storage (e.g., AWS S3, GCS, Cloudflare R2)
This approach involves pushing the generated JSON files directly to a cloud object storage bucket.

*   **Freshness Reliability:** Very High. Dedicated storage services are built for high availability and consistency.
*   **Failure Isolation:** High. Independent from GitHub infrastructure entirely.
*   **Implementation Complexity:** High. Requires provisioning cloud resources, setting up OIDC/IAM credentials in GitHub Actions, and managing CORS policies for the frontend.
*   **Cache Busting:** High. Full control over HTTP Cache-Control headers on the object storage.
*   **Rollback/Versioning:** Native object versioning (e.g., S3 versioning).
*   **Local Development:** High. Developers can directly fetch the feed from the public URL.
*   **Observability/Debuggability:** High. Full access logs and versioning.
*   **Operational/Cost Burden:** Adds unnecessary paid infrastructure and added operational complexity of managing external cloud provider accounts, which violates the strict architectural constraints.

---

## Recommended Architecture: GitHub-Native Artifact/Static Publication

The **GitHub-Native Artifact/Static Publication** architecture is selected as the lowest-complexity path that fits within existing constraints.

It completely decouples runtime data generation from source-control Git commits, eliminating repository bloat and merge conflicts. It leverages our existing reliance on GitHub Pages, requires no external paid infrastructure, and strictly prevents invalid feed pipelines from corrupting the live site.

## Migration Sequence

1.  **Modify Feed Generation Actions:** Update `.github/workflows/update-feed.yml` and `.github/workflows/refresh-inspections.yml`. Instead of pushing commits to `main`, use `actions/upload-artifact` to expose `data/listings.json` and `data/workday-inspections.json` as workflow artifacts (e.g., `yartchives-listings`, `yartchives-inspections`).
2.  **Modify Deployment Action:** Update `.github/workflows/deploy-pages.yml` to download the latest successful runtime artifacts using `actions/download-artifact` or the GitHub API (e.g., `gh run download`) before building the `_site` payload.
3.  **Update Frontend Cache-Busting:** Update `app.js` to rely on the deployed build SHA injected into `index.html` by `deploy-pages.yml` rather than using `Date.now()`, ensuring the requested data asset perfectly aligns with the deployed site version.
4.  **Add Local Development Tooling:** Provide a script (e.g., `scripts/download_latest_feed.py`) that uses the GitHub API to fetch the latest known-good feed artifacts, ensuring local development remains frictionless.
5.  **Remove Checked-in Data:** Once the artifact pipeline is fully functional and successfully publishing to GitHub Pages, delete `data/listings.json` and `data/workday-inspections.json` from the repository and add them to `.gitignore`.

### Rollback Path

If the artifact-based deployment causes critical failures during migration:
1. Revert the workflow file changes (`update-feed.yml`, `deploy-pages.yml`) back to their Git-commit-based versions.
2. Remove the `.gitignore` rules for the JSON data files.
3. Trigger the legacy deployment workflow. GitHub Pages will seamlessly revert to deploying the files currently checked into `main`.

## Frontend Discovery and Cache Busting

Currently, the frontend bypasses browser caches by appending arbitrary timestamps to the URL (`data/listings.json?ts=${Date.now()}`). This breaks HTTP caching semantics and can cause version skew.

In the new architecture:
1. When `deploy-pages.yml` processes the site deployment, it already injects a `BUILD_SHA` into `index.html`.
2. The frontend in `app.js` will read this `yartchives-build` meta tag on initialization.
3. It will construct data fetch URLs using this exact build hash (e.g., `data/listings.json?v=__YARTCHIVES_BUILD_SHA__`).
4. This guarantees deterministic static-site cache busting, ensuring the user always downloads the exact valid feed payload deployed with that specific frontend version.

## Handling Invalid or Failed Refreshes

The existing feed validation step ensures malformed feeds fail the build early. In the new architecture:
1. If an execution of `update-feed.yml` fails (e.g., due to a structural validation error, scraper failure, or runtime exception), the GitHub Action fails.
2. Because the workflow fails before reaching the artifact upload step, no new artifact is produced.
3. Subsequent runs of `deploy-pages.yml` will continue pulling the *last known-good successful artifact* for deployment.
4. The GitHub Pages deployment remains completely uncorrupted, continuing to serve the healthy legacy feed data without interruption.

## Implementation note

The migration keeps the checked-in runtime JSON files temporarily as rollback and local-development seed snapshots, but routine refreshes no longer publish by committing those files. Each producer hydrates from the newest publishable artifact first, then uploads a replacement only after its runtime data has passed the relevant validation/update boundary.

For feed publication, artifact existence is the validity signal rather than the final workflow conclusion. This allows a validated feed to remain publishable even if a later audit/reporting step fails, while runs that fail before validation produce no replacement artifact and therefore leave the last known-good deployment intact. Once the artifact path has been proven operational, the fallback snapshots can be removed in a separate cleanup without changing the runtime publication contract.
