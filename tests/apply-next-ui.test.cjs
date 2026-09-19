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
assert.equal(UI.totalScoreBandClass(50), "apply-next-score-low");
assert.equal(UI.totalScoreBandClass(65), "apply-next-score-medium");
assert.equal(UI.totalScoreBandClass(85), "apply-next-score-high");
// rankingSummary tests
// Note: test environment componentMax: fit=40, freshness=10, roi=15, location=15
assert.equal(
  UI.rankingSummary({
    components: { fit: { score: 30 }, freshness: { score: 8 }, roi: { score: 12 }, location: { score: 12 } } // Ratios: fit: 30/40=0.75, freshness: 8/10=0.8, roi: 12/15=0.8, location: 12/15=0.8
  }),
  "Why this is here: strongest drivers: timing, role value, location convenience and profile match."
);
assert.equal(
  UI.rankingSummary({
    components: { fit: { score: 35 }, freshness: { score: 9 }, roi: { score: 6 }, location: { score: 9 } } // Ratios: fit: 35/40=0.875, freshness: 9/10=0.9, roi: 6/15=0.4, location: 9/15=0.6
  }),
  "Why this is here: strongest drivers: timing and profile match; limited by: role value."
);
assert.equal(
  UI.rankingSummary({
    components: { fit: { score: 20 }, freshness: { score: 2 }, roi: { score: 3 }, location: { score: 4 } } // Ratios: fit: 20/40=0.5, freshness: 2/10=0.2, roi: 3/15=0.2, location: 4/15=0.26
  }),
  "Why this is here: limited by: location convenience, timing and role value."
);
assert.equal(
  UI.rankingSummary({
    components: { fit: { score: 40 }, freshness: { score: 2 }, roi: { score: 14 }, location: { score: 4 } } // Ratios: fit: 40/40=1.0, freshness: 2/10=0.2, roi: 14/15=0.93, location: 4/15=0.26
  }),
  "Why this is here: strongest drivers: profile match and role value; limited by: location convenience and timing."
);

// worthApplyingSummary tests
assert.equal(
  UI.worthApplyingSummary({
    components: { fit: { score: 35 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } },
    inspection: { state: "inspected" }
  }),
  "Yes: strong match, high value, recent, convenient location, verified posting."
);

assert.equal(
  UI.worthApplyingSummary({
    components: { fit: { score: 35 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } },
    inspection: { state: "metadata-only" }
  }),
  "Uncertain: strong match, high value, recent, convenient location; unverified evidence."
);

assert.equal(
  UI.worthApplyingSummary({
    components: { fit: { score: 20 }, freshness: { score: 2 }, roi: { score: 5 }, location: { score: 5 } },
    inspection: { state: "unavailable" }
  }),
  "Mixed: concerns: weak match, lower value, older posting, less convenient location, posting unavailable."
);

assert.equal(
  UI.worthApplyingSummary({
    components: { fit: { score: 20 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } },
    inspection: { state: "inspected" }
  }),
  "Mixed: high value, recent, convenient location, verified posting; concerns: weak match."
);

assert.equal(
  UI.worthApplyingSummary({
    excluded: true,
    components: { fit: { score: 35 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } }
  }),
  "No: excluded by eligibility constraints."
);

const postedNow = new Date("2026-09-17T12:00:00Z");
assert.equal(UI.formatPostedDate("2026-09-15T23:30:00-04:00", true, postedNow), "Posted 9/16 · 1 day ago");
assert.equal(UI.formatPostedDate("2026-09-15", true, postedNow), "Posted 9/15 · 2 days ago");
assert.equal(UI.formatPostedDate("2026-09-15", false, postedNow), "2 days ago");
assert.equal(
  UI.formatPostedDate("2025-12-31T23:00:00Z", true, new Date("2026-01-02T01:00:00Z")),
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

assert.equal(UI.formatPostedDate("", true, postedNow), "");
assert.equal(UI.formatPostedDate("not-a-date", true, postedNow), "");
assert.equal(UI.formatPostedDate("2026-09-15", true, "not-a-date"), "");

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

  const hideHandler = uiSource.match(
    /hide\.addEventListener\("click",\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\}\);/
  );
  assert.ok(hideHandler, "Hide click handler should be present");
  assert.match(hideHandler[1], /state\.hidden\.add\(job\.id\);/, "Hide should add to hidden state");
  assert.match(hideHandler[1], /persist\(\);/, "Hide should persist state");
  assert.match(hideHandler[1], /updateQueueOptimistically/, "Hide should trigger optimistic queue update immediately");
  assert.match(hideHandler[1], /applyFilters\(\);/);

  assert.match(uiSource, /Restore them from the main feed\./, "Should document recovery path for Applied and Hidden jobs");
  assert.match(uiSource, /setProfileSetupMode\(true\)/, "Profile setup should enter focused onboarding mode");
  assert.match(uiSource, /setProfileSetupMode\(false\)/, "Queue and panel close paths should restore the normal feed");
  assert.match(uiSource, /apply-next-profile-mode/, "Focused onboarding should use an explicit main-state class");

  assert.doesNotMatch(uiSource, /<option value="newest">Newest<\/option>/, "Apply Next should not expose a Newest sort mode");

  assert.match(uiSource, /document\.createDocumentFragment\(\)/, "renderQueue should build DOM off-screen before swapping to avoid UI stalls");
  assert.doesNotMatch(uiSource, /Kaamil|Badami|kaamil\.badami/i);

  const deployWorkflow = fs.readFileSync(path.join(__dirname, "..", ".github", "workflows", "deploy-pages.yml"), "utf8");
  assert.ok(deployWorkflow.includes("data/workday-inspections.json"), "Pages workflow must deploy Workday inspections");

  // Feedback state tests
  const feedbackStorageVals = new Map();
  const feedbackStorage = {
    getItem: key => feedbackStorageVals.get(key) || null,
    setItem: (key, value) => feedbackStorageVals.set(key, value),
    removeItem: key => feedbackStorageVals.delete(key),
  };

  // Ensure we start with clean state
  UI.loadFeedback(feedbackStorage);
  assert.equal(UI.getFeedback("job1"), null, "Feedback should default to null");

  UI.setFeedback(feedbackStorage, "job1", "good");
  let stored = UI.getFeedback("job1");
  assert.ok(stored, "Feedback should be saved");
  assert.equal(stored.type, "good", "Feedback type should be good");
  assert.equal(stored.reason, null, "Reason should be null for good feedback");

  // Verify persistence
  const rawFeedback = JSON.parse(feedbackStorageVals.get(UI.FEEDBACK_STORAGE_KEY) || "{}");
  assert.ok(rawFeedback["job1"], "Feedback should be persisted to storage");
  assert.equal(rawFeedback["job1"].type, "good");

  UI.setFeedback(feedbackStorage, "job1", "bad", "location");
  stored = UI.getFeedback("job1");
  assert.equal(stored.type, "bad", "Feedback should update to bad");
  assert.equal(stored.reason, "location", "Reason should be saved");

  UI.setFeedback(feedbackStorage, "job1", null);
  assert.equal(UI.getFeedback("job1"), null, "Feedback should be cleared when type is null");

  const rawCleared = JSON.parse(feedbackStorageVals.get(UI.FEEDBACK_STORAGE_KEY) || "{}");
  assert.ok(!rawCleared["job1"], "Cleared feedback should be removed from storage");

  console.log("apply-next UI tests passed");
})().catch(error => {
  console.error(error);
  process.exit(1);
});
const oldProfile = { targetTerm: "Summer 2027", roleFamilies: [{ id: "software" }] };
assert.equal(UI.explainProfileChange(oldProfile, oldProfile, "1", "1"), null);

const newTerm = { targetTerm: "Fall 2027", roleFamilies: [{ id: "software" }] };
assert.match(UI.explainProfileChange(oldProfile, newTerm, "1", "1"), /Recommendations re-evaluated after target term changes./);

const newRole = { targetTerm: "Summer 2027", roleFamilies: [{ id: "data" }] };
assert.match(UI.explainProfileChange(oldProfile, newRole, "1", "2"), /This new top recommendation is stronger under your updated role preferences./);

const multiChange = { targetTerm: "Fall 2027", roleFamilies: [{ id: "data" }] };
assert.match(UI.explainProfileChange(oldProfile, multiChange, "1", "2"), /This new top recommendation is a better match for your updated profile./);
assert.match(UI.explainProfileChange(oldProfile, multiChange, "1", "2"), /role and target term changes/);

const nonMaterial = { targetTerm: "Summer 2027", roleFamilies: [{ id: "software" }], version: 2 };
assert.match(UI.explainProfileChange(oldProfile, nonMaterial, "1", "1"), /Recommendations re-evaluated after profile changes./);
