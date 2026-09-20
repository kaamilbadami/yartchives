# Yartchives Product Invariants

This file records product semantics that should be difficult to change accidentally. Documentation is not sufficient on its own: each invariant below is enforced by executable tests.

## Apply Next ranking contract

The final recommendation score is exactly 100 points:

| Signal | Role | Maximum |
| --- | --- | ---: |
| Qualification fit | ranking | 45 |
| Application value | ranking | 25 |
| Location fit | ranking | 20 |
| Freshness | ranking | 10 |
| Eligibility | gate | 0 |
| Link provenance | metadata | 0 |

The canonical source is `SCORING_CONTRACT` in `apply-next-dimensions.js`. Score composition must whitelist fields whose contract role is `ranking`; adding a field to a component object cannot make it count automatically.

### Semantic invariants

- **Link provenance is not a ranking signal.** Otherwise-identical direct, intermediary-listing, and source-only jobs must receive the same score. Link provenance may still control destination/display behavior.
- **Eligibility is a gate, not a bonus.** Passing eligibility cannot increase rank; failing an exclusion removes the recommendation.
- **The approved ranking maxima sum to exactly 100.** CI must fail if the contract drifts above or below 100.
- **Unknown components are inert.** A future component cannot affect the total unless it is explicitly added to the canonical contract with role `ranking`.
- **UI score denominators come from the canonical contract.** Do not maintain a second independent weighting scheme in presentation code.

Executable coverage lives primarily in `tests/apply-next-dimensions.test.cjs` and `tests/apply-next-ui.test.cjs`.

## Changing an invariant

A product-semantic change is intentional only when the issue explicitly requests it. The same PR must:

1. update the canonical contract or owning product contract;
2. update paired/golden behavioral regression tests;
3. update this file;
4. explain the before/after behavior in the PR description.

Refactors must preserve these invariants.
