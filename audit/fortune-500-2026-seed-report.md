# Fortune 500 2026 employer seed report

Generated from the frozen `fortune-500-2026` employer seed catalog on 2026-09-17. No careers resolution or job enumeration was run for this report.

## Provenance

- Publisher: Fortune Media IP Limited
- Edition: 2026
- Edition-pinned source: `https://fortune.com/ranking/fortune500/2026/`
- Published timestamp exposed by the ranking payload: `2026-06-03 05:10:23`
- Retrieved: `2026-09-17T21:40:00Z`
- Selection: first 500 rows by `order` from `props.pageProps.franchiseSearch.items`
- Selected-row SHA-256: `50a5abf698e3e495cb9bf129385e5db13a0b9233d191e6142d01de0f06b180e3`

Fortune exposes 1,000 ordered rows on this page. The seed builder selects orders 1 through 500 and retains Fortune's published `rank`, including ties at ranks 160 and 350. Only order, rank, company name, and Fortune company slug are retained per employer.

## Merge metrics

| Metric | Count |
| --- | ---: |
| Fortune 500 seed records | 500 |
| Merged into existing employer identities | 7 |
| Newly added employers | 493 |
| Resulting employer-universe size | 549 |

The 7 merged identities are American Express, Amgen, BNY, DoorDash, Exelon, Leidos, Stanley Black & Decker. Existing display names and benchmark metadata remain canonical; Fortune names and ranks are added as aliases and seed-specific metadata where applicable.

## Existing resolution-queue readiness

For the 500 Fortune-seeded employer identities:

| Readiness | Count |
| --- | ---: |
| `ready` | 1 |
| `needs_tenant_identity` | 1 |
| `no_domain_hint` | 498 |

Leidos is immediately ready. DoorDash retains a shared Greenhouse-domain hint and is `needs_tenant_identity`. These hints come only from previously preserved benchmark evidence; the Fortune catalog contributes none.

Across the full 549-employer unresolved universe, the corresponding counts are 20 `ready`, 13 `needs_tenant_identity`, and 516 `no_domain_hint`.

## Identity findings

The conservative alias rules produced 34 aliases across 31 catalog records. Parenthetical aliases and one-pass legal-entity suffix stripping are allowed; semantic business terms such as Group, International, Technologies, and Worldwide are intentionally preserved. No identity collisions were found. Parenthetical names supply aliases such as `BNY`; terminal corporate descriptors supply aliases such as `Leidos` from `Leidos Holdings`; and a leading `The` is ignored for matching.

The flat identity model should not be broadened to collapse corporate families automatically. The current data contains parent/division or parent/brand pairs such as General Dynamics / General Dynamics Electric Boat, Huntington Ingalls Industries / HII Mission Technologies, Textron / Textron Systems, Otis Worldwide / Otis Elevator Co., and Charter Communications / Spectrum. These may share ownership while retaining distinct recruiting identities. Scaling beyond deterministic display-name aliases would benefit from an explicit parent-child/brand relationship field rather than more aggressive normalization.
