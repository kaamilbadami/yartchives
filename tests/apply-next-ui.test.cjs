const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const UI = require("../apply-next-ui.js");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
  baseZips: ["06897", "20740"],
  baseLabels: ["Wilton", "College Park / DC"],
};

assert.equal(UI.validateProfile(profile).ok, true);
assert.equal(UI.validateProfile({ roleFamilies: profile.roleFamilies }).ok, false);
assert.equal(UI.validateProfile({ targetTerm: "Summer 2027", roleFamilies: [] }).ok, false);
assert.equal(UI.componentMax("fit"), 40);
assert.equal(UI.componentMax("role"), 20);
assert.equal(UI.componentMax("location"), 15);
assert.equal(UI.componentMax("roi"), 15);
assert.equal(UI.componentMax("freshness"), 10);
assert.equal(UI.componentMax("eligibility"), 0);
assert.equal(UI.componentMax("link"), 0);
assert.equal(UI.componentLabel("fit"), "How well you match");
assert.equal(UI.componentLabel("freshness"), "How recent it is");
assert.equal(UI.componentLabel("roi"), "Worth applying");
assert.equal(UI.componentLabel("location"), "Location convenience");
assert.match(UI.componentExplanation("fit"), /skills, major, degree level/i);
assert.equal(UI.scoreBand("fit", 30, 40), "Strong match");
assert.equal(UI.scoreBand("freshness", 5, 10), "Recent");
assert.equal(UI.scoreBand("roi", 10, 30), "Lower value");
assert.equal(UI.scoreBand("location", 15, 20), "Very convenient");
assert.match(UI.rankingSummary({ components: { fit: { score: 30 }, freshness: { score: 8 }, roi: { score: 23 }, location: { score: 15 } } }), /^Why this is here: /);
const postedNow = new Date("2026-09-17T12:00:00Z");
assert.equal(UI.formatPostedDate("2026-09-15T23:30:00-04:00", postedNow), "Posted 9/16 · 1 day ago");
assert.equal(UI.formatPostedDate("2026-09-15", postedNow), "Posted 9/15 · 2 days ago");
assert.equal(
  UI.formatPostedDate("2025-12-31T23:00:00Z", new Date("2026-01-02T01:00:00Z")),
  "Posted 12/31 · 2 days ago"
);
assert.deepEqual(
  UI.orderLocationValues(
    ["St. Louis, MO", "Austin, TX", "Bloomfield, CT"],
    [1100, 1700, 35],
    [900, 1300, 35],
  ),
  ["Bloomfield, CT", "St. Louis, MO", "Austin, TX"]
);
assert.deepEqual(
  UI.orderLocationValues(
    ["Morris Plains, NJ", "Bloomfield, CT"],
    [Infinity, 40],
    [25, 40],
  ),
  ["Bloomfield, CT", "Morris Plains, NJ"]
);

assert.equal(UI.locationValueText({ text: "USA - Remote" }), "USA - Remote");
assert.equal(UI.locationValueText({ display_name: "Bloomfield, CT" }), "Bloomfield, CT");
assert.equal(UI.locationValueText({ city: "College Park", state: "MD" }), "College Park, MD");
assert.equal(
  UI.locationValueText({ values: ["Bloomfield, CT", "Morris Plains, NJ"] }),
  "Bloomfield, CT · Morris Plains, NJ"
);
assert.deepEqual(
  UI.locationDisplayValues({ location: { city: "College Park", state: "MD" } }),
  ["College Park, MD"]
);
assert.doesNotMatch(UI.locationValueText({ city: "College Park", state: "MD" }), /\[object Object\]/);

assert.equal(
  UI.cardLocationText({
    location: "Fallback, MD",
    _displayLocation: { text: "Bloomfield, CT · Morris Plains, NJ", preferred: "Bloomfield, CT", all: ["Bloomfield, CT", "Morris Plains, NJ"] },
  }),
  "Bloomfield, CT · Morris Plains, NJ"
);
assert.doesNotMatch(
  UI.cardLocationText({ _displayLocation: { text: "USA - Remote" }, location: "fallback" }),
  /\[object Object\]/
);

assert.equal(UI.formatPostedDate("", postedNow), "");
assert.equal(UI.formatPostedDate("not-a-date", postedNow), "");
assert.equal(UI.formatPostedDate("2026-09-15", "not-a-date"), "");

const values = new Map();
const storage = {
  getItem: key => values.get(key) || null,
  setItem: (key, value) => values.set(key, value),
};
UI.saveProfile(storage, profile);
assert.deepEqual(UI.loadProfile(storage), profile);
assert.ok(values.has(UI.STORAGE_KEY));

const jobs = [
  { id: "good", term: "Summer 2027" },
  { id: "unknown-term", term: null },
  { id: "wrong-term", term: "Summer 2026" },
  { id: "applied", term: "Summer 2027" },
  { id: "hidden", term: "Summer 2027" },
];
const pool = UI.candidatePool(jobs, profile, {
  applied: new Set(["applied"]),
  hidden: new Set(["hidden"]),
});
assert.deepEqual(pool.map(job => job.id), ["good", "unknown-term"]);
assert.equal(UI.knownWrongTerm(jobs[2], profile), true);
assert.equal(UI.knownWrongTerm(jobs[1], profile), false);
assert.match(UI.profileSummary(profile), /Summer 2027/);
assert.match(UI.profileSummary(profile), /Wilton/);

const artifact = {
  version: 3,
  listing_index: {
    good: "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Role_REQ-1",
    "unknown-term": "https://careers-example.icims.com/jobs/74848/job",
  },
  entries: {
    "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Role_REQ-1": {
      inspection: {
        status: "inspected",
        posting: { application_status: "available" },
        requirements: {},
      },
    },
    "https://careers-example.icims.com/jobs/74848/job": {
      provider: "icims",
      inspection: {
        provider: "icims",
        status: "inspected",
        posting: { application_status: "available" },
        requirements: {},
      },
    },
  },
};
UI.attachInspections(jobs, artifact);
assert.equal(jobs[0]._inspection.status, "inspected");
assert.equal(jobs[1]._inspection.provider, "icims");
assert.equal(jobs[2]._inspection, undefined);

(async () => {
  const loaded = await UI.loadInspectionArtifact(async (url, options) => {
    assert.equal(url, UI.INSPECTION_URL);
    assert.equal(options.cache, "no-store");
    return { ok: true, json: async () => artifact };
  });
  assert.deepEqual(loaded.listing_index, artifact.listing_index);

  const failed = await UI.loadInspectionArtifact(async () => {
    throw new Error("offline");
  });
  assert.deepEqual(failed, { version: 1, entries: {}, listing_index: {} });

  const index = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  assert.ok(index.includes('href="apply-next.css"'));
  assert.ok(index.includes('src="apply-next.js"'));
  assert.ok(index.includes('src="apply-next-dimensions.js"'));
  assert.ok(index.includes('src="apply-next-ui.js"'));
  assert.ok(index.indexOf('src="apply-next.js"') < index.indexOf('src="apply-next-dimensions.js"'));
  assert.ok(index.indexOf('src="apply-next-dimensions.js"') < index.indexOf('src="apply-next-ui.js"'));

  const uiSource = fs.readFileSync(path.join(__dirname, "..", "apply-next-ui.js"), "utf8");
  assert.match(uiSource, /local storage/i);
  assert.match(uiSource, /Authoritative posting evidence/);
  assert.match(uiSource, /metadata is used as a fallback/);
  assert.match(uiSource, /apply-next-inspection-\$\{inspectionState\}/);
  assert.match(uiSource, /Worth applying/);
  assert.match(uiSource, /How well you match/);
  assert.match(uiSource, /How recent it is/);
  assert.match(uiSource, /Location convenience/);
  assert.match(uiSource, /Posted \$\{monthDay\} · \$\{ageLabel\}/);
  assert.match(uiSource, /apply-next-posted-date/);
  assert.match(uiSource, /data\/workday-inspections\.json/);
  assert.match(uiSource, /job\.link_kind === "employer_job" \? "View posting ↗" : "Apply ↗"/);
  const appliedHandler = uiSource.match(
    /applied\.addEventListener\("click",\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\}\);/
  );
  assert.ok(appliedHandler, "Mark applied click handler should be present");
  assert.match(appliedHandler[1], /updateQueueOptimistically/, "Mark applied should trigger optimistic queue update immediately");
  assert.match(appliedHandler[1], /applyFilters\(\);/);
  assert.doesNotMatch(
    appliedHandler[1],
    /renderPanel\(/,
    "Mark applied should rely on optimistic update and applyFilters/renderJobs panel refresh instead of triggering a second expensive render"
  );
  assert.match(uiSource, /document\.createDocumentFragment\(\)/, "renderQueue should build DOM off-screen before swapping to avoid UI stalls");
  assert.doesNotMatch(uiSource, /Kaamil|Badami|kaamil\.badami/i);

  const deployWorkflow = fs.readFileSync(path.join(__dirname, "..", ".github", "workflows", "deploy-pages.yml"), "utf8");
  assert.ok(deployWorkflow.includes("data/workday-inspections.json"), "Pages workflow must deploy Workday inspections");

  console.log("apply-next UI tests passed");
})().catch(error => {
  console.error(error);
  process.exit(1);
});