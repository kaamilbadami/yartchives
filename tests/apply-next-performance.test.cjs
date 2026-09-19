const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");
const A = require("../apply-next.js");
const UI = require("../apply-next-ui.js");

const listingsObject = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "data", "listings.json"), "utf8"));
const listings = Array.isArray(listingsObject) ? listingsObject : listingsObject.jobs || Object.values(listingsObject) || [];
let artifact;
try {
  artifact = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "data", "workday-inspections.json"), "utf8"));
} catch (e) {
  artifact = {};
}

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs", "tech-business"],
  supportedKeywords: ["software", "testing", "systems", "linux", "java", "c"],
  cautiousKeywords: ["python", "bash"],
  facts: {
    graduation: "May 2028",
    workAuthorization: "U.S. citizen; no sponsorship needed",
    supportedSkills: ["Java", "C", "Linux", "testing"],
    cautiousSkills: ["Python", "Bash"],
  },
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer", "software developer"] },
    { id: "testing", label: "Testing / systems", priority: 1, keywords: ["test engineer", "qa", "systems"] },
    { id: "analytics", label: "Technical analytics", priority: 0.8, keywords: ["data analyst", "business analyst"] },
  ],
  preferredStates: ["MD", "DC", "CT", "NY"],
  remoteRelevant: true,
  relocationAllowed: true,
  nearbyMiles: 50,
};

UI.attachInspections(listings, artifact);

const state = {
  applied: new Set(),
  hidden: new Set(),
  saved: new Set()
};

const now = new Date();
const startRank = performance.now();
const pool = UI.candidatePool(listings, profile, state);
const ranked = A.rankJobs(pool, profile, now);
const endRank = performance.now();
const rankTime = endRank - startRank;

console.log(`Ranking ${listings.length} jobs took ${rankTime.toFixed(2)} ms`);

// Test state transition bottlenecks
const startTransition = performance.now();
state.saved.add(listings[0].id);

// Since we patched apply-next-ui to memoize ranking, let's just make sure
// if we call updateQueueOptimistically, it's fast.
UI.updateQueueOptimistically(null, profile, listings[0].id);

const endTransition = performance.now();
const transitionTime = endTransition - startTransition;
console.log(`State transition for one action took ${transitionTime.toFixed(2)} ms`);

if (process.env.CI && transitionTime > 1500) {
    throw new Error(`State transition is too slow! Took ${transitionTime.toFixed(2)} ms (budget is 1500ms)`);
}

console.log("apply-next performance tests passed");
