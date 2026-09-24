(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesApplyNextUI = api;
    if (typeof document !== "undefined") api.init();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const STORAGE_KEY = "yartchives-apply-next-profile-v1";
  const FOUNDING_BETA_TESTER_KEY = "yartchives-founding-beta-tester-v1";
  const ENTRY_MODE_KEY = "yartchives-entry-mode-v1";
  const INSPECTION_URL = "data/apply-next-inspections.json";
  const CANDIDATE_URL = "data/apply-next-candidates.json";
  const TOP_N = 10;
  const FRESH_MAX_AGE_DAYS = 3;
  const FRESH_MIN_SCORE = 55;
  const LOCATION_DISTANCE_MAX_GAIN = 18;
  const LOCATION_ENRICHMENT_YIELD_BUDGET_MS = 100;
  const FEEDBACK_ENDPOINT = "https://formspree.io/f/mqakpejw";
  let inspectionArtifactPromise = null;
  let candidateArtifactPromise = null;
  let recommendationJobs = [];
  let geoWarmScheduled = false;
  let geoWarmState = "cold";
  let lastRankedResults = [];
  let lastProfile = null;
  let lastTotalEligibleCount = 0;
  let activeQueueView = "recommended";
  let queueVisibleCounts = { recommended: TOP_N, fresh: TOP_N };
  const trackedRecommendationIds = new Set();

  function normalize(value) {
    return String(value || "").trim();
  }
  function timingNow() {
    if (typeof performance !== "undefined" && typeof performance.now === "function") return performance.now();
    return Date.now();
  }

  function yieldToBrowser() {
    if (
      typeof YartchivesUtils !== "undefined"
      && typeof YartchivesUtils.yieldToBrowser === "function"
    ) {
      return YartchivesUtils.yieldToBrowser();
    }
    return Promise.resolve();
  }

  function recordTimingStage(timing, name, startedAt, endedAt = timingNow()) {
    if (!timing || !name) return 0;
    const duration = Math.max(0, endedAt - startedAt);
    timing.stages[name] = Math.round(duration * 10) / 10;
    return duration;
  }

  function normalizeGeoErrorCode(value) {
    const code = normalize(value);
    if (!code) return null;
    if (
      code === "geo_network"
      || code === "geo_malformed"
      || code === "geo_internal"
      || /^geo_http_(?:[1-5][0-9]{2}|error)$/.test(code)
      || /^geo_index_(?:zips|cities|sort)$/.test(code)
    ) return code;
    return "geo_unknown";
  }

  const TIMING_STAGE_LABELS = {
    queue_setup: "Queue setup",
    paint_wait: "Frame callback wait",
    candidate_artifact: "Candidate download",
    candidate_filter: "Candidate filtering",
    inspection_artifact: "Inspection download",
    inspection_attach: "Inspection attachment",
    location_enrichment: "Location enrichment",
    ranking: "Ranking",
    render: "Render",
  };

  function timingDiagnosticText(payload) {
    if (!payload) return "";
    const lines = [`Apply Next total: ${Number(payload.total_ms || 0).toFixed(1)} ms`];
    for (const [name, value] of Object.entries(payload.stages_ms || {})) {
      lines.push(`${TIMING_STAGE_LABELS[name] || name}: ${Number(value || 0).toFixed(1)} ms`);
    }
    const counts = payload.counts || {};
    lines.push(
      `Candidates: ${Number(counts.candidates || 0)} · Rankable: ${Number(counts.rankable || 0)} · Distance candidates: ${Number(counts.distance_candidates || 0)} · Unique distance lookups: ${Number(counts.distance_unique_lookups || 0)} · Distance cache hits: ${Number(counts.distance_cache_hits || 0)} · Distance lookup failures: ${Number(counts.distance_lookup_failures || 0)} · Recommendations: ${Number(counts.recommendations || 0)}`
    );
    lines.push(`Location geo load: ${Number(counts.location_geo_load_ms || 0).toFixed(1)} ms · parse: ${Number(counts.location_parse_ms || 0).toFixed(1)} ms · compute: ${Number(counts.location_compute_ms || 0).toFixed(1)} ms · yields: ${Number(counts.location_yield_ms || 0).toFixed(1)} ms (${Number(counts.location_yield_count || 0)}) · ordering: ${Number(counts.location_order_ms || 0).toFixed(1)} ms`);
    if (payload.geo_error) lines.push(`Geo load error: ${payload.geo_error}`);
    if (payload.geo_warm_state) lines.push(`Geo warm state at open: ${payload.geo_warm_state}`);
    if (payload.page_visibility) lines.push(`Page visibility at open: ${payload.page_visibility}`);
    lines.push(`Status: ${payload.status || "unknown"}`);
    return lines.join("\n");
  }

  function dominantTimingStage(payload) {
    let dominant = null;
    for (const [name, rawValue] of Object.entries(payload?.stages_ms || {})) {
      const value = Number(rawValue);
      if (!Number.isFinite(value)) continue;
      if (!dominant || value > dominant.ms) dominant = { name, ms: value };
    }
    return dominant;
  }

  function renderTimingDiagnostic(panel, payload) {
    if (!panel || !payload || typeof document === "undefined") return null;
    panel.querySelector(".apply-next-diagnostics")?.remove();

    const details = element("details", "apply-next-diagnostics");
    if (Number(payload.total_ms || 0) >= 1500) details.open = true;

    const dominant = dominantTimingStage(payload);
    const totalSeconds = Number(payload.total_ms || 0) / 1000;
    const summaryText = dominant
      ? `Performance: ${totalSeconds.toFixed(1)}s · slowest: ${TIMING_STAGE_LABELS[dominant.name] || dominant.name} ${(dominant.ms / 1000).toFixed(1)}s`
      : `Performance: ${totalSeconds.toFixed(1)}s`;
    details.append(element("summary", "", summaryText));

    details.append(
      element(
        "p",
        "apply-next-note",
        "Beta diagnostics only. This contains aggregate timing and counts, not your profile, ZIP, employers, jobs, URLs, or feedback."
      ),
      element("pre", "apply-next-diagnostics-output", timingDiagnosticText(payload))
    );

    const copy = element("button", "ghost-btn apply-next-diagnostics-copy", "Copy diagnostics");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      const output = details.querySelector(".apply-next-diagnostics-output");
      try {
        if (!navigator?.clipboard?.writeText) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(output?.textContent || "");
        copy.textContent = "Copied";
      } catch (_) {
        copy.textContent = "Select text above to copy";
      }
    });
    details.append(copy);
    panel.append(details);
    return details;
  }

  function publishApplyNextTiming(timing, metadata = {}, endedAt = timingNow()) {
    if (!timing) return null;
    const payload = {
      total_ms: Math.round(Math.max(0, endedAt - timing.startedAt) * 10) / 10,
      stages_ms: { ...timing.stages },
      counts: {
        candidates: Number(metadata.candidates || 0),
        rankable: Number(metadata.rankable || 0),
        distance_candidates: Number(metadata.distance_candidates || 0),
        distance_unique_lookups: Number(metadata.distance_unique_lookups || 0),
        distance_cache_hits: Number(metadata.distance_cache_hits || 0),
        distance_lookup_failures: Number(metadata.distance_lookup_failures || 0),
        location_geo_load_ms: Number(metadata.location_geo_load_ms || 0),
        location_parse_ms: Number(metadata.location_parse_ms || 0),
        location_compute_ms: Number(metadata.location_compute_ms || 0),
        location_yield_ms: Number(metadata.location_yield_ms || 0),
        location_yield_count: Number(metadata.location_yield_count || 0),
        location_order_ms: Number(metadata.location_order_ms || 0),
        recommendations: Number(metadata.recommendations || 0),
      },
      geo_error: normalizeGeoErrorCode(metadata.geo_error),
      geo_warm_state: normalize(metadata.geo_warm_state) || null,
      page_visibility: normalize(metadata.page_visibility) || null,
      status: metadata.status || "success",
    };
    if (typeof globalThis !== "undefined") globalThis.__YARTCHIVES_APPLY_NEXT_TIMING__ = payload;
    if (typeof console !== "undefined" && typeof console.info === "function") {
      console.info("[Yartchives Apply Next timing]", payload);
    }
    try {
      if (typeof YartchivesAnalytics !== "undefined" && typeof YartchivesAnalytics.track === "function") {
        YartchivesAnalytics.track("apply_next_timing", payload);
        if (typeof YartchivesAnalytics.flush === "function") {
          void YartchivesAnalytics.flush();
        }
      }
    } catch (_) {}
    return payload;
  }


  function hasFoundingBetaTester(storage) {
    try {
      return storage?.getItem(FOUNDING_BETA_TESTER_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function awardFoundingBetaTester(storage) {
    try {
      storage?.setItem(FOUNDING_BETA_TESTER_KEY, "1");
    } catch (_) {}
    refreshFoundingBetaStatus();
  }

  function refreshFoundingBetaStatus() {
    if (typeof document === "undefined") return;
    const badge = document.querySelector("#applyNextFoundingBetaBadge");
    if (!badge) return;
    badge.classList.toggle("hidden", !hasFoundingBetaTester(typeof localStorage !== "undefined" ? localStorage : null));
  }

  function foundingBetaBadge() {
    const badge = element("span", "apply-next-beta-badge", "Founding beta tester");
    badge.id = "applyNextFoundingBetaBadge";
    badge.classList.toggle("hidden", !hasFoundingBetaTester(typeof localStorage !== "undefined" ? localStorage : null));
    badge.setAttribute("title", "Thanks for helping shape the Apply Next beta.");
    return badge;
  }

  function postedAgeDays(value, nowValue = new Date()) {
    if (!value) return null;
    const date = new Date(value);
    const now = nowValue instanceof Date ? nowValue : new Date(nowValue);
    if (!Number.isFinite(date.getTime()) || !Number.isFinite(now.getTime())) return null;

    const postedUtcDay = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
    const nowUtcDay = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    return Math.max(0, Math.floor((nowUtcDay - postedUtcDay) / 86400000));
  }

  function formatPostedDate(value, isAuthoritative, nowValue = new Date()) {
    if (!value) return "";
    const date = new Date(value);
    const daysAgo = postedAgeDays(value, nowValue);
    if (!Number.isFinite(date.getTime()) || daysAgo === null) return "";

    const monthDay = `${date.getUTCMonth() + 1}/${date.getUTCDate()}`;
    const ageLabel = `${daysAgo} ${daysAgo === 1 ? "day" : "days"} ago`;
    return isAuthoritative ? `Posted ${monthDay} · ${ageLabel}` : ageLabel;
  }

  function freshRankedResults(ranked, nowValue = new Date()) {
    return (ranked || []).filter(result => {
      if (!result || result.excluded || Number(result.total || 0) < FRESH_MIN_SCORE) return false;
      const age = postedAgeDays(result.job?.posted_at, nowValue);
      return age !== null && age <= FRESH_MAX_AGE_DAYS;
    });
  }

  function queueResults(ranked, view = "recommended", nowValue = new Date()) {
    return view === "fresh"
      ? freshRankedResults(ranked, nowValue)
      : (ranked || []);
  }

  function visibleQueueResults(ranked, view = "recommended", nowValue = new Date(), visibleCount = TOP_N) {
    return queueResults(ranked, view, nowValue).slice(0, Math.max(TOP_N, Number(visibleCount || TOP_N)));
  }

  function validateProfile(profile) {
    if (!profile || typeof profile !== "object" || Array.isArray(profile)) {
      return { ok: false, error: "Profile must be a JSON object." };
    }
    if (!normalize(profile.targetTerm)) {
      return { ok: false, error: "Profile must include targetTerm." };
    }
    if (!Array.isArray(profile.roleFamilies) || !profile.roleFamilies.length) {
      return { ok: false, error: "Profile must include at least one role family." };
    }
    return { ok: true, profile };
  }

  function loadProfile(storage) {
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return validateProfile(parsed).ok ? parsed : null;
    } catch (_) {
      return null;
    }
  }

  function saveProfile(storage, profile) {
    const checked = validateProfile(profile);
    if (!checked.ok) throw new Error(checked.error);
    const existed = Boolean(loadProfile(storage));
    storage.setItem(STORAGE_KEY, JSON.stringify(profile));
    if (!existed && typeof YartchivesAnalytics !== "undefined") {
      YartchivesAnalytics.track("profile_created");
    }
    return profile;
  }

  function knownWrongTerm(job, profile) {
    const target = normalize(profile?.targetTerm).toLowerCase();
    const term = normalize(job?.term).toLowerCase();
    return Boolean(target && term && target !== term);
  }

  function candidatePool(jobs, profile, localState) {
    const applied = localState?.applied || new Set();
    const hidden = localState?.hidden || new Set();
    return (jobs || []).filter(job => {
      if (!job || applied.has(job.id) || hidden.has(job.id)) return false;
      if (knownWrongTerm(job, profile)) return false;
      return true;
    });
  }

  function eligiblePoolCount(jobs, profile) {
    return (jobs || []).filter(job => {
      if (!job || knownWrongTerm(job, profile)) return false;
      return true;
    }).length;
  }

  function authoritativeCandidatePool(jobs) {
    return (jobs || []).filter(job => job?._inspection?.status === "inspected");
  }

  function maximumDistanceLocationGain(result) {
    if (!result?.job || isRemoteJob(result.job)) return 0;
    const currentLocationScore = Number(result?.components?.location?.score);
    if (!Number.isFinite(currentLocationScore)) return LOCATION_DISTANCE_MAX_GAIN;
    return Math.max(0, componentMax("location") - currentLocationScore);
  }

  function distanceEnrichmentCandidates(preliminaryRanked, nowValue = new Date()) {
    const ranked = (preliminaryRanked || []).filter(result => result && !result.excluded && result.job);
    if (!ranked.length) return [];

    const recommendedCutoff = ranked.length >= TOP_N
      ? Number(ranked[TOP_N - 1].total || 0)
      : 0;

    const freshByAge = ranked.filter(result => {
      const age = postedAgeDays(result.job?.posted_at, nowValue);
      return age !== null && age <= FRESH_MAX_AGE_DAYS;
    });
    const freshCutoff = freshByAge.length >= TOP_N
      ? Math.max(FRESH_MIN_SCORE, Number(freshByAge[TOP_N - 1].total || 0))
      : FRESH_MIN_SCORE;

    const decisionCutoff = Math.min(recommendedCutoff, freshCutoff);
    return ranked
      .filter(result => (
        maximumDistanceLocationGain(result) > 0
        && Number(result.total || 0) + maximumDistanceLocationGain(result) >= decisionCutoff
      ))
      .map(result => result.job);
  }


  function explainProfileChange(oldProfile, newProfile, oldTopId, newTopId) {
    if (!oldProfile || !newProfile) return null;
    if (JSON.stringify(oldProfile) === JSON.stringify(newProfile)) return null;

    const changes = [];
    const changedLoc = JSON.stringify(oldProfile.baseZips) !== JSON.stringify(newProfile.baseZips) ||
      JSON.stringify(oldProfile.preferredStates) !== JSON.stringify(newProfile.preferredStates) ||
      oldProfile.relocationAllowed !== newProfile.relocationAllowed ||
      oldProfile.remoteRelevant !== newProfile.remoteRelevant ||
      oldProfile.nearbyMiles !== newProfile.nearbyMiles;
    if (changedLoc) changes.push("location");

    const oldRoleIds = (oldProfile.roleFamilies || []).map(f => f.id);
    const newRoleIds = (newProfile.roleFamilies || []).map(f => f.id);
    const changedRoles = JSON.stringify(oldRoleIds) !== JSON.stringify(newRoleIds) ||
      JSON.stringify(oldProfile.opportunityTypes) !== JSON.stringify(newProfile.opportunityTypes);
    if (changedRoles) changes.push("role");

    const changedFit = JSON.stringify(oldProfile.facts?.supportedSkills) !== JSON.stringify(newProfile.facts?.supportedSkills) ||
      JSON.stringify(oldProfile.facts?.cautiousSkills) !== JSON.stringify(newProfile.facts?.cautiousSkills) ||
      oldProfile.major !== newProfile.major ||
      oldProfile.degree !== newProfile.degree ||
      oldProfile.graduation !== newProfile.graduation ||
      JSON.stringify(oldProfile.supportedKeywords) !== JSON.stringify(newProfile.supportedKeywords) ||
      JSON.stringify(oldProfile.cautiousKeywords) !== JSON.stringify(newProfile.cautiousKeywords);
    if (changedFit) changes.push("skills/background");

    const changedTerm = oldProfile.targetTerm !== newProfile.targetTerm;
    if (changedTerm) changes.push("target term");

    const changedEligibility = oldProfile.citizenship !== newProfile.citizenship ||
      oldProfile.workAuthorization !== newProfile.workAuthorization ||
      oldProfile.securityClearance !== newProfile.securityClearance;
    if (changedEligibility) changes.push("eligibility");

    if (changes.length === 0) return "Recommendations re-evaluated after profile changes.";

    let changedList = changes.join(", ");
    if (changes.length > 1) {
        changedList = changes.slice(0, -1).join(", ") + " and " + changes[changes.length - 1];
    }

    let msg = `Recommendations re-evaluated after ${changedList} changes.`;

    if (oldTopId && newTopId && oldTopId !== newTopId) {
      if (changes.length === 1) {
        msg += ` This new top recommendation is stronger under your updated ${changes[0]} preferences.`;
      } else {
        msg += ` This new top recommendation is a better match for your updated profile.`;
      }
    }
    return msg;
  }

  function profileSummary(profile) {
    const families = (profile?.roleFamilies || [])
      .slice()
      .sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0))
      .map(family => family.label || family.id)
      .filter(Boolean)
      .slice(0, 4);
    const bases = (profile?.baseLabels || []).filter(Boolean);
    return [profile?.targetTerm, families.join(" · "), bases.join(" + ")].filter(Boolean).join(" · ");
  }

  function emptyInspectionArtifact() {
    return { version: 1, entries: {}, listing_index: {} };
  }

  async function fetchInspectionArtifact(fetchImpl) {
    const client = fetchImpl || (typeof fetch === "function" ? fetch : null);
    if (!client) return emptyInspectionArtifact();
    try {
      const response = await client(INSPECTION_URL);
      if (!response || !response.ok) return emptyInspectionArtifact();
      const payload = await response.json();
      if (!payload || typeof payload !== "object") return emptyInspectionArtifact();
      return {
        version: payload.version || 1,
        entries: payload.entries && typeof payload.entries === "object" ? payload.entries : {},
        listing_index: payload.listing_index && typeof payload.listing_index === "object" ? payload.listing_index : {},
      };
    } catch (_) {
      return emptyInspectionArtifact();
    }
  }

  function loadInspectionArtifact(fetchImpl) {
    if (fetchImpl) return fetchInspectionArtifact(fetchImpl);
    if (!inspectionArtifactPromise) inspectionArtifactPromise = fetchInspectionArtifact();
    return inspectionArtifactPromise;
  }

  async function fetchCandidateArtifact(fetchImpl) {
    const client = fetchImpl || (typeof fetch === "function" ? fetch : null);
    if (!client) return [];
    try {
      const response = await client(CANDIDATE_URL);
      if (!response || !response.ok) return [];
      const payload = await response.json();
      return Array.isArray(payload?.jobs) ? payload.jobs : [];
    } catch (_) {
      return [];
    }
  }

  function loadCandidateArtifact(fetchImpl) {
    if (fetchImpl) return fetchCandidateArtifact(fetchImpl);
    if (!candidateArtifactPromise) candidateArtifactPromise = fetchCandidateArtifact();
    return candidateArtifactPromise;
  }

  function scheduleGeoWarm(profile) {
    if (geoWarmScheduled) return false;
    const zips = (profile?.baseZips || []).filter(value => /^\d{5}$/.test(String(value)));
    if (!zips.length || typeof loadGeoIndex !== "function") return false;
    geoWarmScheduled = true;
    geoWarmState = "scheduled";

    const warm = () => {
      geoWarmState = "loading";
      void loadGeoIndex()
        .then(() => { geoWarmState = "ready"; })
        .catch(() => {
          geoWarmScheduled = false;
          geoWarmState = "failed";
        });
    };
    const scheduleWhenIdle = () => {
      if (typeof requestIdleCallback === "function") {
        requestIdleCallback(warm);
      } else if (typeof setTimeout === "function") {
        setTimeout(warm, 1500);
      } else {
        warm();
      }
    };

    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => scheduleWhenIdle());
    } else if (typeof setTimeout === "function") {
      setTimeout(scheduleWhenIdle, 0);
    } else {
      scheduleWhenIdle();
    }
    return true;
  }

  function attachInspections(jobs, artifact) {
    const index = artifact?.listing_index || {};
    const entries = artifact?.entries || {};
    for (const job of jobs || []) {
      if (!job || typeof job !== "object") continue;
      delete job._inspection;
      const canonical = index[job.id];
      const inspection = canonical && entries[canonical]?.inspection;
      if (inspection && typeof inspection === "object") {
        job._inspection = inspection;
        const authoritativePostedAt = normalize(inspection?.posting?.posted_at);
        if (authoritativePostedAt) {
          if (!("_metadataPostedAt" in job)) job._metadataPostedAt = job.posted_at || null;
          job.posted_at = authoritativePostedAt;
          job._postedAtBasis = "authoritative";
        }
      }
    }
    return jobs;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function setProfileError(message) {
    const box = document.querySelector("#applyNextProfileError");
    if (!box) return;
    box.textContent = message || "";
    box.classList.toggle("hidden", !message);
  }

  function setProfileSetupMode(active) {
    const main = document.querySelector("main");
    if (!main) return;
    main.classList.toggle("apply-next-profile-mode", Boolean(active));
  }

  function loadEntryMode(storage) {
    try {
      const mode = storage?.getItem(ENTRY_MODE_KEY);
      return mode === "apply-next" || mode === "browse" ? mode : null;
    } catch (_) {
      return null;
    }
  }

  function saveEntryMode(storage, mode) {
    if (mode !== "apply-next" && mode !== "browse") throw new Error("Invalid entry mode.");
    try {
      storage?.setItem(ENTRY_MODE_KEY, mode);
    } catch (_) {}
    return mode;
  }

  function switchToBrowse(panel) {
    saveEntryMode(typeof localStorage !== "undefined" ? localStorage : null, "browse");
    panel?.classList.add("hidden");
    delete panel?.dataset?.view;
    const button = typeof document !== "undefined" ? document.querySelector("#applyNextBtn") : null;
    if (button) button.setAttribute("aria-expanded", "false");
    setProfileSetupMode(false);
  }

  function browseInternshipsButton(panel, className = "ghost-btn") {
    const browse = element("button", className, "Browse internships");
    browse.type = "button";
    browse.addEventListener("click", () => switchToBrowse(panel));
    return browse;
  }

  function renderEntryChoice(panel) {
    panel.dataset.view = "entry";
    panel.classList.remove("hidden");
    setProfileSetupMode(true);
    panel.innerHTML = "";

    const entry = element("div", "apply-next-entry");
    const copy = element("div", "apply-next-entry-copy");
    copy.append(
      element("p", "eyebrow", "Start here"),
      element("h2", "", "Find the internships worth applying to"),
      element("p", "apply-next-entry-lede", "Apply Next ranks current internships around your profile so you can spend your time on the strongest opportunities first.")
    );

    const actions = element("div", "apply-next-entry-actions");
    const ranked = element("button", "primary-btn apply-next-entry-primary", "Get internships ranked for you");
    ranked.type = "button";
    ranked.addEventListener("click", () => document.querySelector("#applyNextBtn")?.click());

    const browse = element("button", "ghost-btn apply-next-entry-secondary", "Browse all internships");
    browse.type = "button";
    browse.addEventListener("click", () => switchToBrowse(panel));

    actions.append(ranked, browse);
    entry.append(copy, actions);
    panel.append(entry);
  }

  function setupPanel(panel) {
    setProfileSetupMode(true);
    panel.innerHTML = "";
    panel.dataset.view = "apply-next";
    const header = element("div", "apply-next-heading");
    const copy = element("div");
    copy.append(
      element("p", "eyebrow", "private browser profile"),
      element("h2", "", "Apply Next"),
      element("p", "muted", "Import your private strategy once. It stays in this browser's local storage and is never added to the public feed or shared URL.")
    );
    header.append(copy, browseInternshipsButton(panel));
    panel.append(header);

    const textarea = element("textarea", "apply-next-profile-input");
    textarea.id = "applyNextProfileInput";
    textarea.rows = 12;
    textarea.placeholder = "Paste your Apply Next profile JSON here…";
    textarea.setAttribute("aria-label", "Paste your Apply Next profile JSON here");
    textarea.autocomplete = "off";
    textarea.spellcheck = false;
    panel.append(textarea);

    const error = element("p", "error-box hidden");
    error.id = "applyNextProfileError";
    panel.append(error);

    const actions = element("div", "apply-next-profile-actions");
    const save = element("button", "primary-btn", "Save private profile");
    save.type = "button";
    save.addEventListener("click", async () => {
      try {
        const parsed = JSON.parse(textarea.value);
        saveProfile(localStorage, parsed);
        setProfileError("");
        await renderPanel(panel);
      } catch (error) {
        setProfileError(error.message || "Invalid profile JSON.");
      }
    });
    actions.append(save);
    panel.append(actions);
  }

  function locationValueText(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string" || typeof value === "number") return normalize(value);
    if (Array.isArray(value)) {
      return value.map(locationValueText).filter(Boolean).join(" · ");
    }
    if (typeof value !== "object") return "";

    if (Array.isArray(value.values)) {
      const values = value.values.map(locationValueText).filter(Boolean);
      if (values.length) return values.join(" · ");
    }

    for (const key of ["text", "label", "display_name", "displayName", "formatted", "formatted_address", "name"]) {
      const text = locationValueText(value[key]);
      if (text) return text;
    }

    const city = locationValueText(value.city);
    const stateValue = locationValueText(value.state || value.region || value.state_code);
    const country = locationValueText(value.country || value.country_code);
    const parts = [city, stateValue, country].filter(Boolean);
    return parts.join(", ");
  }

  function locationDisplayValues(job) {
    const authoritative = (typeof YartchivesUtils !== "undefined" && YartchivesUtils.authoritativeLocationValues)
      ? YartchivesUtils.authoritativeLocationValues(job)
      : [];
    if (authoritative.length > 1) return authoritative;
    const raw = locationValueText(job?._displayLocation) || locationValueText(job?.location);
    if (!raw) return authoritative.length ? authoritative : [];
    const split = raw.split(/\s*(?:;|\||·)\s*/).map(normalize).filter(Boolean);
    return split.length > 1 ? split : [raw];
  }

  function cardLocationText(job) {
    return locationValueText(job?._displayLocation)
      || locationValueText(job?.location)
      || "Location not listed";
  }

  function orderLocationValues(values, primaryDistances, fallbackDistances) {
    return (values || [])
      .map((value, index) => ({
        value,
        index,
        primary: Number.isFinite(primaryDistances?.[index]) ? primaryDistances[index] : Infinity,
        fallback: Number.isFinite(fallbackDistances?.[index]) ? fallbackDistances[index] : Infinity,
      }))
      .sort((a, b) => (
        a.primary - b.primary
        || a.fallback - b.fallback
        || a.index - b.index
      ))
      .map(item => item.value);
  }

  function distanceCacheKey(value, job, origin) {
    const normalizedValue = normalize(value).toLowerCase().replace(/\s+/g, " ");
    const states = Array.isArray(job?.states)
      ? job.states.map(state => normalize(state).toUpperCase()).filter(Boolean).sort().join(",")
      : "";
    const lat = Number(origin?.lat);
    const lon = Number(origin?.lon);
    return `${states}|${normalizedValue}|${Number.isFinite(lat) ? lat : ""}|${Number.isFinite(lon) ? lon : ""}`;
  }

  async function addBaseDistances(jobs, profile) {
    for (const job of jobs || []) {
      if (!job || typeof job !== "object") continue;
      job._distanceMiles = null;
      delete job._distanceMilesBasis;
    }

    const stats = { unique_lookups: 0, cache_hits: 0, lookup_failures: 0, geo_error: null, geo_load_ms: 0, parse_ms: 0, compute_ms: 0, yield_ms: 0, order_ms: 0, yield_count: 0 };
    const zips = (profile?.baseZips || []).filter(value => /^\d{5}$/.test(String(value)));
    if (!zips.length || typeof loadGeoIndex !== "function" || typeof distanceForJob !== "function") return stats;

    let geo;
    const geoLoadStartedAt = timingNow();
    try {
      geo = await loadGeoIndex();
      stats.geo_load_ms += timingNow() - geoLoadStartedAt;
    } catch (error) {
      stats.geo_load_ms += timingNow() - geoLoadStartedAt;
      stats.lookup_failures += 1;
      stats.geo_error = normalizeGeoErrorCode(error?.code);
      return stats;
    }

    const origins = zips.map(zip => geo.zips.get(zip)).filter(Boolean);
    if (!origins.length) return stats;

    const distanceCache = new Map();
    const distanceJobs = jobs || [];
    let lastYieldAt = timingNow();
    for (let jobIndex = 0; jobIndex < distanceJobs.length; jobIndex += 1) {
      if (jobIndex > 0 && timingNow() - lastYieldAt >= LOCATION_ENRICHMENT_YIELD_BUDGET_MS) {
        const yieldStartedAt = timingNow();
        await yieldToBrowser();
        stats.yield_ms += timingNow() - yieldStartedAt;
        stats.yield_count += 1;
        lastYieldAt = timingNow();
      }

      const job = distanceJobs[jobIndex];
      if (!job || typeof job !== "object") continue;

      let values;
      const parseStartedAt = timingNow();
      try {
        values = locationDisplayValues(job);
        stats.parse_ms += timingNow() - parseStartedAt;
      } catch (_) {
        stats.parse_ms += timingNow() - parseStartedAt;
        stats.lookup_failures += 1;
        continue;
      }

      const perLocation = values.map(value => {
        const pseudoJob = { ...job, location: value, _inspection: null };
        delete pseudoJob._geo;
        delete pseudoJob._geoResolved;
        return origins.map(origin => {
          const cacheKey = distanceCacheKey(value, job, origin);
          if (distanceCache.has(cacheKey)) {
            stats.cache_hits += 1;
            return distanceCache.get(cacheKey);
          }

          let distance = null;
          const computeStartedAt = timingNow();
          try {
            distance = distanceForJob(pseudoJob, origin, geo);
          } catch (_) {
            stats.lookup_failures += 1;
          } finally {
            stats.compute_ms += timingNow() - computeStartedAt;
          }

          distanceCache.set(cacheKey, distance);
          stats.unique_lookups = distanceCache.size;
          return distance;
        });
      });

      const orderStartedAt = timingNow();
      const finiteDistances = perLocation.flat().filter(value => Number.isFinite(value));
      if (finiteDistances.length) {
        job._distanceMiles = Math.min(...finiteDistances);
        job._distanceMilesBasis = "apply-next-profile";
      }
      if (values.length > 1) {
        const primary = perLocation.map(distances => distances[0]);
        const fallback = perLocation.map(distances => {
          const finite = distances.filter(value => Number.isFinite(value));
          return finite.length ? Math.min(...finite) : Infinity;
        });
        job._displayLocation = orderLocationValues(values, primary, fallback).join(" · ");
      } else {
        delete job._displayLocation;
      }
      stats.order_ms += timingNow() - orderStartedAt;
    }

    for (const key of ["geo_load_ms", "parse_ms", "compute_ms", "yield_ms", "order_ms"]) {
      stats[key] = Math.round(stats[key] * 10) / 10;
    }
    return stats;
  }

  function isRemoteJob(job) {
    const states = Array.isArray(job?.states) ? job.states.map(value => normalize(value).toLowerCase()) : [];
    if (states.includes("remote")) return true;
    return normalize(job?.location || job?._displayLocation).toLowerCase().split(/[·,]/).some(part => part.trim() === "remote");
  }

  function componentLabel(key) {
    return ({
      fit: "How well you match",
      eligibility: "Eligibility",
      freshness: "How recent it is",
      roi: "Worth applying",
      role: "Role",
      location: "Location fit",
      link: "Link",
    })[key] || key;
  }

  function componentExplanation(key) {
    return ({
      fit: "Based on your skills, major, degree level, and the job's known requirements.",
      freshness: "Newer postings score higher because timing can affect how crowded the applicant pool is.",
      roi: "Balances how valuable this role is for you with the opportunity and competition signals we know.",
      location: "Based on commute distance, remote status, and your location preferences.",
    })[key] || "";
  }

  function scoreBand(key, score, max, job = null) {
    if (!max) return "";
    const ratio = Number(score || 0) / max;
    if (key === "fit") return ratio >= 0.75 ? "Strong match" : (ratio >= 0.55 ? "Good match" : "Possible match");
    if (key === "freshness") return ratio >= 0.8 ? "Very recent" : (ratio >= 0.5 ? "Recent" : "Older posting");
    if (key === "roi") return ratio >= 0.75 ? "High value" : (ratio >= 0.55 ? "Worth considering" : "Lower value");
    if (key === "location" && isRemoteJob(job)) return "Remote";
    if (key === "location") return ratio >= 0.75 ? "Very convenient" : (ratio >= 0.55 ? "Manageable" : "Less convenient");
    return "";
  }

  function totalScoreBandClass(score) {
    if (score < 55) return "apply-next-score-low";
    if (score < 75) return "apply-next-score-medium";
    return "apply-next-score-high";
  }

  function decisionHighlights(result) {
    if (result?.excluded || result?.components?.eligibility?.excluded) {
      return ["Excluded by eligibility constraints"];
    }

    const highlights = [];
    const concerns = [];

    const fitRatio = (result?.components?.fit?.score || 0) / (componentMax("fit") || 1);
    if (fitRatio >= 0.75) highlights.push("Strong match");
    else if (fitRatio < 0.55) concerns.push("weak match");

    const roiRatio = (result?.components?.roi?.score || 0) / (componentMax("roi") || 1);
    if (roiRatio >= 0.75) highlights.push("High value");
    else if (roiRatio < 0.55) concerns.push("lower value");

    const freshnessRatio = (result?.components?.freshness?.score || 0) / (componentMax("freshness") || 1);
    if (freshnessRatio >= 0.8) highlights.push("Very recent");
    else if (freshnessRatio >= 0.5) highlights.push("Recent");
    else concerns.push("older posting");

    const locRatio = (result?.components?.location?.score || 0) / (componentMax("location") || 1);
    if (isRemoteJob(result?.job)) {
      if (locRatio >= 0.55) highlights.push("Remote");
      else concerns.push("remote preference mismatch");
    } else if (locRatio >= 0.75) highlights.push("Very convenient location");
    else if (locRatio >= 0.55) highlights.push("Manageable location");
    else concerns.push("less convenient location");

    if (result?.inspection?.state === "unavailable") {
      concerns.push("posting unavailable");
    } else if (result?.inspection?.state !== "inspected") {
      concerns.push("unverified evidence");
    }

    const finalHighlights = [];

    if (concerns.length > 0) {
      finalHighlights.push("Concerns: " + concerns.join(", "));
    }

    // take top positive highlights up to 4 total
    const slotsRemaining = 4 - finalHighlights.length;
    finalHighlights.push(...highlights.slice(0, slotsRemaining));

    if (finalHighlights.length === 0) {
      finalHighlights.push("Meets basic profile criteria");
    }

    return finalHighlights;
  }

  function rankingSummary(result) {
    const drivers = [];
    for (const key of ["fit", "freshness", "roi", "location"]) {
      const component = result?.components?.[key];
      const max = componentMax(key);
      if (!component || max <= 0) continue;
      drivers.push({
        key,
        ratio: component.score / max,
        name: key === "fit" ? "profile match" : key === "roi" ? "role value" : key === "freshness" ? "timing" : "location convenience"
      });
    }

    if (!drivers.length) return "Why this is here: based on your profile and the evidence available.";

    drivers.sort((a, b) => b.ratio - a.ratio);

    const topRatio = drivers[0].ratio;
    const positiveDrivers = drivers.filter(d => topRatio - d.ratio <= 0.15 && d.ratio >= 0.55);

    const bottomRatio = drivers[drivers.length - 1].ratio;
    const negativeDrivers = drivers.filter(d => d.ratio - bottomRatio <= 0.15 && d.ratio < 0.55 && !positiveDrivers.includes(d));

    const parts = [];

    const formatNames = (names) => {
      if (names.length === 0) return "";
      if (names.length === 1) return names[0];
      return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
    };

    if (positiveDrivers.length > 0) {
      const names = positiveDrivers.map(d => d.name);
      parts.push(`strongest drivers: ${formatNames(names)}`);
    }
    if (negativeDrivers.length > 0) {
      const names = negativeDrivers.map(d => d.name);
      parts.push(`limited by: ${formatNames(names)}`);
    }

    return parts.length > 0 ? `Why this is here: ${parts.join("; ")}.` : "Why this is here: based on your profile and the evidence available.";
  }

  function componentMax(key) {
    const contract = (typeof YartchivesApplyNext !== "undefined" && YartchivesApplyNext.SCORING_CONTRACT)
      ? YartchivesApplyNext.SCORING_CONTRACT
      : {
          fit: { role: "ranking", max: 45 },
          eligibility: { role: "gate", max: 0 },
          freshness: { role: "ranking", max: 10 },
          roi: { role: "ranking", max: 25 },
          location: { role: "ranking", max: 20 },
          link: { role: "metadata", max: 0 },
        };
    return Number(contract[key]?.max || 0);
  }

  function recommendationCard(result, rank) {
    const job = result.job;
    const card = element("article", "apply-next-card");
    if (job?.id) card.dataset.id = job.id;

    const top = element("div", "apply-next-card-top");
    const titleWrap = element("div");
    titleWrap.append(
      element("p", "apply-next-rank", `#${rank} · ${job.company || "Company not listed"}`),
      element("h3", "", job.title || "Untitled opportunity"),
      element("p", "muted", cardLocationText(job))
    );
    const isAuthoritative = result.inspection?.state === "inspected";
    const postedDate = formatPostedDate(job.posted_at, isAuthoritative);
    if (postedDate) titleWrap.append(element("p", "muted apply-next-posted-date", postedDate));
    const inspectionState = result.inspection?.state || "metadata-only";
    const evidenceStatus = element(
      "span",
      `apply-next-component apply-next-inspection-status apply-next-inspection-${inspectionState}`,
      result.inspection?.label || "Metadata fallback"
    );
    let statusExplanation = "";
    if (inspectionState === "inspected") {
      statusExplanation = "Authoritative employer posting evidence is included in this score.";
    } else if (inspectionState === "unavailable") {
      statusExplanation = "This score falls back to feed metadata because authoritative posting evidence is no longer available.";
    } else {
      statusExplanation = "This score falls back to feed metadata because authoritative posting evidence is unavailable.";
    }
    evidenceStatus.title = statusExplanation;
    evidenceStatus.append(element("span", "sr-only", " " + statusExplanation));
    titleWrap.append(evidenceStatus);

    const scoreClass = `apply-next-score ${totalScoreBandClass(result.total)}`;
    const score = element("div", scoreClass);
    score.append(element("strong", "", String(result.total)), element("span", "", "/100"));
    top.append(titleWrap, score);
    card.append(top);

        const highlights = decisionHighlights(result);
    const highlightsUl = element("ul", "apply-next-highlights");
    for (const h of highlights) {
      highlightsUl.append(element("li", "", h));
    }
    card.append(highlightsUl);

    const breakdown = element("div", "apply-next-breakdown");
    for (const [key, component] of Object.entries(result.components || {})) {
      const max = componentMax(key);
      if (max <= 0) continue;
      const metric = element("div", "apply-next-metric");
      const line = element("div", "apply-next-metric-line");
      const label = element("strong", "", componentLabel(key));
      const scoreText = element("span", "", `${component.score}/${max}`);
      line.append(label, scoreText);
      metric.append(line);
      const band = scoreBand(key, component.score, max, job);
      if (band) metric.append(element("p", "apply-next-metric-band", band));
      const explanation = componentExplanation(key);
      if (explanation) metric.append(element("p", "apply-next-metric-explanation", explanation));
      breakdown.append(metric);
    }


    const details = element("details", "apply-next-why");
    const summary = element("summary", "", "Why this ranks here");
    details.append(summary, breakdown);

    if (result.inspection?.evidence?.length) {
      const evidenceHeading = element("p", "muted", "Authoritative posting evidence");
      const evidenceList = element("ul");
      for (const evidence of result.inspection.evidence) {
        const li = element("li", "", evidence);
        const text = String(evidence).toLowerCase();
        if (text.includes("unsupported hard required skill") || text.includes("major required gaps") || text.includes("known requirement conflict") || text.includes("required gap")) {
          li.classList.add("apply-next-gap-hard");
        } else if (text.includes("learnable/low-threshold stack gap") || text.includes("required skill only cautiously")) {
          li.classList.add("apply-next-gap-learnable");
        } else if (text.includes("unverified requirement") || text.includes("unverified required domain experience")) {
          li.classList.add("apply-next-gap-unknown");
        }
        evidenceList.append(li);
      }
      details.append(evidenceHeading, evidenceList);
    } else if (result.inspection?.state !== "inspected") {
      details.append(element("p", "muted", "No authoritative posting evidence is attached; metadata is used as a fallback."));
    }

    const list = element("ul");
    for (const [key, component] of Object.entries(result.components || {})) {
      const item = element("li");
      const strong = element("strong", "", `${componentLabel(key)}: `);
      item.append(strong, document.createTextNode(component.detail || "No detail available"));
      list.append(item);
    }
    details.append(list);
    card.append(details);

    const actions = element("div", "apply-next-actions");
    if (job.url) {
      const actionLabel = job.link_kind === "employer_job" ? "View posting ↗" : "Apply ↗";
      const apply = element("a", "primary-btn link-btn", actionLabel);
      apply.href = job.url;
      apply.target = "_blank";
      apply.rel = "noopener noreferrer";
      apply.addEventListener("click", () => {
        typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("apply_clicked");
      });
      actions.append(apply);
    }
    const saved = element("button", "secondary-btn", state.saved.has(job.id) ? "Saved" : "Save");
    saved.type = "button";
    saved.addEventListener("click", () => {
      if (state.saved.has(job.id)) state.saved.delete(job.id);
      else {
        state.saved.add(job.id);
        typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("saved");
      }
      persist();
      saved.textContent = state.saved.has(job.id) ? "Saved" : "Save";
      updateStats();
    });
    const applied = element("button", "secondary-btn", "Mark applied");
    applied.type = "button";
    applied.addEventListener("click", () => {
      state.applied.add(job.id);
      persist();
      updateQueueOptimistically(document.querySelector("#applyNextPanel"), loadProfile(localStorage), job.id);
      applyFilters();
    });
    const hide = element("button", "icon-btn hide-btn", "×");
    hide.type = "button";
    hide.title = "Hide listing";
    hide.setAttribute("aria-label", "Hide listing");
    hide.addEventListener("click", () => {
      state.hidden.add(job.id);
      typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("hidden");
      persist();
      updateQueueOptimistically(document.querySelector("#applyNextPanel"), loadProfile(localStorage), job.id);
      applyFilters();
    });
    actions.append(saved, applied, hide);
    card.append(actions);

    const feedbackSection = element("div", "apply-next-feedback");

    function renderFeedback() {
      feedbackSection.innerHTML = "";
      const currentFeedback = state.feedback[job.id];

      if (!currentFeedback) {
        const p = element("span", "muted", "Was this recommendation useful?");
        const goodBtn = element("button", "secondary-btn apply-next-feedback-btn", "Good suggestion");
        goodBtn.type = "button";
        goodBtn.addEventListener("click", () => {
          state.feedback[job.id] = { rating: "good" };
          awardFoundingBetaTester(localStorage);
          persist();
          renderFeedback();
        });

        const badBtn = element("button", "secondary-btn apply-next-feedback-btn", "Bad suggestion");
        badBtn.type = "button";
        badBtn.addEventListener("click", () => {
          state.feedback[job.id] = { rating: "bad" };
          awardFoundingBetaTester(localStorage);
          persist();
          renderFeedback();
        });

        const btnGroup = element("div", "apply-next-feedback-group");
        btnGroup.append(goodBtn, badBtn);
        feedbackSection.append(p, btnGroup);
      } else if (currentFeedback.submitted) {
        const p = element("span", "muted", "Feedback submitted. Thank you!");
        feedbackSection.append(p);
      } else {
        const p = element("span", "muted", `Rated as a ${currentFeedback.rating} suggestion.`);
        const undoBtn = element("button", "text-btn", "Undo");
        undoBtn.type = "button";
        undoBtn.addEventListener("click", () => {
          delete state.feedback[job.id];
          persist();
          renderFeedback();
        });
        feedbackSection.append(p, undoBtn);

        if (currentFeedback.rating === "bad") {
          const reasonWrap = element("div", "apply-next-feedback-reason");
          const reasonLabel = element("span", "muted", "Optional reason:");
          const select = element("select", "apply-next-feedback-select");
          select.innerHTML = `
            <option value="">Select reason...</option>
            <option value="role">Role interest</option>
            <option value="location">Location</option>
            <option value="fit">Requirements/Fit</option>
            <option value="company">Company/Industry</option>
            <option value="other">Other</option>
          `;
          if (currentFeedback.reason) select.value = currentFeedback.reason;

          select.addEventListener("change", (e) => {
            if (e.target.value) {
              state.feedback[job.id].reason = e.target.value;
            } else {
              delete state.feedback[job.id].reason;
            }
            persist();
          });

          reasonWrap.append(reasonLabel, select);
          feedbackSection.append(reasonWrap);
        }

        const noteWrap = element("label", "apply-next-feedback-note");
        noteWrap.append(element("span", "muted", "Anything else? (optional)"));
        const note = element("textarea", "apply-next-feedback-note-input");
        note.rows = 2;
        note.maxLength = 500;
        note.placeholder = currentFeedback.rating === "good" ? "What made this a good suggestion?" : "Tell us what was wrong with this suggestion.";
        note.value = currentFeedback.note || "";
        note.addEventListener("input", (e) => {
          const value = e.target.value.trim();
          if (value) state.feedback[job.id].note = value;
          else delete state.feedback[job.id].note;
          persist();
        });
        noteWrap.append(note);
        feedbackSection.append(noteWrap);

        const submitAction = element("div", "apply-next-feedback-submit-wrap");
        const submitBtn = element("button", "primary-btn apply-next-feedback-submit", "Submit feedback");
        submitBtn.type = "button";

        let errorSpan = null;

        submitBtn.addEventListener("click", async () => {
          if (errorSpan) {
            errorSpan.remove();
            errorSpan = null;
          }
          await YartchivesUtils.runWithPendingUi({
            control: submitBtn,
            pendingLabel: "Submitting...",
            work: async () => {
              try {
                const payload = {
                  schema: "yartchives-feedback-v1",
                  jobId: job.id,
                  rating: currentFeedback.rating,
                  reason: currentFeedback.reason || "",
                  note: currentFeedback.note || "",
                  submittedAt: new Date().toISOString()
                };
                const res = await fetch(FEEDBACK_ENDPOINT, {
                  method: "POST",
                  headers: { "Content-Type": "application/json", "Accept": "application/json" },
                  body: JSON.stringify(payload)
                });
                if (!res.ok) throw new Error("Submission failed");

                state.feedback[job.id].submitted = true;
                typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("feedback_submitted");
                persist();
                renderFeedback();
              } catch (err) {
                errorSpan = element("span", "apply-next-feedback-error", "Failed to submit. Please try again.");
                submitAction.append(errorSpan);
              }
            }
          });
        });

        submitAction.append(submitBtn);
        feedbackSection.append(submitAction);
      }
    }

    renderFeedback();
    card.append(feedbackSection);

    return card;
  }

  function renderEmptyState(type, container) {
    const empty = element("div", "apply-next-empty");
    const p = element("p", "apply-next-note");

    if (type === "loading") {
      p.textContent = "Finding your best matches…";
      p.setAttribute("role", "status");
      p.setAttribute("aria-live", "polite");
      empty.append(p);
    } else if (type === "error") {
      p.textContent = "Apply Next could not load the current feed.";
      const retryBtn = element("button", "primary-btn apply-next-empty-action", "Retry");
      retryBtn.type = "button";
      retryBtn.addEventListener("click", () => renderPanel(container.closest(".apply-next-panel")));
      empty.append(p, retryBtn);
    } else if (type === "exhausted") {
      p.textContent = "You have saved, applied to, or hidden all eligible Apply Next candidates. Close Apply Next to explore the main feed, or wait for new matches to be posted.";
      const closeBtn = element("button", "primary-btn apply-next-empty-action", "Close Apply Next");
      closeBtn.type = "button";
      closeBtn.addEventListener("click", () => document.querySelector("#applyNextBtn")?.click());
      empty.append(p, closeBtn);
    } else if (type === "no-recommendations") {
      p.textContent = "No eligible Apply Next candidates are available yet. Try adjusting your profile, or explore the main feed.";
      const editBtn = element("button", "primary-btn apply-next-empty-action", "Edit profile");
      editBtn.type = "button";
      editBtn.addEventListener("click", () => {
        const panel = container.closest(".apply-next-panel");
        setupPanel(panel);
        const input = document.querySelector("#applyNextProfileInput");
        if (input) input.value = JSON.stringify(loadProfile(localStorage), null, 2);
      });
      empty.append(p, editBtn);
    } else if (type === "fresh-empty") {
      p.textContent = `No strong matches were posted within the last ${FRESH_MAX_AGE_DAYS} days.`;
      const switchBtn = element("button", "primary-btn apply-next-empty-action", "View all recommendations");
      switchBtn.type = "button";
      switchBtn.addEventListener("click", () => {
        const panel = container.closest(".apply-next-panel");
        const btn = panel.querySelector('.apply-next-view-btn[data-queue-view="recommended"]');
        if (btn) btn.click();
      });
      empty.append(p, switchBtn);
    }

    return empty;
  }

  function renderCurrentQueue(panel, profile, poolCount, status = "success") {
    if (!panel || !profile) return;
    const list = panel.querySelector(".apply-next-list");
    const note = panel.querySelector(".apply-next-queue-note");
    const loadMore = panel.querySelector(".apply-next-load-more");
    if (!list || !note) return;

    if (status === "loading" || status === "error") {
      note.textContent = "";
      list.innerHTML = "";
      list.append(renderEmptyState(status, list));
      if (loadMore) loadMore.classList.add("hidden");
      return;
    }

    const now = new Date();
    const allForView = queueResults(lastRankedResults, activeQueueView, now);
    const visibleCount = queueVisibleCounts[activeQueueView] || TOP_N;
    const ranked = visibleQueueResults(lastRankedResults, activeQueueView, now, visibleCount);
    const inspectedCount = ranked.filter(result => result.inspection?.state === "inspected").length;

    panel.querySelectorAll(".apply-next-view-btn").forEach(button => {
      const active = button.dataset.queueView === activeQueueView;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });

    if (activeQueueView === "fresh") {
      note.textContent = `Showing ${ranked.length} of ${allForView.length} strong matches posted within the last ${FRESH_MAX_AGE_DAYS} days. Ranked by overall Apply Next score, not posting time. ${inspectedCount} of these ${ranked.length || 0} recommendations use authoritative posting evidence; the rest use metadata fallback.`;
    } else {
      note.textContent = `Showing ${ranked.length} of ${allForView.length} recommended options from ${poolCount.toLocaleString()} current candidates. ${inspectedCount} of these ${ranked.length || 0} recommendations use authoritative posting evidence; the rest use metadata fallback. Known non-${profile.targetTerm} terms plus applied/hidden jobs are excluded.`;
    }

    list.innerHTML = "";
    ranked.forEach((result, index) => list.append(recommendationCard(result, index + 1)));
    const newlyShown = ranked.filter(result => {
      const id = result?.job?.id;
      if (!id || trackedRecommendationIds.has(id)) return false;
      trackedRecommendationIds.add(id);
      return true;
    }).length;
    if (newlyShown && typeof YartchivesAnalytics !== "undefined") {
      YartchivesAnalytics.track("recommendations_shown", { count: newlyShown });
    }

    if (!ranked.length) {
      if (activeQueueView === "fresh") {
        list.append(renderEmptyState("fresh-empty", list));
      } else if (lastTotalEligibleCount > 0 && poolCount === 0) {
        list.append(renderEmptyState("exhausted", list));
      } else {
        list.append(renderEmptyState("no-recommendations", list));
      }
    }

    if (loadMore) {
      const remaining = Math.max(0, allForView.length - ranked.length);
      loadMore.classList.toggle("hidden", remaining === 0);
      loadMore.textContent = remaining > 0 ? `Load 10 more` : "";
    }
  }

  function updateQueueOptimistically(panel, profile, appliedJobId) {
    const targetPanel = panel || (typeof document !== "undefined" ? document.querySelector("#applyNextPanel") : null);
    if (!targetPanel) return;

    if (Array.isArray(lastRankedResults) && lastRankedResults.length) {
      lastRankedResults = lastRankedResults.filter(r => r.job && r.job.id !== appliedJobId && !state.applied?.has(r.job.id) && !state.hidden?.has(r.job.id));
    } else if (typeof feed !== "undefined" && Array.isArray(feed?.jobs) && profile && typeof YartchivesApplyNext !== "undefined") {
      const pool = candidatePool(feed.jobs, profile, state);
      lastRankedResults = YartchivesApplyNext.rankJobs(pool, profile, new Date());
    }

    if (typeof feed !== "undefined" && Array.isArray(feed?.jobs) && profile) {
      lastTotalEligibleCount = eligiblePoolCount(feed.jobs, profile);
    }

    const poolCount = (typeof feed !== "undefined" && Array.isArray(feed?.jobs) && profile)
      ? candidatePool(recommendationJobs, profile, state).length
      : 0;
    renderCurrentQueue(targetPanel, profile, poolCount);
  }

  function buildQueueSkeleton(profile, panel, explanation) {
    const fragment = document.createDocumentFragment();

    const heading = element("div", "apply-next-heading");
    const copy = element("div");
    copy.append(
      element("p", "eyebrow", "your next application queue"),
      element("h2", "", "Apply Next"),
      foundingBetaBadge(),
      element("p", "muted apply-next-production-status", "Checking production status…")
    );
    const controls = element("div", "apply-next-profile-actions");
    controls.append(browseInternshipsButton(panel, "text-btn"));
    const edit = element("button", "ghost-btn", "Edit profile");
    edit.type = "button";
    edit.addEventListener("click", () => {
      setupPanel(panel);
      const input = document.querySelector("#applyNextProfileInput");
      if (input) input.value = JSON.stringify(profile, null, 2);
    });
    const clear = element("button", "text-btn", "Clear private profile");
    clear.type = "button";
    clear.addEventListener("click", () => {
      localStorage.removeItem(STORAGE_KEY);
      setupPanel(panel);
    });
    controls.append(edit, clear);
    const productionStatus = copy.querySelector(".apply-next-production-status");
    if (productionStatus) {
      productionStatus.dataset.productionStatus = "true";
      productionStatus.setAttribute("aria-live", "polite");
      if (typeof renderProductionStatus === "function") renderProductionStatus();
    }
    copy.append(element("p", "muted", profileSummary(profile) || "Private strategy loaded"));
    heading.append(copy, controls);
    fragment.append(heading);

    const viewTabs = element("div", "apply-next-view-tabs");
    viewTabs.setAttribute("role", "group");
    viewTabs.setAttribute("aria-label", "Apply Next recommendation view");
    for (const [view, label] of [["recommended", "Recommended"], ["fresh", "Fresh"]]) {
      const button = element("button", "apply-next-view-btn", label);
      button.type = "button";
      button.dataset.queueView = view;
      button.addEventListener("click", () => {
        if (activeQueueView === view) return;
        activeQueueView = view;
        renderCurrentQueue(panel, profile, candidatePool(recommendationJobs, profile, state).length);
      });
      viewTabs.append(button);
    }
    fragment.append(viewTabs);

    const note = element("p", "apply-next-note apply-next-queue-note");
    fragment.append(note);
    if (explanation) {
      const explanationEl = element("p", "apply-next-explanation apply-next-note", explanation);
      fragment.append(explanationEl);
    }

    const list = element("div", "apply-next-list");
    fragment.append(list);

    const loadMore = element("button", "primary-btn apply-next-load-more hidden", "Load 10 more");
    loadMore.type = "button";
    loadMore.addEventListener("click", () => {
      queueVisibleCounts[activeQueueView] = (queueVisibleCounts[activeQueueView] || TOP_N) + TOP_N;
      renderCurrentQueue(panel, profile, candidatePool(recommendationJobs, profile, state).length);
    });
    fragment.append(loadMore);
    return fragment;
  }

  async function renderQueue(panel, profile) {
    const timing = { startedAt: timingNow(), stages: {} };
    const counts = { candidates: 0, rankable: 0, distance_candidates: 0, distance_unique_lookups: 0, distance_cache_hits: 0, distance_lookup_failures: 0, location_geo_load_ms: 0, location_parse_ms: 0, location_compute_ms: 0, location_yield_ms: 0, location_yield_count: 0, location_order_ms: 0, recommendations: 0 };
    const geoWarmStateAtOpen = geoWarmState;
    const pageVisibilityAtOpen = typeof document !== "undefined" ? normalize(document.visibilityState) : "";
    let geoError = null;
    let timingStatus = "success";
    const queueSetupStartedAt = timingNow();

    setProfileSetupMode(true);
    panel.dataset.view = "apply-next";

    panel.innerHTML = "";
    panel.append(buildQueueSkeleton(profile, panel, null));
    if (typeof renderProductionStatus === "function") renderProductionStatus();
    renderCurrentQueue(panel, profile, 0, "loading");
    panel.setAttribute("aria-busy", "true");

    const slowLoadingTimer = setTimeout(() => {
      const loadingMessage = panel.querySelector(".apply-next-empty .apply-next-note");
      if (loadingMessage && panel.getAttribute("aria-busy") === "true") {
        loadingMessage.textContent = "Still finding your best matches…";
      }
    }, 1500);

    recordTimingStage(timing, "queue_setup", queueSetupStartedAt);
    let stageStartedAt = timingNow();
    await YartchivesUtils.waitForBrowserPaint();
    recordTimingStage(timing, "paint_wait", stageStartedAt);

    try {
      stageStartedAt = timingNow();
      recommendationJobs = await loadCandidateArtifact();
      recordTimingStage(timing, "candidate_artifact", stageStartedAt);
      if (!recommendationJobs.length) throw new Error("Apply Next candidates unavailable");

      stageStartedAt = timingNow();
      const pool = candidatePool(recommendationJobs, profile, state);
      lastTotalEligibleCount = eligiblePoolCount(recommendationJobs, profile);
      counts.candidates = pool.length;
      recordTimingStage(timing, "candidate_filter", stageStartedAt);

      stageStartedAt = timingNow();
      const artifact = await loadInspectionArtifact();
      recordTimingStage(timing, "inspection_artifact", stageStartedAt);

      stageStartedAt = timingNow();
      attachInspections(pool, artifact);
      const rankablePool = authoritativeCandidatePool(pool);
      counts.rankable = rankablePool.length;
      recordTimingStage(timing, "inspection_attach", stageStartedAt);

      stageStartedAt = timingNow();
      const rankingNow = new Date();
      const preliminaryRanked = YartchivesApplyNext.rankJobs(rankablePool, profile, rankingNow);
      const distanceCandidates = distanceEnrichmentCandidates(preliminaryRanked, rankingNow);
      counts.distance_candidates = distanceCandidates.length;
      const distanceStats = await addBaseDistances(distanceCandidates, profile);
      counts.distance_unique_lookups = Number(distanceStats?.unique_lookups || 0);
      counts.distance_cache_hits = Number(distanceStats?.cache_hits || 0);
      counts.distance_lookup_failures = Number(distanceStats?.lookup_failures || 0);
      counts.location_geo_load_ms = Number(distanceStats?.geo_load_ms || 0);
      counts.location_parse_ms = Number(distanceStats?.parse_ms || 0);
      counts.location_compute_ms = Number(distanceStats?.compute_ms || 0);
      counts.location_yield_ms = Number(distanceStats?.yield_ms || 0);
      counts.location_yield_count = Number(distanceStats?.yield_count || 0);
      counts.location_order_ms = Number(distanceStats?.order_ms || 0);
      geoError = distanceStats?.geo_error || null;
      recordTimingStage(timing, "location_enrichment", stageStartedAt);

      stageStartedAt = timingNow();
      const ranked = YartchivesApplyNext.rankJobs(rankablePool, profile, rankingNow);
      counts.recommendations = ranked.length;
      recordTimingStage(timing, "ranking", stageStartedAt);

      const explanation = explainProfileChange(lastProfile, profile, lastRankedResults?.[0]?.job?.id, ranked?.[0]?.job?.id);

      lastRankedResults = ranked;
      lastProfile = profile;

      stageStartedAt = timingNow();
      panel.innerHTML = "";
      panel.append(buildQueueSkeleton(profile, panel, explanation));
      if (typeof renderProductionStatus === "function") renderProductionStatus();
      renderCurrentQueue(panel, profile, pool.length);
      recordTimingStage(timing, "render", stageStartedAt);
    } catch (error) {
      timingStatus = "error";
      console.error(error);
      panel.innerHTML = "";
      panel.append(buildQueueSkeleton(profile, panel, null));
      if (typeof renderProductionStatus === "function") renderProductionStatus();
      renderCurrentQueue(panel, profile, 0, "error");
    } finally {
      clearTimeout(slowLoadingTimer);
      panel.setAttribute("aria-busy", "false");
      const timingPayload = publishApplyNextTiming(timing, {
        ...counts,
        geo_error: geoError,
        geo_warm_state: geoWarmStateAtOpen,
        page_visibility: pageVisibilityAtOpen,
        status: timingStatus,
      });
      renderTimingDiagnostic(panel, timingPayload);
    }
  }

  async function renderPanel(panel) {
    const profile = loadProfile(localStorage);
    if (!profile) setupPanel(panel);
    else await renderQueue(panel, profile);
  }

  function init() {
    if (typeof YartchivesApplyNext === "undefined") return;
    loadInspectionArtifact();
    const savedProfile = loadProfile(typeof localStorage !== "undefined" ? localStorage : null);
    if (savedProfile) scheduleGeoWarm(savedProfile);
    const headerActions = document.querySelector(".header-actions");
    const main = document.querySelector("main");
    if (!headerActions || !main || document.querySelector("#applyNextBtn")) return;

    const button = element("button", "primary-btn apply-next-open", "Apply Next");
    button.id = "applyNextBtn";
    button.type = "button";
    button.setAttribute("aria-controls", "applyNextPanel");
    headerActions.prepend(button);

    const panel = element("section", "panel apply-next-panel hidden");
    panel.id = "applyNextPanel";
    panel.setAttribute("aria-label", "Apply Next");
    const stats = main.querySelector(".stats");
    main.insertBefore(panel, stats ? stats.nextSibling : main.firstChild);

    async function openApplyNext({ persist = true, scroll = true } = {}) {
      if (!panel.classList.contains("hidden") && panel.dataset.view === "apply-next") {
        if (scroll) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      if (persist) saveEntryMode(localStorage, "apply-next");
      typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("apply_next_open");
      panel.classList.remove("hidden");
      panel.dataset.view = "apply-next";
      button.setAttribute("aria-expanded", "true");
      activeQueueView = "recommended";
      queueVisibleCounts = { recommended: TOP_N, fresh: TOP_N };
      await YartchivesUtils.runWithPendingUi({
        control: button,
        pendingLabel: "Finding matches…",
        prepare: () => {
          setProfileSetupMode(true);
          if (scroll) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        },
        work: () => renderPanel(panel),
      });
    }

    button.addEventListener("click", async () => {
      await openApplyNext();
    });

    const rememberedMode = loadEntryMode(localStorage);
    if (!rememberedMode) {
      renderEntryChoice(panel);
    } else if (rememberedMode === "apply-next") {
      void openApplyNext({ persist: false, scroll: false });
    }

    if (typeof renderJobs === "function") {
      const priorRenderJobs = renderJobs;
      renderJobs = function () {
        priorRenderJobs();
        if (!panel.classList.contains("hidden") && loadProfile(localStorage)) renderPanel(panel);
      };
    }
  }

  return {
    STORAGE_KEY,
    FOUNDING_BETA_TESTER_KEY,
    ENTRY_MODE_KEY,
    loadEntryMode,
    saveEntryMode,
    hasFoundingBetaTester,
    awardFoundingBetaTester,
    INSPECTION_URL,
    TOP_N,
    FRESH_MAX_AGE_DAYS,
    FRESH_MIN_SCORE,
    LOCATION_ENRICHMENT_YIELD_BUDGET_MS,
    postedAgeDays,
    freshRankedResults,
    queueResults,
    visibleQueueResults,
    validateProfile,
    loadProfile,
    saveProfile,
    timingNow,
    yieldToBrowser,
    recordTimingStage,
    normalizeGeoErrorCode,
    publishApplyNextTiming,
    timingDiagnosticText,
    dominantTimingStage,
    renderTimingDiagnostic,
    fetchCandidateArtifact,
    loadCandidateArtifact,
    scheduleGeoWarm,
    geoWarmState: () => geoWarmState,
    knownWrongTerm,
    candidatePool,
    authoritativeCandidatePool,
    maximumDistanceLocationGain,
    distanceEnrichmentCandidates,
    profileSummary,
    formatPostedDate,
    locationValueText,
    locationDisplayValues,
    cardLocationText,
    orderLocationValues,
    emptyInspectionArtifact,
    loadInspectionArtifact,
    attachInspections,
    addBaseDistances,
    distanceCacheKey,
    isRemoteJob,
    componentLabel,
    componentExplanation,
    scoreBand,
    totalScoreBandClass,
    decisionHighlights,
    rankingSummary,
    componentMax,
    renderQueue,
    updateQueueOptimistically,
    explainProfileChange,
    setProfileSetupMode,
    init,
  };
});