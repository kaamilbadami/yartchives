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

const source = require("node:fs").readFileSync(require("node:path").join(__dirname, "..", "analytics.js"), "utf8");
assert.doesNotMatch(source, /searchInput|locationInput|resume|profileToSave|jobId|company|title/);
assert.match(source, /keepalive:\s*true/);
assert.match(source, /schema:\s*SCHEMA/);
