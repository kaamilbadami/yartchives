# Regional benchmark change note

Previous feed snapshot: `2026-09-17T18:11:34.574004Z`
Current feed snapshot: `2026-09-17T18:32:35.335115Z`

## Benchmark delta

- Captured or probably captured: **53/106 (50.0%) → 53/106 (50.0%)**.
- Visible under expected filters: **33/106 (31.1%) → 34/106 (32.1%)**.
- Actionable findings: **73 → 72**.

## Status changes

- **Audax Group — IT Operations Co-Op** (New York, NY): `filtered_or_misclassified` → `already_in_yartchives`.

## Measurement caveat

The post-#85 production refresh successfully recovered **General Dynamics — Cybersecurity - 2027 Summer Internship** from the evidenced GDEB iCIMS site, and `ct-auto-icims-careers-gdeb-icims-com` contributed two CT CS listings. The benchmark nevertheless still reports the external **General Dynamics Electric Boat** observation as the remaining `icims: 1` miss. This is now a benchmark identity/matching false negative rather than an ingestion miss; the audit matcher does not currently reconcile that employer-name alias even though the provider requisition is present in the feed.
