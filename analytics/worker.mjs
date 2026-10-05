const SCHEMA = "yartchives-usage-v2";
const MAX_BODY_BYTES = 64 * 1024;
const MAX_AI_BODY_BYTES = 12 * 1024;
const AI_PROFILE_DAILY_LIMIT = 20;
const RAW_RETENTION_DAYS = 90;

const CAREER_AREA_IDS = new Set(["cs", "engineering", "finance-econ"]);
const ROLE_FAMILY_IDS = new Set([
  "software", "testing-systems", "analytics", "infrastructure", "ai-ml",
  "cybersecurity", "hpc", "mechanical-manufacturing", "electrical-hardware",
  "aerospace", "engineering-systems", "robotics-controls", "civil-structural",
  "product-design-test", "business-operations", "technology-business", "finance-broad",
]);
const STUDENT_STAGES = new Set(["Freshman", "Sophomore", "Junior", "Senior", "Graduate"]);
const CITIZENSHIP_VALUES = new Set(["U.S. citizen", "Not a U.S. citizen"]);
const WORK_AUTH_VALUES = new Set([
  "Authorized to work in the U.S. without sponsorship",
  "Needs visa sponsorship",
]);
const PRIOR_INTERNSHIP_VALUES = new Set(["none", "has_prior", "unknown"]);

const ALLOWED_EVENTS = new Set([
  "site_open",
  "apply_next_open",
  "profile_created",
  "recommendations_shown",
  "apply_clicked",
  "saved",
  "hidden",
  "feedback_submitted",
  "apply_next_timing",
]);

const ALLOWED_STAGES = new Set([
  "queue_setup",
  "paint_wait",
  "candidate_artifact",
  "candidate_filter",
  "inspection_artifact",
  "inspection_attach",
  "preliminary_ranking",
  "location_enrichment",
  "ranking",
  "render",
  "post_render_paint_wait",
]);

const ALLOWED_COUNTS = new Set([
  "candidates",
  "rankable",
  "recommendations",
  "inspection_await_ms",
  "inspection_normalization_ms",
  "geo_await_ms",
  "inspection_request_ms",
  "inspection_headers_ms",
  "inspection_body_parse_ms",
  "inspection_preload_age_ms",
  "preliminary_ranking_ms",
  "distance_selection_ms",
  "geo_enrichment_ms",
  "distance_candidates",
  "distance_unique_lookups",
  "distance_cache_hits",
  "distance_lookup_failures",
  "location_parse_ms",
  "location_compute_ms",
  "location_yield_ms",
  "location_yield_count",
  "location_order_ms",
]);

const ALLOWED_STATES = new Set([
  "inspection_promise_state_at_await",
  "geo_warm_state_at_await",
]);

function jsonResponse(status, body, origin = "") {
  const headers = new Headers({
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  if (origin) {
    headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Vary", "Origin");
  }
  return new Response(JSON.stringify(body), { status, headers });
}

function allowedOrigin(request, env) {
  const configured = String(env.ALLOWED_ORIGIN || "").trim();
  const incoming = String(request.headers.get("Origin") || "").trim();
  return configured && incoming === configured ? configured : "";
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function onlyKeys(value, allowed) {
  return Object.keys(value).every(key => allowed.has(key));
}

function finiteNonNegative(value) {
  return Number.isFinite(value) && value >= 0;
}

function validIdentifier(value, prefix) {
  return typeof value === "string"
    && value.startsWith(prefix)
    && value.length <= 100
    && /^[a-z0-9-]+$/i.test(value);
}

function validIsoDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function validTimestamp(value) {
  if (typeof value !== "string" || value.length > 40) return false;
  return Number.isFinite(Date.parse(value));
}

function validateTiming(timing) {
  if (!isObject(timing)) return false;
  const allowed = new Set(["total_ms", "stages_ms", "counts", "status"]);
  if (!onlyKeys(timing, allowed)) return false;
  if (!finiteNonNegative(timing.total_ms)) return false;
  if (String(timing.status || "").length > 20 || !/^[a-z0-9_-]+$/i.test(String(timing.status || ""))) return false;

  if (!isObject(timing.stages_ms) || !onlyKeys(timing.stages_ms, ALLOWED_STAGES)) return false;
  for (const value of Object.values(timing.stages_ms)) {
    if (!finiteNonNegative(value)) return false;
  }

  if (!isObject(timing.counts)) return false;
  for (const [key, value] of Object.entries(timing.counts)) {
    if (ALLOWED_COUNTS.has(key)) {
      if (!finiteNonNegative(value)) return false;
    } else if (ALLOWED_STATES.has(key)) {
      if (typeof value !== "string" || value.length > 20 || !/^[a-z0-9_-]+$/i.test(value)) return false;
    } else {
      return false;
    }
  }
  return true;
}

export function validatePayload(payload) {
  if (!isObject(payload)) return { ok: false, error: "payload_not_object" };
  const allowedKeys = new Set([
    "schema",
    "visitorId",
    "firstSeenDay",
    "returningVisitor",
    "sessionId",
    "sequence",
    "startedAt",
    "endedAt",
    "build",
    "events",
    "timings",
  ]);
  if (!onlyKeys(payload, allowedKeys)) return { ok: false, error: "unexpected_field" };
  if (payload.schema !== SCHEMA) return { ok: false, error: "unsupported_schema" };
  if (!validIdentifier(payload.visitorId, "visitor-")) return { ok: false, error: "invalid_visitor" };
  if (!validIdentifier(payload.sessionId, "session-")) return { ok: false, error: "invalid_session" };
  if (!validIsoDate(payload.firstSeenDay)) return { ok: false, error: "invalid_first_seen_day" };
  if (typeof payload.returningVisitor !== "boolean") return { ok: false, error: "invalid_returning_visitor" };
  if (!Number.isInteger(payload.sequence) || payload.sequence < 1 || payload.sequence > 1_000_000) {
    return { ok: false, error: "invalid_sequence" };
  }
  if (!validTimestamp(payload.startedAt) || !validTimestamp(payload.endedAt)) return { ok: false, error: "invalid_timestamp" };
  if (Date.parse(payload.endedAt) < Date.parse(payload.startedAt)) return { ok: false, error: "invalid_time_order" };
  if (typeof payload.build !== "string" || payload.build.length > 40 || !/^[a-f0-9]*$/i.test(payload.build)) {
    return { ok: false, error: "invalid_build" };
  }

  if (!isObject(payload.events) || !onlyKeys(payload.events, ALLOWED_EVENTS)) return { ok: false, error: "invalid_events" };
  if (Object.keys(payload.events).length === 0) return { ok: false, error: "empty_events" };
  for (const value of Object.values(payload.events)) {
    if (!Number.isInteger(value) || value < 0 || value > 1_000_000) return { ok: false, error: "invalid_event_count" };
  }

  if (payload.timings !== undefined) {
    if (!Array.isArray(payload.timings) || payload.timings.length > 20 || !payload.timings.every(validateTiming)) {
      return { ok: false, error: "invalid_timings" };
    }
  }

  return { ok: true };
}

function eventCount(payload, key) {
  return Number(payload.events?.[key] || 0);
}

async function persistBatch(env, payload) {
  const statement = env.DB.prepare(`
    INSERT INTO usage_batches (
      schema_version, visitor_id, session_id, first_seen_day, returning_visitor,
      sequence, started_at, ended_at, build_sha, site_open, apply_next_open,
      profile_created, recommendations_shown, apply_clicked, saved, hidden,
      feedback_submitted, apply_next_timing, timings_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  await statement.bind(
    payload.schema,
    payload.visitorId,
    payload.sessionId,
    payload.firstSeenDay,
    payload.returningVisitor ? 1 : 0,
    payload.sequence,
    payload.startedAt,
    payload.endedAt,
    payload.build,
    eventCount(payload, "site_open"),
    eventCount(payload, "apply_next_open"),
    eventCount(payload, "profile_created"),
    eventCount(payload, "recommendations_shown"),
    eventCount(payload, "apply_clicked"),
    eventCount(payload, "saved"),
    eventCount(payload, "hidden"),
    eventCount(payload, "feedback_submitted"),
    eventCount(payload, "apply_next_timing"),
    JSON.stringify(payload.timings || [])
  ).run();
}

async function handleCollect(request, env) {
  const origin = allowedOrigin(request, env);
  if (!origin) return jsonResponse(403, { ok: false, error: "origin_not_allowed" });

  const contentType = String(request.headers.get("Content-Type") || "").toLowerCase();
  if (!contentType.startsWith("application/json")) return jsonResponse(415, { ok: false, error: "json_required" }, origin);

  const declaredLength = Number(request.headers.get("Content-Length") || 0);
  if (declaredLength > MAX_BODY_BYTES) return jsonResponse(413, { ok: false, error: "payload_too_large" }, origin);

  const body = await request.text();
  if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
    return jsonResponse(413, { ok: false, error: "payload_too_large" }, origin);
  }

  let payload;
  try {
    payload = JSON.parse(body);
  } catch (_) {
    return jsonResponse(400, { ok: false, error: "invalid_json" }, origin);
  }

  const checked = validatePayload(payload);
  if (!checked.ok) return jsonResponse(400, checked, origin);

  try {
    await persistBatch(env, payload);
  } catch (_) {
    return jsonResponse(503, { ok: false, error: "storage_unavailable" }, origin);
  }
  return jsonResponse(202, { ok: true }, origin);
}


function validAiClientId(value) {
  return typeof value === "string"
    && /^ai-[a-z0-9-]{8,80}$/i.test(value);
}

function validateAiProfileRequest(payload) {
  if (!isObject(payload)) return { ok: false, error: "payload_not_object" };
  if (!onlyKeys(payload, new Set(["intent", "clientId"]))) return { ok: false, error: "unexpected_field" };
  if (typeof payload.intent !== "string" || payload.intent.trim().length < 4 || payload.intent.length > 4000) {
    return { ok: false, error: "invalid_intent" };
  }
  if (!validAiClientId(payload.clientId)) return { ok: false, error: "invalid_client" };
  return { ok: true };
}

function cleanString(value, max = 120) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string") return null;
  const cleaned = value.replace(/\s+/g, " ").trim();
  return cleaned && cleaned.length <= max ? cleaned : null;
}

function validateAiProfilePatch(value) {
  if (!isObject(value)) return { ok: false, error: "model_output_not_object" };
  const allowed = new Set([
    "targetTerm", "studentStage", "graduation", "degree", "major",
    "careerAreaIds", "roleFamilyIds", "baseZips", "preferredStates",
    "nearbyMiles", "remoteRelevant", "relocationAllowed", "citizenship",
    "workAuthorization", "priorInternship",
  ]);
  if (!onlyKeys(value, allowed)) return { ok: false, error: "model_output_unexpected_field" };

  const patch = {};
  for (const key of ["targetTerm", "graduation", "degree", "major"]) {
    const cleaned = cleanString(value[key]);
    if (cleaned) patch[key] = cleaned;
  }
  if (value.studentStage !== null && value.studentStage !== undefined) {
    if (!STUDENT_STAGES.has(value.studentStage)) return { ok: false, error: "model_output_invalid_stage" };
    patch.studentStage = value.studentStage;
  }
  if (value.citizenship !== null && value.citizenship !== undefined) {
    if (!CITIZENSHIP_VALUES.has(value.citizenship)) return { ok: false, error: "model_output_invalid_citizenship" };
    patch.citizenship = value.citizenship;
  }
  if (value.workAuthorization !== null && value.workAuthorization !== undefined) {
    if (!WORK_AUTH_VALUES.has(value.workAuthorization)) return { ok: false, error: "model_output_invalid_authorization" };
    patch.workAuthorization = value.workAuthorization;
  }
  if (value.priorInternship !== null && value.priorInternship !== undefined) {
    if (!PRIOR_INTERNSHIP_VALUES.has(value.priorInternship)) return { ok: false, error: "model_output_invalid_prior_internship" };
    patch.priorInternship = value.priorInternship;
  }

  if (value.careerAreaIds !== undefined) {
    if (!Array.isArray(value.careerAreaIds) || value.careerAreaIds.some(item => !CAREER_AREA_IDS.has(item))) {
      return { ok: false, error: "model_output_invalid_career_areas" };
    }
    if (value.careerAreaIds.length) patch.careerAreaIds = [...new Set(value.careerAreaIds)].slice(0, 3);
  }
  if (value.roleFamilyIds !== undefined) {
    if (!Array.isArray(value.roleFamilyIds) || value.roleFamilyIds.some(item => !ROLE_FAMILY_IDS.has(item))) {
      return { ok: false, error: "model_output_invalid_role_families" };
    }
    if (value.roleFamilyIds.length) patch.roleFamilyIds = [...new Set(value.roleFamilyIds)].slice(0, 12);
  }
  if (value.baseZips !== undefined) {
    if (!Array.isArray(value.baseZips) || value.baseZips.some(item => typeof item !== "string" || !/^\d{5}$/.test(item))) {
      return { ok: false, error: "model_output_invalid_zips" };
    }
    if (value.baseZips.length) patch.baseZips = [...new Set(value.baseZips)].slice(0, 4);
  }
  if (value.preferredStates !== undefined) {
    if (!Array.isArray(value.preferredStates) || value.preferredStates.some(item => typeof item !== "string" || !/^[A-Z]{2}$/.test(item))) {
      return { ok: false, error: "model_output_invalid_states" };
    }
    if (value.preferredStates.length) patch.preferredStates = [...new Set(value.preferredStates)].slice(0, 12);
  }
  if (value.nearbyMiles !== null && value.nearbyMiles !== undefined) {
    if (!Number.isFinite(value.nearbyMiles) || value.nearbyMiles < 5 || value.nearbyMiles > 500) {
      return { ok: false, error: "model_output_invalid_nearby_miles" };
    }
    patch.nearbyMiles = Math.round(value.nearbyMiles);
  }
  for (const key of ["remoteRelevant", "relocationAllowed"]) {
    if (value[key] !== null && value[key] !== undefined) {
      if (typeof value[key] !== "boolean") return { ok: false, error: `model_output_invalid_${key}` };
      patch[key] = value[key];
    }
  }
  return { ok: true, patch };
}

const AI_PROFILE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    targetTerm: { type: ["string", "null"] },
    studentStage: { type: ["string", "null"], enum: ["Freshman", "Sophomore", "Junior", "Senior", "Graduate", null] },
    graduation: { type: ["string", "null"] },
    degree: { type: ["string", "null"] },
    major: { type: ["string", "null"] },
    careerAreaIds: { type: "array", items: { type: "string", enum: [...CAREER_AREA_IDS] }, maxItems: 3 },
    roleFamilyIds: { type: "array", items: { type: "string", enum: [...ROLE_FAMILY_IDS] }, maxItems: 12 },
    baseZips: { type: "array", items: { type: "string", pattern: "^\\d{5}$" }, maxItems: 4 },
    preferredStates: { type: "array", items: { type: "string", pattern: "^[A-Z]{2}$" }, maxItems: 12 },
    nearbyMiles: { type: ["number", "null"], minimum: 5, maximum: 500 },
    remoteRelevant: { type: ["boolean", "null"] },
    relocationAllowed: { type: ["boolean", "null"] },
    citizenship: { type: ["string", "null"], enum: ["U.S. citizen", "Not a U.S. citizen", null] },
    workAuthorization: { type: ["string", "null"], enum: ["Authorized to work in the U.S. without sponsorship", "Needs visa sponsorship", null] },
    priorInternship: { type: ["string", "null"], enum: ["none", "has_prior", "unknown", null] },
  },
  required: [
    "targetTerm", "studentStage", "graduation", "degree", "major",
    "careerAreaIds", "roleFamilyIds", "baseZips", "preferredStates",
    "nearbyMiles", "remoteRelevant", "relocationAllowed", "citizenship",
    "workAuthorization", "priorInternship",
  ],
};

async function consumeAiQuota(env, clientId) {
  if (!env.DB) return { ok: false, error: "storage_unavailable" };
  const day = new Date().toISOString().slice(0, 10);
  await env.DB.prepare(`
    INSERT INTO ai_profile_usage (usage_date, client_id, request_count)
    VALUES (?, ?, 1)
    ON CONFLICT(usage_date, client_id)
    DO UPDATE SET request_count = request_count + 1
  `).bind(day, clientId).run();
  const row = await env.DB.prepare(
    "SELECT request_count FROM ai_profile_usage WHERE usage_date = ? AND client_id = ?"
  ).bind(day, clientId).first();
  const count = Number(row?.request_count || 0);
  return count <= AI_PROFILE_DAILY_LIMIT
    ? { ok: true, remaining: Math.max(0, AI_PROFILE_DAILY_LIMIT - count) }
    : { ok: false, error: "daily_limit_reached", remaining: 0 };
}

async function callAzureProfileParser(env, intent) {
  const apiKey = String(env.AZURE_OPENAI_API_KEY || "").trim();
  const endpoint = String(env.AZURE_OPENAI_ENDPOINT || "").trim().replace(/\/+$/, "");
  const deployment = String(env.AZURE_OPENAI_DEPLOYMENT || "").trim();
  if (!apiKey || !endpoint || !deployment) throw new Error("ai_unavailable");

  let parsedEndpoint;
  try { parsedEndpoint = new URL(endpoint); } catch (_) { throw new Error("ai_unavailable"); }
  if (parsedEndpoint.protocol !== "https:" || parsedEndpoint.username || parsedEndpoint.password) {
    throw new Error("ai_unavailable");
  }

  const instruction = [
    "Convert a student's internship-search intent into a bounded Yartchives profile patch.",
    "Only include facts/preferences explicitly stated by the user.",
    "Do not infer citizenship, work authorization, ZIP code, graduation date, prior internship history, or relocation preference.",
    "Use empty arrays/null for unspecified fields.",
    "Career area IDs: cs, engineering, finance-econ.",
    "Role family IDs must come from the provided schema.",
    "Do not include skills, coursework, projects, work evidence, leadership evidence, ranking scores, eligibility decisions, or job data.",
  ].join(" ");

  const response = await fetch(`${parsedEndpoint.origin}/openai/v1/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "api-key": apiKey },
    body: JSON.stringify({
      model: deployment,
      messages: [
        { role: "system", content: instruction },
        { role: "user", content: intent.trim() },
      ],
      response_format: {
        type: "json_schema",
        json_schema: { name: "yartchives_user_profile_patch", strict: true, schema: AI_PROFILE_SCHEMA },
      },
    }),
  });
  if (!response.ok) throw new Error(response.status === 429 ? "ai_quota_unavailable" : "ai_provider_error");
  const body = await response.json();
  const content = body?.choices?.[0]?.message?.content;
  if (typeof content !== "string") throw new Error("ai_invalid_response");
  let decoded;
  try { decoded = JSON.parse(content); } catch (_) { throw new Error("ai_invalid_response"); }
  const checked = validateAiProfilePatch(decoded);
  if (!checked.ok) throw new Error(checked.error);
  return checked.patch;
}

async function handleAiProfile(request, env) {
  const origin = allowedOrigin(request, env);
  if (!origin) return jsonResponse(403, { ok: false, error: "origin_not_allowed" });
  const contentType = String(request.headers.get("Content-Type") || "").toLowerCase();
  if (!contentType.startsWith("application/json")) return jsonResponse(415, { ok: false, error: "json_required" }, origin);

  const declaredLength = Number(request.headers.get("Content-Length") || 0);
  if (declaredLength > MAX_AI_BODY_BYTES) return jsonResponse(413, { ok: false, error: "payload_too_large" }, origin);
  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_AI_BODY_BYTES) {
    return jsonResponse(413, { ok: false, error: "payload_too_large" }, origin);
  }

  let payload;
  try { payload = JSON.parse(raw); } catch (_) { return jsonResponse(400, { ok: false, error: "invalid_json" }, origin); }
  const checked = validateAiProfileRequest(payload);
  if (!checked.ok) return jsonResponse(400, checked, origin);

  let quota;
  try { quota = await consumeAiQuota(env, payload.clientId); }
  catch (_) { return jsonResponse(503, { ok: false, error: "storage_unavailable" }, origin); }
  if (!quota.ok) return jsonResponse(429, { ok: false, error: quota.error, remaining: 0 }, origin);

  try {
    const patch = await callAzureProfileParser(env, payload.intent);
    return jsonResponse(200, { ok: true, patch, remaining: quota.remaining }, origin);
  } catch (error) {
    const code = String(error?.message || "ai_unavailable");
    const status = code === "ai_quota_unavailable" ? 429 : 503;
    return jsonResponse(status, { ok: false, error: code }, origin);
  }
}

async function runDailyMaintenance(env) {
  const rollup = env.DB.prepare(`
    INSERT INTO daily_usage (
      usage_date, unique_visitors, returning_visitors, sessions, apply_next_sessions,
      recommendations_shown, apply_clicked, saved, hidden, feedback_submitted
    )
    SELECT
      date(received_at),
      COUNT(DISTINCT visitor_id),
      COUNT(DISTINCT CASE WHEN returning_visitor = 1 THEN visitor_id END),
      COUNT(DISTINCT session_id),
      COUNT(DISTINCT CASE WHEN apply_next_open > 0 THEN session_id END),
      COALESCE(SUM(recommendations_shown), 0),
      COALESCE(SUM(apply_clicked), 0),
      COALESCE(SUM(saved), 0),
      COALESCE(SUM(hidden), 0),
      COALESCE(SUM(feedback_submitted), 0)
    FROM usage_batches
    WHERE date(received_at) = date('now', '-1 day')
    GROUP BY date(received_at)
    ON CONFLICT(usage_date) DO UPDATE SET
      unique_visitors = excluded.unique_visitors,
      returning_visitors = excluded.returning_visitors,
      sessions = excluded.sessions,
      apply_next_sessions = excluded.apply_next_sessions,
      recommendations_shown = excluded.recommendations_shown,
      apply_clicked = excluded.apply_clicked,
      saved = excluded.saved,
      hidden = excluded.hidden,
      feedback_submitted = excluded.feedback_submitted
  `);
  await rollup.run();

  const retention = env.DB.prepare("DELETE FROM usage_batches WHERE received_at < datetime('now', ?)");
  await retention.bind(`-${RAW_RETENTION_DAYS} days`).run();
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") return jsonResponse(200, { ok: true, schema: SCHEMA });
    if (!["/collect", "/ai/profile"].includes(url.pathname)) return jsonResponse(404, { ok: false, error: "not_found" });

    const origin = allowedOrigin(request, env);
    if (request.method === "OPTIONS") {
      if (!origin) return jsonResponse(403, { ok: false, error: "origin_not_allowed" });
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": origin,
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "86400",
          "Vary": "Origin",
        },
      });
    }

    if (request.method !== "POST") {
      const response = jsonResponse(405, { ok: false, error: "method_not_allowed" }, origin);
      response.headers.set("Allow", "POST, OPTIONS");
      return response;
    }
    return url.pathname === "/ai/profile"
      ? handleAiProfile(request, env)
      : handleCollect(request, env);
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(runDailyMaintenance(env));
  },
};

export {
  ALLOWED_EVENTS,
  AI_PROFILE_DAILY_LIMIT,
  MAX_AI_BODY_BYTES,
  MAX_BODY_BYTES,
  RAW_RETENTION_DAYS,
  callAzureProfileParser,
  runDailyMaintenance,
  validateAiProfilePatch,
  validateAiProfileRequest,
};
