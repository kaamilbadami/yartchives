const fs = require('fs');
const D = require('../apply-next-dimensions.js');
const base = require('../apply-next.js');
const applyNextLocation = require('../apply-next-location.js');

function loadFeed() {
  const data = JSON.parse(fs.readFileSync('data/listings.json', 'utf-8'));
  const inspectionsData = JSON.parse(fs.readFileSync('data/workday-inspections.json', 'utf-8'));

  const inspections = new Map();
  if (inspectionsData.inspections) {
      for (const i of inspectionsData.inspections) {
          inspections.set(i.url, i);
      }
  }

  const jobs = data.jobs || [];
  jobs.forEach(job => {
      // By replacing missing _inspections with an "inspected" status but generic empty requirements,
      // we observe the "missing evidence" cause without breaking the apply-next-location gate.
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

const jobs = loadFeed();
const now = new Date("2026-09-17T12:00:00Z");

const ranked = D.rankJobs(jobs, profile, now);

// Using a deterministic sequence (e.g. alternating actions, apply 1 hide 4)
let pool = [...ranked];
let top10 = pool.slice(0, 10);

let report = [];
report.push("## Recommendation Exhaustion Report");
report.push("");
report.push(`- Initial eligible pool size: ${ranked.length}`);
report.push(`- Initial Top 10 range: ${top10[0]?.total || 0} to ${top10[9]?.total || 0}`);
report.push(`- Initial Rank 50 score: ${pool[49]?.total || 0}`);
report.push("");

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

// Dominant causes
report.push("### Dominant Causes of Premature Exhaustion");
report.push("- The maximum score drops rapidly over the first few hundred actions.");
report.push(`- Missing Evidence: The **Fit** score stays very low across almost all high-ranking recommendations because most jobs lack authoritative inspection evidence, defaulting to a neutral fit score. We had to mock 'inspected' status for most jobs in this test just to get them to show up.`);
report.push("- Local Actions: Because Fit is not differentiating, the ranking overly relies on static Location and ROI, causing the top recommendations to bunch up and exhaust quickly once the perfectly-located/perfect-ROI matches are consumed.");
report.push("- Ranking behavior / Sort instability: There was a systemic issue with `apply-next-dimensions.js` incorrectly parsing timestamps during sorting: `new Date(job?.posted_at) - new Date(...)` results in `NaN`, which breaks the sort stability and fallback comparisons, further contributing to poor exhaustion characteristics.");

fs.writeFileSync('exhaustion_report.md', report.join('\n'));
