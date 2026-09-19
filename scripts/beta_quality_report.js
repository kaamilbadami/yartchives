const fs = require('fs');
const D = require('../apply-next-dimensions.js');
const Metrics = require('../apply-next-metrics.js');

function generateReport(rankedJobs, profile, now, localState, feedbackState) {
  let report = [];
  report.push("# Beta Quality Report");
  report.push("");
  report.push("> **Limitation:** This report is generated using deterministically simulated fixture data for interactions. No backend telemetry or user accounts exist in the current architecture. Therefore, we cannot durably aggregate conversion rates or feedback across users. All metrics presented below are a single-session snapshot based on local state limitations.");
  report.push("");

  if (!rankedJobs || rankedJobs.length === 0) {
    report.push("## Missing/Unknown Data");
    report.push("No jobs available to generate report metrics.");
    return report.join("\n");
  }

  // Application Conversion
  report.push("## Application Conversion (Top 10)");
  const conversionMetrics = Metrics.measureConversion(rankedJobs, localState, 10);
  if (conversionMetrics.eligible === 0) {
    report.push("Missing/Unknown Data for Conversion.");
  } else {
    report.push(`- Eligible: ${conversionMetrics.eligible}`);
    report.push(`- Applied: ${conversionMetrics.applied}`);
    report.push(`- Saved: ${conversionMetrics.saved}`);
    report.push(`- Hidden: ${conversionMetrics.hidden}`);
    report.push(`- Viewed (No Action): ${conversionMetrics.viewedNoAction}`);
    report.push(`- Conversion Rate (Applied / Eligible): ${(conversionMetrics.conversionRate * 100).toFixed(1)}%`);
  }
  report.push("");

  // Recommendation Feedback
  report.push("## Recommendation Feedback (Top 10)");
  const feedbackMetrics = Metrics.analyzeFeedback(rankedJobs, feedbackState, 10);
  if (feedbackMetrics.totalRated === 0) {
    report.push("Missing/Unknown Data for Feedback.");
  } else {
    report.push(`- Total Rated: ${feedbackMetrics.totalRated}`);
    report.push(`- Good: ${feedbackMetrics.goodCount}`);
    report.push(`- Bad: ${feedbackMetrics.badCount}`);
    report.push(`- Good Rate: ${(feedbackMetrics.goodRate * 100).toFixed(1)}%`);
    report.push("- Bad Suggestion Reasons:");
    for (const [reason, count] of Object.entries(feedbackMetrics.reasons)) {
      report.push(`  - ${reason}: ${count}`);
    }
  }
  report.push("");

  // Recommendation Exhaustion Simulation
  report.push("## Recommendation Exhaustion Simulation");
  report.push(`- Initial eligible pool size: ${rankedJobs.length}`);
  let top10 = rankedJobs.slice(0, 10);
  report.push(`- Initial Top 10 range: ${top10[0]?.total || 0} to ${top10[9]?.total || 0}`);
  report.push(`- Initial Rank 50 score: ${rankedJobs[49]?.total || 0}`);
  report.push("");

  let pool = [...rankedJobs];
  const MAX_ACTIONS = 200;
  let applied = 0;
  let hidden = 0;

  for (let i = 1; i <= MAX_ACTIONS; i++) {
    if (pool.length === 0) break;
    const job = pool.shift();

    // Deterministic rule: Apply every 5th action, Hide otherwise
    if (i % 5 === 0) applied++;
    else hidden++;

    const newTop10 = pool.slice(0, 10);
    const overlap = top10.filter(t => newTop10.some(n => n.job.id === t.job.id)).length;
    top10 = newTop10;

    if (i % 50 === 0 && pool.length > 0) {
        report.push(`### After ${i} actions (Applied: ${applied}, Hidden: ${hidden})`);
        report.push(`- Remaining eligible: ${pool.length}`);
        report.push(`- Top 10 Replenishment Range: ${top10[0]?.total || 0} to ${top10[9]?.total || 0}`);
        report.push(`- Top 10 Avg Fit Score: ${(top10.reduce((s, r) => s + r.components.fit.score, 0) / 10).toFixed(1)} / ${D.SCORE_MAXIMA.fit}`);
        report.push(`- Top 10 Overlap with previous action: ${overlap} / 10`);
        report.push("");
    }
  }

  return report.join("\n");
}

function loadFeed() {
    let data;
    try {
        data = JSON.parse(fs.readFileSync('data/listings.json', 'utf-8'));
    } catch (e) {
        return [];
    }

    let inspectionsData = { inspections: [] };
    try {
        inspectionsData = JSON.parse(fs.readFileSync('data/workday-inspections.json', 'utf-8'));
    } catch (e) {}

    const inspections = new Map();
    if (inspectionsData.inspections) {
        for (const i of inspectionsData.inspections) {
            inspections.set(i.url, i);
        }
    }

    const jobs = data.jobs || [];
    jobs.forEach(job => {
        job._inspection = {
            status: "inspected",
            posting: { application_status: "available" },
            requirements: {
                skills: { required: [], preferred: [], unspecified: [], not_required: [] },
                education: { required: [], preferred: [], unspecified: [], not_required: [] },
                major_fields: { required: [], preferred: [], unspecified: [], not_required: [] },
            }
        };
        if (inspections.has(job.url)) {
            job._inspection = inspections.get(job.url);
        }
    });

    return jobs;
}

if (require.main === module) {
  const jobs = loadFeed();

  const profile = {
    targetTerm: "Summer 2027",
    opportunityTypes: ["internship", "co-op"],
    excludeGraduateOnly: true,
    preferredProfiles: ["cs"],
    supportedKeywords: ["software", "java", "python", "git", "linux", "sql"],
    cautiousKeywords: ["c++", "c#"],
    facts: {
      degree: "Bachelor of Science",
      major: "Computer Science",
      supportedSkills: ["Java", "Python", "Git", "Linux", "SQL"],
      cautiousSkills: ["C++", "C#"],
      graduation: "May 2028",
    },
    roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
    preferredStates: ["NY", "MA", "CA", "WA"],
    relocationAllowed: true,
    locationMode: "normal",
    baseZips: [],
    baseLabels: [],
    nearbyMiles: 50,
  };

  const now = new Date("2026-09-17T12:00:00Z");
  const ranked = jobs.length > 0 ? D.rankJobs(jobs, profile, now) : [];

  const localState = {
    applied: new Set(),
    hidden: new Set(),
    saved: new Set()
  };

  const feedbackState = {};

  if (ranked.length >= 10) {
      localState.applied.add(ranked[0].job.id);
      localState.applied.add(ranked[1].job.id);
      localState.saved.add(ranked[2].job.id);
      localState.hidden.add(ranked[3].job.id);

      feedbackState[ranked[0].job.id] = { type: 'good' };
      feedbackState[ranked[1].job.id] = { type: 'good' };
      feedbackState[ranked[2].job.id] = { type: 'bad', reason: 'location' };
      feedbackState[ranked[3].job.id] = { type: 'bad', reason: 'role interest' };
      feedbackState[ranked[4].job.id] = { type: 'bad', reason: 'unknown' };
  }

  const reportString = generateReport(ranked, profile, now, localState, feedbackState);
  fs.writeFileSync('beta_quality_report.md', reportString);
}

module.exports = { generateReport };
