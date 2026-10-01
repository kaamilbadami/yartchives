import assert from "node:assert/strict";
import worker, {
  MAX_BODY_BYTES,
  RAW_RETENTION_DAYS,
  validatePayload,
} from "../analytics/worker.mjs";

function validPayload() {
  return {
    schema: "yartchives-usage-v2",
    visitorId: "visitor-123abc",
    firstSeenDay: "2026-09-30",
    returningVisitor: false,
    sessionId: "session-456def",
    sequence: 1,
    startedAt: "2026-09-30T19:00:00.000Z",
    endedAt: "2026-09-30T19:00:10.000Z",
    build: "abcdef123456",
    events: {
      site_open: 1,
      apply_next_open: 1,
      recommendations_shown: 10,
      apply_clicked: 2,
    },
    timings: [{
      total_ms: 1200.5,
      stages_ms: { candidate_artifact: 300.2, ranking: 42.1 },
      counts: { candidates: 100, rankable: 50, geo_warm_state_at_await: "ready" },
      status: "success",
    }],
  };
}

function fakeDb() {
  const calls = [];
  return {
    calls,
    prepare(sql) {
      const call = { sql, binds: [], ran: false };
      calls.push(call);
      return {
        bind(...values) {
          call.binds = values;
          return this;
        },
        async run() {
          call.ran = true;
          return { success: true };
        },
      };
    },
  };
}

const base = validPayload();
assert.deepEqual(validatePayload(base), { ok: true });
assert.equal(MAX_BODY_BYTES, 64 * 1024);
assert.equal(RAW_RETENTION_DAYS, 90);

for (const forbidden of ["email", "profile", "resume", "search", "location", "jobId", "title", "company"]) {
  const payload = { ...base, [forbidden]: "should-not-pass" };
  assert.equal(validatePayload(payload).ok, false, `${forbidden} must be rejected`);
}

const unexpectedEvent = validPayload();
unexpectedEvent.events = { ...unexpectedEvent.events, job_opened: 1 };
assert.equal(validatePayload(unexpectedEvent).ok, false);

const badTiming = validPayload();
badTiming.timings[0].counts.exact_location = "College Park, MD";
assert.equal(validatePayload(badTiming).ok, false);

const db = fakeDb();
const env = { DB: db, ALLOWED_ORIGIN: "https://kaamilbadami.github.io" };
const request = new Request("https://analytics.example.test/collect", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Origin": "https://kaamilbadami.github.io",
  },
  body: JSON.stringify(validPayload()),
});
const accepted = await worker.fetch(request, env);
assert.equal(accepted.status, 202);
assert.equal(db.calls.length, 1);
assert.equal(db.calls[0].ran, true);
assert.match(db.calls[0].sql, /INSERT INTO usage_batches/);
assert.equal(db.calls[0].binds.includes("visitor-123abc"), true);
assert.equal(db.calls[0].binds.includes("session-456def"), true);
assert.equal(db.calls[0].binds.some(value => String(value).includes("College Park")), false);

const blocked = await worker.fetch(new Request("https://analytics.example.test/collect", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Origin": "https://evil.example",
  },
  body: JSON.stringify(validPayload()),
}), env);
assert.equal(blocked.status, 403);
assert.equal(db.calls.length, 1);

const health = await worker.fetch(new Request("https://analytics.example.test/health"), env);
assert.equal(health.status, 200);

const maintenanceDb = fakeDb();
let waited = null;
await worker.scheduled({}, { DB: maintenanceDb }, { waitUntil(promise) { waited = promise; } });
await waited;
assert.equal(maintenanceDb.calls.length, 2);
assert.match(maintenanceDb.calls[0].sql, /INSERT INTO daily_usage/);
assert.match(maintenanceDb.calls[1].sql, /DELETE FROM usage_batches/);
assert.deepEqual(maintenanceDb.calls[1].binds, ["-90 days"]);

console.log("analytics Worker tests passed");
