# Yartchives internal analytics backend

This directory contains the first-party receiver for Yartchives beta usage analytics.

## Privacy contract

The Worker accepts only the `yartchives-usage-v2` aggregate/session payload. It rejects unexpected top-level fields, unknown events, unknown timing fields, and requests from origins other than the configured Yartchives site origin.

The receiver does **not** store profile contents, resumes, searches, exact locations, job IDs, job titles, company names, browser user agents, or IP addresses.

## Storage

Raw flush batches are stored in Cloudflare D1 for 90 days. A scheduled Worker job rolls the previous UTC day into `daily_usage`, then removes raw rows older than 90 days.

## Automated deployment

`.github/workflows/deploy-analytics.yml` owns the backend. After these two repository secrets are configured once:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

the workflow finds or creates the `yartchives-analytics` D1 database, applies migrations, deploys the Worker, verifies `/health`, and publishes the receiver URL as the `yartchives-analytics-endpoint` artifact.

The Pages workflow consumes the newest successful endpoint artifact and injects it into the frontend automatically. If no backend artifact exists, Pages deploys with analytics disabled.

The Cloudflare API token should be scoped to the account and only the permissions needed for Workers and D1 deployment. Never commit credentials.
