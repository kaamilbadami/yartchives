(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.YartchivesAnalytics = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  const ENDPOINT = "https://formspree.io/f/mqakpejw";
  const SCHEMA = "yartchives-usage-v1";
  const ALLOWED_EVENTS = new Set([
    "site_open",
    "apply_next_open",
    "profile_created",
    "recommendations_shown",
    "apply_clicked",
    "saved",
    "hidden",
    "feedback_submitted",
  ]);

  const counts = Object.create(null);
  let sequence = 0;
  let startedAt = new Date().toISOString();
  let flushing = null;

  function randomSessionId() {
    try {
      if (root.crypto?.randomUUID) return root.crypto.randomUUID();
    } catch (_) {}
    return `session-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  }

  const sessionId = randomSessionId();

  function normalizedIncrement(event, properties) {
    if (event === "recommendations_shown") {
      const count = Number(properties?.count);
      if (Number.isFinite(count) && count > 0) return Math.min(100, Math.floor(count));
    }
    return 1;
  }

  function track(event, properties = {}) {
    if (!ALLOWED_EVENTS.has(event)) return false;
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
    return {
      schema: SCHEMA,
      sessionId,
      sequence: ++sequence,
      startedAt,
      endedAt: new Date().toISOString(),
      build: build.startsWith("__") ? "" : build.slice(0, 40),
      events: snapshot,
    };
  }

  async function flush() {
    if (flushing) return flushing;
    const snapshot = pendingCounts();
    if (!Object.keys(snapshot).length) return true;
    clearCounts(snapshot);
    const payload = buildPayload(snapshot);

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
        return false;
      } finally {
        flushing = null;
      }
    })();
    return flushing;
  }

  function snapshot() {
    return {
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
    track,
    flush,
    snapshot,
  };
});
