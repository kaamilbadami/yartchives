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
  assert.ok(index.includes('src="apply-next-ui.js"'));
  assert.ok(index.indexOf('src="apply-next.js"') < index.indexOf('src="apply-next-ui.js"'));

  const uiSource = fs.readFileSync(path.join(__dirname, "..", "apply-next-ui.js"), "utf8");
  assert.match(uiSource, /local storage/i);
  assert.match(uiSource, /Authoritative posting evidence/);
  assert.match(uiSource, /data\/workday-inspections\.json/);
  assert.doesNotMatch(uiSource, /Kaamil|Badami|kaamil\.badami/i);

  const deployWorkflow = fs.readFileSync(path.join(__dirname, "..", ".github", "workflows", "deploy-pages.yml"), "utf8");
  assert.ok(deployWorkflow.includes("data/workday-inspections.json"), "Pages workflow must deploy Workday inspections");

  console.log("apply-next UI tests passed");
})().catch(error => {
  console.error(error);
  process.exit(1);
});
