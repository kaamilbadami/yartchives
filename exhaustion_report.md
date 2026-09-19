## Recommendation Exhaustion Report

- Initial eligible pool size: 4768
- Initial Top 10 range: 78 to 78
- Initial Rank 50 score: 76

### After 50 actions (Applied: 10, Hidden: 40)
- Remaining eligible: 4718
- Top 10 Replenishment Range: 76 to 74
- Top 10 Avg Fit Score: 18.0 / 40
- Top 10 Overlap with previous action: 9 / 10

### After 100 actions (Applied: 20, Hidden: 80)
- Remaining eligible: 4668
- Top 10 Replenishment Range: 72 to 71
- Top 10 Avg Fit Score: 18.0 / 40
- Top 10 Overlap with previous action: 9 / 10

### After 150 actions (Applied: 30, Hidden: 120)
- Remaining eligible: 4618
- Top 10 Replenishment Range: 71 to 71
- Top 10 Avg Fit Score: 18.0 / 40
- Top 10 Overlap with previous action: 9 / 10

### After 200 actions (Applied: 40, Hidden: 160)
- Remaining eligible: 4568
- Top 10 Replenishment Range: 69 to 69
- Top 10 Avg Fit Score: 18.0 / 40
- Top 10 Overlap with previous action: 9 / 10

### Dominant Causes of Premature Exhaustion
- The maximum score drops rapidly over the first few hundred actions.
- Missing Evidence: The **Fit** score stays very low across almost all high-ranking recommendations because most jobs lack authoritative inspection evidence, defaulting to a neutral fit score. We had to mock 'inspected' status for most jobs in this test just to get them to show up.
- Local Actions: Because Fit is not differentiating, the ranking overly relies on static Location and ROI, causing the top recommendations to bunch up and exhaust quickly once the perfectly-located/perfect-ROI matches are consumed.
- Ranking behavior / Sort instability: There was a systemic issue with `apply-next-dimensions.js` incorrectly parsing timestamps during sorting: `new Date(job?.posted_at) - new Date(...)` results in `NaN`, which breaks the sort stability and fallback comparisons, further contributing to poor exhaustion characteristics.