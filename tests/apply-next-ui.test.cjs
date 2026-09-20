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
assert.equal(UI.componentMax("fit"), 45);
assert.equal(UI.componentMax("role"), 0);
assert.equal(UI.componentMax("location"), 20);
assert.equal(UI.componentMax("roi"), 25);
assert.equal(UI.componentMax("freshness"), 10);
assert.equal(UI.componentMax("eligibility"), 0);
assert.equal(UI.componentMax("link"), 0);
assert.equal(UI.componentMax("effort"), 0);
assert.equal(UI.componentLabel("fit"), "How well you match");
assert.equal(UI.componentLabel("freshness"), "How recent it is");
assert.equal(UI.componentLabel("roi"), "Worth applying");
assert.equal(UI.componentLabel("location"), "Location fit");
assert.match(UI.componentExplanation("fit"), /skills, major, degree level/i);
assert.equal(UI.scoreBand("fit", 30, 40), "Strong match");
assert.equal(UI.scoreBand("freshness", 5, 10), "Recent");
assert.equal(UI.scoreBand("roi", 10, 30), "Lower value");
assert.equal(UI.scoreBand("location", 15, 20), "Very convenient");
assert.equal(UI.scoreBand("location", 18, 20, { states: ["Remote", "CA"] }), "Remote");
assert.equal(UI.totalScoreBandClass(50), "apply-next-score-low");
assert.equal(UI.totalScoreBandClass(65), "apply-next-score-medium");
assert.equal(UI.totalScoreBandClass(85), "apply-next-score-high");
assert.equal(UI.FRESH_MAX_AGE_DAYS, 3);
assert.equal(UI.FRESH_MIN_SCORE, 55);

const freshNow = new Date("2026-09-19T12:00:00Z");
const freshRanked = [
  { total: 88, job: { id: "fresh-best", posted_at: "2026-09-19" } },
  { total: 86, job: { id: "fresh-three-day", posted_at: "2026-09-16" } },
  { total: 84, job: { id: "too-old", posted_at: "2026-09-15" } },
  { total: 54, job: { id: "fresh-low", posted_at: "2026-09-19" } },
  { total: 72, job: { id: "fresh-good", posted_at: "2026-09-17" } },
  { total: 70, job: { id: "unknown-date", posted_at: null } },
];
assert.equal(UI.postedAgeDays("2026-09-16", freshNow), 3);
assert.equal(UI.postedAgeDays("not-a-date", freshNow), null);
assert.deepEqual(
  UI.freshRankedResults(freshRanked, freshNow).map(result => result.job.id),
  ["fresh-best", "fresh-three-day", "fresh-good"]
);
assert.deepEqual(
  UI.visibleQueueResults(freshRanked, "recommended", freshNow).map(result => result.job.id),
  freshRanked.map(result => result.job.id)
);

const pagedRanked = Array.from({ length: 24 }, (_, index) => ({
  total: 100 - index,
  job: { id: `rank-${index + 1}`, posted_at: "2026-09-19" },
}));
assert.equal(UI.visibleQueueResults(pagedRanked, "recommended", freshNow).length, 10);
assert.equal(UI.visibleQueueResults(pagedRanked, "recommended", freshNow, 20).length, 20);
assert.equal(UI.visibleQueueResults(pagedRanked, "fresh", freshNow).length, 10);
assert.equal(UI.visibleQueueResults(pagedRanked, "fresh", freshNow, 20).length, 20);
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

// decisionHighlights tests
assert.deepEqual(
  UI.decisionHighlights({
    components: { fit: { score: 35 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } },
    inspection: { state: "inspected" }
  }),
  ["Strong match", "High value", "Very recent", "Very convenient location"]
);

assert.deepEqual(
  UI.decisionHighlights({
    job: { states: ["Remote", "CA"], location: "Remote · Thousand Oaks, CA" },
    components: { fit: { score: 35 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } },
    inspection: { state: "inspected" }
  }),
  ["Strong match", "High value", "Very recent", "Remote"]
);

assert.deepEqual(
  UI.decisionHighlights({
    components: { fit: { score: 35 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } },
    inspection: { state: "metadata-only" }
  }),
  ["Concerns: unverified evidence", "Strong match", "High value", "Very recent"] // concerns is prioritized and capped at 4 total
);

assert.deepEqual(
  UI.decisionHighlights({
    components: { fit: { score: 20 }, freshness: { score: 2 }, roi: { score: 5 }, location: { score: 5 } },
    inspection: { state: "unavailable" }
  }),
  ["Concerns: weak match, lower value, older posting, less convenient location, posting unavailable"]
);

assert.deepEqual(
  UI.decisionHighlights({
    components: { fit: { score: 20 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } },
    inspection: { state: "inspected" }
  }),
  ["Concerns: weak match", "High value", "Very recent", "Very convenient location"]
);

assert.deepEqual(
  UI.decisionHighlights({
    excluded: true,
    components: { fit: { score: 35 }, freshness: { score: 9 }, roi: { score: 12 }, location: { score: 12 } }
  }),
  ["Excluded by eligibility constraints"]
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
  assert.match(uiSource, /Location fit/);
  assert.doesNotMatch(uiSource, /Application access|application-link friction/);
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

  assert.match(uiSource, /apply-next-gap-hard/);
  assert.match(uiSource, /apply-next-gap-learnable/);
  assert.match(uiSource, /apply-next-gap-unknown/);

  const hideHandler = uiSource.match(
    /hide\.addEventListener\("click",\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\}\);/
  );
  assert.ok(hideHandler, "Hide click handler should be present");
  assert.match(hideHandler[1], /state\.hidden\.add\(job\.id\);/, "Hide should add to hidden state");
  assert.match(hideHandler[1], /persist\(\);/, "Hide should persist state");
  assert.match(hideHandler[1], /updateQueueOptimistically/, "Hide should trigger optimistic queue update immediately");
  assert.match(hideHandler[1], /applyFilters\(\);/);

  assert.doesNotMatch(uiSource, /function waitForBrowserPaint\(\)/, "Apply Next should not own a feature-specific paint helper");
  assert.match(uiSource, /await YartchivesUtils\.waitForBrowserPaint\(\)/, "Apply Next should use the shared browser-paint primitive");
  const renderQueueSource = uiSource.match(/async function renderQueue\(panel, profile\) \{([\s\S]*?)\n  \}/);
  assert.ok(renderQueueSource, "renderQueue should be present");
  assert.ok(
    renderQueueSource[1].indexOf("await YartchivesUtils.waitForBrowserPaint()") < renderQueueSource[1].indexOf("candidatePool(feed.jobs"),
    "Apply Next should yield a paint before synchronous candidate filtering"
  );
  const applyNextCss = fs.readFileSync(path.join(__dirname, "..", "apply-next.css"), "utf8");
  assert.match(applyNextCss, /\.apply-next-open:disabled\s*\{[\s\S]*?cursor:\s*progress/, "Disabled Apply Next should have a visible loading treatment");

  assert.match(uiSource, /Finding your best matches…/, "Apply Next should show an immediate loading message");
  assert.match(uiSource, /Still finding your best matches…/, "Apply Next should escalate the loading message if ranking takes longer");
  assert.match(uiSource, /setTimeout\(\(\) => \{[\s\S]*?\}, 1500\)/, "Apply Next should delay the long-loading message rather than showing it immediately");
  assert.match(uiSource, /panel\.setAttribute\("aria-busy", "true"\)/, "Apply Next should expose loading state to assistive technology");
  const openHandler = uiSource.match(
    /button\.addEventListener\("click", async \(\) => \{([\s\S]*?)\n\s*\}\);/
  );
  assert.ok(openHandler, "Apply Next open handler should be present");
  assert.match(openHandler[1], /YartchivesUtils\.runWithPendingUi\(\{/, "Apply Next should use the shared pending-UI helper");
  assert.match(openHandler[1], /control:\s*button/, "Apply Next should delegate button disabling/restoration to the shared helper");
  assert.match(openHandler[1], /pendingLabel:\s*"Finding matches…"/, "Apply Next should acknowledge the click immediately");
  assert.match(openHandler[1], /prepare:\s*\(\) => \{[\s\S]*?panel\.scrollIntoView/, "Apply Next should reveal its shell in the helper prepare phase");
  assert.match(openHandler[1], /work:\s*\(\) => renderPanel\(panel\)/, "Apply Next should start recommendation work only after the shared paint boundary");

  assert.match(uiSource, /setProfileSetupMode\(true\)/, "Apply Next should enter focused mode");
  assert.match(uiSource, /setProfileSetupMode\(false\)/, "Closing Apply Next should restore the normal feed");
  assert.match(uiSource, /apply-next-profile-mode/, "Focused Apply Next should use an explicit main-state class");

  assert.match(uiSource, /panel\.setAttribute\("aria-label", "Apply Next"\)/, "Panel should have an accessible label");
  assert.match(uiSource, /button\.setAttribute\("aria-controls", "applyNextPanel"\)/, "Button should control the panel via aria-controls");
  assert.match(uiSource, /textarea\.setAttribute\("aria-label", "Paste your Apply Next profile JSON here"\)/, "Textarea should have an accessible label");
  assert.match(uiSource, /evidenceStatus\.append\(element\("span", "sr-only", " " \+ statusExplanation\)\)/, "Evidence status should use sr-only text rather than a native title tooltip");

  const cssSource = fs.readFileSync(path.join(__dirname, "..", "styles.css"), "utf8");
  assert.match(cssSource, /\.sr-only\s*\{/, "Global styles should include a screen-reader-only utility class");
  assert.match(cssSource, /:focus-visible\s*\{/, "Global styles should include a focus-visible outline for keyboard accessibility");

  assert.match(uiSource, /FOUNDING_BETA_TESTER_KEY = "yartchives-founding-beta-tester-v1"/, "Founding beta tester status should use a dedicated local key");
  assert.match(uiSource, /Founding beta tester/, "Apply Next should expose the founding beta tester role");
  assert.match(uiSource, /awardFoundingBetaTester\(localStorage\)/, "Giving recommendation feedback should award founding beta tester status");
  assert.match(uiSource, /foundingBetaBadge\(\)/, "Apply Next queue heading should surface earned beta tester status");
  assert.match(applyNextCss, /\.apply-next-beta-badge\s*\{/, "Founding beta tester status should have dedicated badge styling");

  // Feedback tests
  assert.match(uiSource, /state\.feedback\[job\.id\] = \{ rating: "good" \}/, "Good feedback should be recorded in state");
  assert.match(uiSource, /state\.feedback\[job\.id\] = \{ rating: "bad" \}/, "Bad feedback should be recorded in state");
  assert.match(uiSource, /delete state\.feedback\[job\.id\]/, "Feedback should be reversible (Undo)");
  assert.match(uiSource, /state\.feedback\[job\.id\]\.reason = e\.target\.value/, "Feedback should support optional reasons for bad suggestions");
  assert.match(uiSource, /<option value="role">Role interest<\/option>/, "Optional reason should include Role interest");
  assert.match(uiSource, /<option value="location">Location<\/option>/, "Optional reason should include Location");
  assert.match(uiSource, /<option value="fit">Requirements\/Fit<\/option>/, "Optional reason should include Requirements/Fit");
  assert.match(uiSource, /<option value="company">Company\/Industry<\/option>/, "Optional reason should include Company/Industry");
  assert.match(uiSource, /<option value="other">Other<\/option>/, "Optional reason should include Other");
  assert.match(uiSource, /Anything else\? \(optional\)/, "Feedback should expose an optional written note");
  assert.match(uiSource, /What made this a good suggestion\?/, "Good feedback should support written context");
  assert.match(uiSource, /Tell us what was wrong with this suggestion\./, "Bad feedback should support written context");
  assert.match(uiSource, /state\.feedback\[job\.id\]\.note = value/, "Written feedback should persist with the recommendation");
  assert.match(uiSource, /delete state\.feedback\[job\.id\]\.note/, "Clearing written feedback should remove the stored note");
  assert.match(uiSource, /note\.maxLength = 500/, "Written feedback should have a bounded length");
  assert.match(applyNextCss, /\.apply-next-feedback-note-input\s*\{/, "Written feedback should have dedicated responsive styling");

  assert.doesNotMatch(uiSource, /<option value="newest">Newest<\/option>/, "Apply Next should not expose a Newest sort mode");
  assert.match(uiSource, /\["recommended", "Recommended"\]/, "Apply Next should expose the Recommended queue");
  assert.match(uiSource, /\["fresh", "Fresh"\]/, "Apply Next should expose a Fresh queue");
  assert.doesNotMatch(uiSource, /\["top", "Top 10"\]/, "Apply Next should not label a paginated queue Top 10");
  assert.match(uiSource, /Load 10 more/, "Apply Next queues should paginate ten recommendations at a time");
  assert.match(uiSource, /Ranked by overall Apply Next score, not posting time\./, "Fresh should preserve recommendation quality ordering");

  assert.match(uiSource, /document\.createDocumentFragment\(\)/, "renderQueue should build DOM off-screen before swapping to avoid UI stalls");
  assert.doesNotMatch(uiSource, /Kaamil|Badami|kaamil\.badami/i);

  const deployWorkflow = fs.readFileSync(path.join(__dirname, "..", ".github", "workflows", "deploy-pages.yml"), "utf8");
  assert.ok(deployWorkflow.includes("data/workday-inspections.json"), "Pages workflow must deploy Workday inspections");

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
