const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const P = require("../apply-next-presentation.js");

let priorCalls = 0;
const scope = {
  YartchivesUtils: null,
  distanceForJob(job) {
    priorCalls += 1;
    job._applyNextAnchorDistanceSamples = [{ distanceMiles: 12 }];
    return 12;
  },
};

assert.equal(P.captureMatchedLocationPoints(scope), true);
assert.equal(P.captureMatchedLocationPoints(scope), true, "capture wrapper should be idempotent");
assert.equal(typeof scope.distanceForJob, "function");
const job = {};
assert.equal(scope.distanceForJob(job, { city: "college park", state: "MD" }, {}), 12);
assert.equal(priorCalls, 1);

const browserScript = fs.readFileSync(path.join(__dirname, "..", "apply-next-presentation.js"), "utf8");
let browserScoreCalls = 0;
let browserRankCalls = 0;
const browserScope = {
  console,
  YartchivesApplyNext: {
    scoreJob(job) {
      browserScoreCalls += 1;
      return { job, total: 80, components: {} };
    },
    rankJobs(jobs) {
      browserRankCalls += 1;
      return jobs.map(job => ({ job, total: 80, components: {} }));
    },
  },
  YartchivesApplyNextLocationPreferences: {
    orderedAnchors() {
      return [];
    },
  },
  YartchivesUtils: {
    STATE_NAMES: { MD: "Maryland" },
    distanceForJob() {
      return null;
    },
  },
  distanceForJob() {
    return null;
  },
};
browserScope.globalThis = browserScope;
vm.runInNewContext(browserScript, browserScope, { filename: "apply-next-presentation.js" });

const ranked = browserScope.YartchivesApplyNext.rankJobs([
  { id: "job-1", title: "Software Intern", company: "Example", location: "College Park, MD" },
], {}, new Date("2026-09-16T12:00:00Z"));
assert.equal(browserRankCalls, 1, "presentation wrapper should call the original browser ranker exactly once");
assert.equal(ranked.length, 1);
assert.equal(ranked[0].job.location, "College Park, MD");

const scored = browserScope.YartchivesApplyNext.scoreJob(
  { id: "job-2", title: "Software Intern", company: "Example", location: "Baltimore, Maryland" },
  {},
  new Date("2026-09-16T12:00:00Z")
);
assert.equal(browserScoreCalls, 1, "presentation wrapper should call the original browser scorer exactly once");
assert.equal(scored.job.location, "Baltimore, MD");

console.log("apply-next presentation browser hook tests passed");
