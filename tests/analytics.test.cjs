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
assert.match(snapshot.sessionId, /^session-/);
assert.match(snapshot.visitorId, /^visitor-/);
assert.equal(snapshot.returningVisitor, false);
assert.equal(snapshot.persistentVisitor, false);
assert.match(snapshot.firstSeenDay, /^\d{4}-\d{2}-\d{2}$/);

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
assert.match(source, /visitorId:\s*visitor\.visitorId/);
assert.match(source, /returningVisitor:\s*visitor\.isReturning/);
assert.match(source, /localStorage/);
assert.doesNotMatch(source, /email|userName|fullName|ipAddress/i);

// A persisted random visitor ID is reused without collecting identity fields.
const originalStorage = globalThis.localStorage;
const store = new Map();
globalThis.localStorage = {
  getItem(key) { return store.has(key) ? store.get(key) : null; },
  setItem(key, value) { store.set(key, String(value)); },
};
try {
  const firstLoad = loadFresh();
  const first = firstLoad.snapshot();
  assert.equal(first.returningVisitor, false);
  assert.equal(first.persistentVisitor, true);

  const secondLoad = loadFresh();
  const second = secondLoad.snapshot();
  assert.equal(second.visitorId, first.visitorId);
  assert.equal(second.firstSeenDay, first.firstSeenDay);
  assert.equal(second.returningVisitor, true);
  assert.equal(second.persistentVisitor, true);
  assert.notEqual(second.sessionId, first.sessionId);
} finally {
  if (originalStorage === undefined) delete globalThis.localStorage;
  else globalThis.localStorage = originalStorage;
}
