const assert = require('assert');
const { generateReport } = require('../scripts/beta_quality_report.js');

(function testBetaQualityReport() {
    console.log("Running beta quality report regression tests...");

    // Test missing/unknown data behavior
    const emptyReport = generateReport([], {}, new Date(), {}, {});
    assert.ok(emptyReport.includes("## Missing/Unknown Data"), "Should print Missing/Unknown Data for empty jobs");
    assert.ok(emptyReport.includes("No jobs available to generate report metrics."), "Should have reason for missing data");
    assert.ok(emptyReport.includes("> **Limitation:**"), "Disclaimer should always be present");

    // Test valid data
    const jobs = Array.from({ length: 60 }, (_, i) => ({
        job: { id: `job${i}` },
        total: 100 - i,
        components: { fit: { score: 20 } }
    }));

    const localState = {
        applied: new Set(['job0']),
        saved: new Set(['job1']),
        hidden: new Set(['job2'])
    };

    const feedbackState = {
        'job0': { type: 'good' },
        'job1': { type: 'bad', reason: 'location' }
    };

    const report = generateReport(jobs, {}, new Date(), localState, feedbackState);

    // Check conversion metrics
    assert.ok(report.includes("## Application Conversion (Top 10)"));
    assert.ok(report.includes("- Eligible: 10"));
    assert.ok(report.includes("- Applied: 1"));
    assert.ok(report.includes("- Saved: 1"));
    assert.ok(report.includes("- Hidden: 1"));
    assert.ok(report.includes("- Viewed (No Action): 7"));
    assert.ok(report.includes("- Conversion Rate (Applied / Eligible): 10.0%"));

    // Check feedback metrics
    assert.ok(report.includes("## Recommendation Feedback (Top 10)"));
    assert.ok(report.includes("- Total Rated: 2"));
    assert.ok(report.includes("- Good: 1"));
    assert.ok(report.includes("- Bad: 1"));
    assert.ok(report.includes("- Good Rate: 50.0%"));
    assert.ok(report.includes("- location: 1"));

    // Check exhaustion
    assert.ok(report.includes("## Recommendation Exhaustion Simulation"));
    assert.ok(report.includes("- Initial eligible pool size: 60"));
    assert.ok(report.includes("### After 50 actions"));

    console.log("All tests passed.");
})();
