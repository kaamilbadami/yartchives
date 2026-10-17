const assert = require("node:assert/strict");
const D = require("../apply-next-dimensions.js");

const now = new Date("2026-09-16T16:00:00Z");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software", "java", "systems", "c++", "python", "linux", "git", "bash", "sql", "testing"],
  cautiousKeywords: ["rust"],
  facts: {
    degree: "Bachelor of Science",
    major: "Computer Science",
    supportedSkills: ["Java", "systems", "C++", "Python", "Linux", "Git", "Bash", "SQL", "testing"],
    cautiousSkills: ["Rust"],
  },
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
  preferredStates: ["CT"],
  relocationAllowed: true,
};

function inspection(required = [], preferred = []) {
  return {
    status: "inspected",
    posting: { application_status: "available" },
    requirements: {
      skills: {
        required: required.map(([statement, technologies]) => ({ statement, technologies })),
        preferred: preferred.map(([statement, technologies]) => ({ statement, technologies })),
        unspecified: [], not_required: [],
      },
      education: {
        required: [], preferred: [], unspecified: [], not_required: []
      },
      major_fields: {
        required: [], preferred: [], unspecified: [], not_required: []
      }
    },
  };
}

const jobs = [];
for (let i = 0; i < 100; i++) {
  jobs.push({
    id: `job-${i}`,
    company: `Company ${i}`,
    title: i % 2 === 0 ? "Software Engineer Intern" : "Data Science Intern",
    profiles: i % 3 === 0 ? ["cs"] : [],
    states: i % 4 === 0 ? ["CT"] : ["TX"],
    location: i % 4 === 0 ? "Hartford, CT" : "Dallas, TX",
    term: "Summer 2027",
    posted_at: new Date(now.getTime() - (i * 12 * 3600 * 1000)).toISOString(),
    link_kind: "direct",
    url: `https://example.com/job-${i}`,
    _inspection: inspection(i % 5 === 0 ? [["Java required", ["Java"]]] : (i % 5 === 1 ? [["Go required", ["Go"]]] : [])),
  });
}

const baseline = D.rankJobs(jobs, profile, now);
const medianJobId = baseline[50].job.id;

function measure(modifier) {
  const modJobs = jobs.map(j => j.id === medianJobId ? modifier(j) : j);
  const ranked = D.rankJobs(modJobs, profile, now);
  const rank = ranked.findIndex(r => r.job.id === medianJobId);
  return { rank, total: ranked[rank].total, components: ranked[rank].components };
}

const baseRank = measure(j => j);

const perfectFit = measure(j => ({ ...j, _inspection: inspection([["Java required", ["Java"]], ["C++ required", ["C++"]]], [["Python preferred", ["Python"]]]) }));
const badFit = measure(j => ({ ...j, _inspection: inspection([["Rust required", ["Rust"]]]) }));
const fitSpread = Math.abs(perfectFit.rank - badFit.rank);
assert.ok(fitSpread >= 15 && fitSpread <= 75, `Fit spread ${fitSpread} is outside reasonable bounds (15-75 ranks)`);

const goodLoc = measure(j => ({ ...j, states: ["CT"], location: "Hartford, CT" }));
const badLoc = measure(j => ({ ...j, states: ["TX"], location: "Dallas, TX" }));
const locSpread = Math.abs(goodLoc.rank - badLoc.rank);
assert.ok(locSpread >= 15 && locSpread <= 75, `Location spread ${locSpread} is outside reasonable bounds (15-75 ranks)`);

const goodFresh = measure(j => ({ ...j, posted_at: now.toISOString() }));
const badFresh = measure(j => ({ ...j, posted_at: "2025-01-01T00:00:00Z" }));
const freshSpread = Math.abs(goodFresh.rank - badFresh.rank);
assert.ok(freshSpread >= 15 && freshSpread <= 75, `Freshness spread ${freshSpread} is outside reasonable bounds (15-75 ranks)`);

const goodRole = measure(j => ({ ...j, title: "Software Engineer Intern", profiles: ["cs"] }));
const badRole = measure(j => ({ ...j, title: "Marketing Intern", profiles: [] }));
const roleSpread = Math.abs(goodRole.rank - badRole.rank);
assert.ok(roleSpread >= 15 && roleSpread <= 75, `Role spread ${roleSpread} is outside reasonable bounds (15-75 ranks)`);

console.log("apply-next sensitivity tests passed");
