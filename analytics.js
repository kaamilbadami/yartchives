(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.YartchivesAnalytics = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  const ENDPOINT = "https://formspree.io/f/mqakpejw";
  const SCHEMA = "yartchives-usage-v2";
  const VISITOR_ID_KEY = "yartchives.analytics.visitor.v1";
  const FIRST_SEEN_KEY = "yartchives.analytics.firstSeen.v1";
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
    "paint_wait",
    "candidate_artifact",
    "candidate_filter",
    "inspection_artifact",
    "inspection_attach",
    "location_enrichment",
    "ranking",
    "render",
  ]);

  const ALLOWED_COUNTS = new Set([
    "candidates",
    "rankable",
    "recommendations",
  ]);

  const counts = Object.create(null);
  let pendingTimings = [];
  let sequence = 0;
  let startedAt = new Date().toISOString();
  let flushing = null;

  function sanitizeTimingPayload(properties) {
    if (!properties || typeof properties !== "object") return null;

    const total_ms = Number(properties.total_ms);
    if (!Number.isFinite(total_ms) || total_ms < 0) return null;

    const stages_ms = {};
    if (properties.stages_ms && typeof properties.stages_ms === "object") {
      for (const [key, val] of Object.entries(properties.stages_ms)) {
        if (ALLOWED_STAGES.has(key)) {
          const num = Number(val);
          if (Number.isFinite(num) && num >= 0) {
            stages_ms[key] = Math.round(num * 10) / 10;
          }
        }
      }
    }

    const counts = {};
    if (properties.counts && typeof properties.counts === "object") {
      for (const [key, val] of Object.entries(properties.counts)) {
        if (ALLOWED_COUNTS.has(key)) {
          const num = Number(val);
          if (Number.isFinite(num) && num >= 0) {
            counts[key] = Math.floor(num);
          }
        }
      }
    }

    const rawStatus = String(properties.status || "success").slice(0, 20);
    const status = /^[a-z0-9_-]+$/i.test(rawStatus) ? rawStatus : "unknown";

    return {
      total_ms: Math.round(total_ms * 10) / 10,
      stages_ms,
      counts,
      status,
    };
  }

  function randomId(prefix) {
    try {
      if (root.crypto?.randomUUID) return `${prefix}-${root.crypto.randomUUID()}`;
    } catch (_) {}
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  }

  function randomSessionId() {
    return randomId("session");
  }

  function currentDay() {
    return new Date().toISOString().slice(0, 10);
  }

  function loadVisitorState() {
    const fallback = {
      visitorId: randomId("visitor"),
      firstSeenDay: currentDay(),
      isReturning: false,
      persistent: false,
    };

    let storage;
    try {
      storage = root.localStorage;
    } catch (_) {
      return fallback;
    }
    if (!storage?.getItem || !storage?.setItem) return fallback;

    try {
      const existingId = storage.getItem(VISITOR_ID_KEY);
      const existingFirstSeen = storage.getItem(FIRST_SEEN_KEY);
      if (existingId) {
        return {
          visitorId: existingId.slice(0, 100),
          firstSeenDay: /^\d{4}-\d{2}-\d{2}$/.test(existingFirstSeen || "")
            ? existingFirstSeen
            : currentDay(),
          isReturning: true,
          persistent: true,
        };
      }

      storage.setItem(VISITOR_ID_KEY, fallback.visitorId);
      storage.setItem(FIRST_SEEN_KEY, fallback.firstSeenDay);
      return { ...fallback, persistent: true };
    } catch (_) {
      return fallback;
    }
  }

  const sessionId = randomSessionId();
  const visitor = loadVisitorState();

  function normalizedIncrement(event, properties) {
    if (event === "recommendations_shown") {
      const count = Number(properties?.count);
      if (Number.isFinite(count) && count > 0) return Math.min(100, Math.floor(count));
    }
    return 1;
  }

  function track(event, properties = {}) {
    if (!ALLOWED_EVENTS.has(event)) return false;
    if (event === "apply_next_timing") {
      const sanitized = sanitizeTimingPayload(properties);
      if (!sanitized) return false;
      pendingTimings.push(sanitized);
      if (pendingTimings.length > 20) pendingTimings.shift();
    }
    counts[event] = (counts[event] || 0) + normalizedIncrement(event, properties);
    return true;
  }

  function pendingCounts() {
    return Object.fromEntries(
      Object.entries(counts).filter(([, value]) => Number(value) > 0)
    );
  }

  function clearCounts(snapshot) {
    for (const [event, value] of Object.entries(snapshot)) {
      counts[event] = Math.max(0, (counts[event] || 0) - value);
    }
  }

  function mergeCounts(snapshot) {
    for (const [event, value] of Object.entries(snapshot)) {
      counts[event] = (counts[event] || 0) + value;
    }
  }

  function buildPayload(snapshot) {
    const build = root.document
      ?.querySelector('meta[name="yartchives-build"]')
      ?.getAttribute("content") || "";
    const payload = {
      schema: SCHEMA,
      visitorId: visitor.visitorId,
      firstSeenDay: visitor.firstSeenDay,
      returningVisitor: visitor.isReturning,
      sessionId,
      sequence: ++sequence,
      startedAt,
      endedAt: new Date().toISOString(),
      build: build.startsWith("__") ? "" : build.slice(0, 40),
      events: snapshot,
    };
    if (pendingTimings.length) {
      payload.timings = pendingTimings.slice();
    }
    return payload;
  }

  async function flush() {
    if (flushing) return flushing;
    const snapshot = pendingCounts();
    if (!Object.keys(snapshot).length) return true;
    clearCounts(snapshot);
    const payload = buildPayload(snapshot);

    const timingsSnapshot = payload.timings ? payload.timings.slice() : [];
    if (payload.timings) {
      pendingTimings = pendingTimings.slice(payload.timings.length);
    }

    flushing = (async () => {
      try {
        const response = await root.fetch(ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify(payload),
          keepalive: true,
        });
        if (!response.ok) throw new Error("Analytics submission failed");
        return true;
      } catch (_) {
        mergeCounts(snapshot);
        if (timingsSnapshot.length) {
          pendingTimings = [...timingsSnapshot, ...pendingTimings].slice(0, 20);
        }
        return false;
      } finally {
        flushing = null;
      }
    })();
    return flushing;
  }

  function snapshot() {
    return {
      visitorId: visitor.visitorId,
      firstSeenDay: visitor.firstSeenDay,
      returningVisitor: visitor.isReturning,
      persistentVisitor: visitor.persistent,
      sessionId,
      sequence,
      events: pendingCounts(),
    };
  }

  function init() {
    if (!root.document || !root.addEventListener) return;
    track("site_open");
    root.addEventListener("pagehide", () => { void flush(); });
    root.document.addEventListener("visibilitychange", () => {
      if (root.document.visibilityState === "hidden") void flush();
    });
  }

  init();

  return {
    ENDPOINT,
    SCHEMA,
    ALLOWED_EVENTS,
    ALLOWED_STAGES,
    sanitizeTimingPayload,
    loadVisitorState,
    track,
    flush,
    snapshot,
  };
});
