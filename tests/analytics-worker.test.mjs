import assert from "node:assert/strict";
import worker, {
  AI_PROFILE_DAILY_LIMIT,
  MAX_AI_BODY_BYTES,
  MAX_BODY_BYTES,
  RAW_RETENTION_DAYS,
  validateAiProfilePatch,
  validateAiProfileRequest,
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
  let aiCount = 0;
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
          if (/INSERT INTO ai_profile_usage/.test(sql)) aiCount += 1;
          return { success: true };
        },
        async first() {
          if (/SELECT request_count FROM ai_profile_usage/.test(sql)) {
            return { request_count: aiCount };
          }
          return null;
        },
      };
    },
  };
}

const base = validPayload();
assert.deepEqual(validatePayload(base), { ok: true });
assert.equal(MAX_BODY_BYTES, 64 * 1024);
assert.equal(MAX_AI_BODY_BYTES, 12 * 1024);
assert.equal(AI_PROFILE_DAILY_LIMIT, 20);
assert.equal(RAW_RETENTION_DAYS, 90);

assert.deepEqual(
  validateAiProfileRequest({ intent: "Sophomore CS student, Summer 2027", clientId: "ai-12345678" }),
  { ok: true }
);
assert.equal(validateAiProfileRequest({ intent: "x", clientId: "ai-12345678" }).ok, false);
assert.equal(validateAiProfileRequest({ intent: "valid intent", clientId: "bad" }).ok, false);

const checkedPatch = validateAiProfilePatch({
  targetTerm: "Summer 2027",
  studentStage: "Sophomore",
  graduation: null,
  degree: null,
  major: "Computer Science",
  careerAreaIds: ["cs"],
  roleFamilyIds: ["software", "analytics"],
  baseZips: ["20740"],
  preferredStates: ["MD", "DC"],
  nearbyMiles: 50,
  remoteRelevant: true,
  relocationAllowed: false,
  citizenship: null,
  workAuthorization: null,
  priorInternship: "none",
});
assert.equal(checkedPatch.ok, true);
assert.equal(checkedPatch.patch.major, "Computer Science");
assert.equal(
  validateAiProfilePatch({ ...checkedPatch.patch, resume: "forbidden" }).ok,
  false,
  "model output must not be able to inject resume/evidence fields"
);

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

const aiDb = fakeDb();
const azureResponse = {
  choices: [{
    message: {
      content: JSON.stringify({
        targetTerm: "Summer 2027",
        studentStage: "Sophomore",
        graduation: null,
        degree: null,
        major: "Computer Science",
        careerAreaIds: ["cs"],
        roleFamilyIds: ["software"],
        baseZips: ["20740"],
        preferredStates: ["MD"],
        nearbyMiles: 40,
        remoteRelevant: true,
        relocationAllowed: false,
        citizenship: null,
        workAuthorization: null,
        priorInternship: "none",
      }),
    },
  }],
};
const realFetch = globalThis.fetch;
let azureRequest = null;
globalThis.fetch = async (url, options) => {
  azureRequest = { url: String(url), options };
  return new Response(JSON.stringify(azureResponse), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
};
const aiEnv = {
  DB: aiDb,
  ALLOWED_ORIGIN: "https://kaamilbadami.github.io",
  AZURE_OPENAI_API_KEY: "secret",
  AZURE_OPENAI_ENDPOINT: "https://example.openai.azure.com/openai/v1",
  AZURE_OPENAI_DEPLOYMENT: "gpt-5-mini",
};
const aiAccepted = await worker.fetch(new Request("https://analytics.example.test/ai/profile", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Origin": "https://kaamilbadami.github.io",
  },
  body: JSON.stringify({
    intent: "I am a sophomore computer science student near College Park. ZIP 20740. I want Summer 2027 software internships within 40 miles, remote is okay, no relocation, and I have no prior internship.",
    clientId: "ai-client-12345678",
  }),
}), aiEnv);
globalThis.fetch = realFetch;
assert.equal(aiAccepted.status, 200);
const aiPayload = await aiAccepted.json();
assert.equal(aiPayload.ok, true);
assert.equal(aiPayload.patch.studentStage, "Sophomore");
assert.equal(aiPayload.patch.priorInternship, "none");
assert.equal(azureRequest.url, "https://example.openai.azure.com/openai/v1/chat/completions");
assert.equal(azureRequest.options.headers["api-key"], "secret");
assert.doesNotMatch(azureRequest.options.body, /resume|job feed|listing/i);

const aiBlocked = await worker.fetch(new Request("https://analytics.example.test/ai/profile", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Origin": "https://evil.example",
  },
  body: JSON.stringify({ intent: "Summer 2027 software", clientId: "ai-client-12345678" }),
}), aiEnv);
assert.equal(aiBlocked.status, 403);

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
