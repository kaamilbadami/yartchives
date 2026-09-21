const assert = require("node:assert/strict");

function loadFresh() {
  const path = require.resolve("../analytics.js");
  delete require.cache[path];
  return require(path);
}

const Analytics = loadFresh();

assert.equal(Analytics.track("saved"), true);
assert.equal(Analytics.track("unknown_event"), false);
assert.equal(Analytics.track("recommendations_shown", { count: 7 }), true);

const snapshot = Analytics.snapshot();
assert.equal(snapshot.events.saved, 1);
assert.equal(snapshot.events.recommendations_shown, 7);
assert.equal(snapshot.events.unknown_event, undefined);
assert.match(snapshot.sessionId, /.+/);

assert.ok(Analytics.ALLOWED_EVENTS.has("site_open"));
assert.ok(Analytics.ALLOWED_EVENTS.has("apply_next_open"));
assert.ok(Analytics.ALLOWED_EVENTS.has("profile_created"));
assert.ok(Analytics.ALLOWED_EVENTS.has("recommendations_shown"));
assert.ok(Analytics.ALLOWED_EVENTS.has("apply_clicked"));
assert.ok(Analytics.ALLOWED_EVENTS.has("saved"));
assert.ok(Analytics.ALLOWED_EVENTS.has("hidden"));
assert.ok(Analytics.ALLOWED_EVENTS.has("feedback_submitted"));
assert.ok(Analytics.ALLOWED_EVENTS.has("apply_next_timing"));

// Test timing payload sanitization and allowlisting
const dirtyPayload = {
  total_ms: 125.4,
  stages_ms: {
    paint_wait: 2.1,
    candidate_filter: 10.5,
    inspection_artifact: 50.2,
    disallowed_stage: 999,
  },
  counts: {
    candidates: 100,
    rankable: 50,
    recommendations: 10,
    disallowed_count: 500,
  },
  status: "success",
  jobId: "12345",
  company: "Forbidden Co",
  title: "Forbidden Title",
  profile: { name: "John Doe" },
};

const sanitized = Analytics.sanitizeTimingPayload(dirtyPayload);
assert.equal(sanitized.total_ms, 125.4);
assert.equal(sanitized.stages_ms.paint_wait, 2.1);
assert.equal(sanitized.stages_ms.candidate_filter, 10.5);
assert.equal(sanitized.stages_ms.inspection_artifact, 50.2);
assert.equal(sanitized.stages_ms.disallowed_stage, undefined);
assert.equal(sanitized.counts.candidates, 100);
assert.equal(sanitized.counts.disallowed_count, undefined);
assert.equal(sanitized.jobId, undefined);
assert.equal(sanitized.company, undefined);
assert.equal(sanitized.title, undefined);
assert.equal(sanitized.profile, undefined);

assert.equal(Analytics.track("apply_next_timing", dirtyPayload), true);

const source = require("node:fs").readFileSync(require("node:path").join(__dirname, "..", "analytics.js"), "utf8");
assert.doesNotMatch(source, /searchInput|locationInput|resume|profileToSave|jobId|company|title/);
assert.match(source, /keepalive:\s*true/);
assert.match(source, /schema:\s*SCHEMA/);
