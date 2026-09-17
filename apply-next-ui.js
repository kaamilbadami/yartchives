(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesApplyNextUI = api;
    if (typeof document !== "undefined") api.init();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const STORAGE_KEY = "yartchives-apply-next-profile-v1";
  const INSPECTION_URL = "data/workday-inspections.json";
  const TOP_N = 10;
  let inspectionArtifactPromise = null;

  function normalize(value) {
    return String(value || "").trim();
  }

  function formatPostedDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "";
    return `Posted ${new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).format(date)}`;
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
    storage.setItem(STORAGE_KEY, JSON.stringify(profile));
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
      const response = await client(INSPECTION_URL, { cache: "no-store" });
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

  function attachInspections(jobs, artifact) {
    const index = artifact?.listing_index || {};
    const entries = artifact?.entries || {};
    for (const job of jobs || []) {
      if (!job || typeof job !== "object") continue;
      delete job._inspection;
      const canonical = index[job.id];
      const inspection = canonical && entries[canonical]?.inspection;
      if (inspection && typeof inspection === "object") job._inspection = inspection;
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

  function setupPanel(panel) {
    panel.innerHTML = "";
    const header = element("div", "apply-next-heading");
    const copy = element("div");
    copy.append(
      element("p", "eyebrow", "private browser profile"),
      element("h2", "", "Apply Next"),
      element("p", "muted", "Import your private strategy once. It stays in this browser's local storage and is never added to the public feed or shared URL.")
    );
    header.append(copy);
    panel.append(header);

    const textarea = element("textarea", "apply-next-profile-input");
    textarea.id = "applyNextProfileInput";
    textarea.rows = 12;
    textarea.placeholder = "Paste your Apply Next profile JSON here…";
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

  async function addBaseDistances(jobs, profile) {
    for (const job of jobs || []) {
      if (!job || typeof job !== "object") continue;
      job._distanceMiles = null;
      delete job._distanceMilesBasis;
    }

    const zips = (profile?.baseZips || []).filter(value => /^\d{5}$/.test(String(value)));
    if (!zips.length || typeof loadGeoIndex !== "function" || typeof distanceForJob !== "function") return;
    try {
      const geo = await loadGeoIndex();
      const origins = zips.map(zip => geo.zips.get(zip)).filter(Boolean);
      if (!origins.length) return;
      for (const job of jobs) {
        const distances = origins
          .map(origin => distanceForJob(job, origin, geo))
          .filter(value => Number.isFinite(value));
        if (distances.length) {
          job._distanceMiles = Math.min(...distances);
          job._distanceMilesBasis = "apply-next-profile";
        }
      }
    } catch (_) {
      // Location scoring still has state/remote/relocation fallbacks if ZIP data is unavailable.
    }
  }

  function componentLabel(key) {
    return ({
      fit: "Fit",
      eligibility: "Eligibility",
      freshness: "Freshness",
      roi: "Application Value",
      role: "Role",
      location: "Location",
      link: "Link",
    })[key] || key;
  }

  function componentMax(key) {
    const maxima = (typeof YartchivesApplyNext !== "undefined" && YartchivesApplyNext.SCORE_MAXIMA)
      ? YartchivesApplyNext.SCORE_MAXIMA
      : { fit: 40, eligibility: 0, freshness: 10, roi: 15, role: 20, location: 15, link: 0 };
    return Number(maxima[key] || 0);
  }

  function recommendationCard(result, rank) {
    const job = result.job;
    const card = element("article", "apply-next-card");

    const top = element("div", "apply-next-card-top");
    const titleWrap = element("div");
    titleWrap.append(
      element("p", "apply-next-rank", `#${rank} · ${job.company || "Company not listed"}`),
      element("h3", "", job.title || "Untitled opportunity"),
      element("p", "muted", job.location || "Location not listed")
    );
    const postedDate = formatPostedDate(job.posted_at);
    if (postedDate) titleWrap.append(element("p", "muted apply-next-posted-date", postedDate));
    const evidenceStatus = element(
      "span",
      "apply-next-component apply-next-inspection-status",
      result.inspection?.label || "Metadata only"
    );
    evidenceStatus.title = result.inspection?.state === "inspected"
      ? "Authoritative employer posting evidence is included in this score."
      : "This score falls back to feed metadata because authoritative posting evidence is unavailable.";
    titleWrap.append(evidenceStatus);

    const score = element("div", "apply-next-score");
    score.append(element("strong", "", String(result.total)), element("span", "", "/100"));
    top.append(titleWrap, score);
    card.append(top);

    const breakdown = element("div", "apply-next-breakdown");
    for (const [key, component] of Object.entries(result.components || {})) {
      const max = componentMax(key);
      if (max <= 0) continue;
      const chip = element("span", "apply-next-component");
      chip.textContent = `${componentLabel(key)} ${component.score}/${max}`;
      breakdown.append(chip);
    }
    card.append(breakdown);

    const details = element("details", "apply-next-why");
    const summary = element("summary", "", "Why this ranks here");
    details.append(summary);

    if (result.inspection?.evidence?.length) {
      const evidenceHeading = element("p", "muted", "Authoritative posting evidence");
      const evidenceList = element("ul");
      for (const evidence of result.inspection.evidence) evidenceList.append(element("li", "", evidence));
      details.append(evidenceHeading, evidenceList);
    } else if (result.inspection?.state !== "inspected") {
      details.append(element("p", "muted", "No authoritative posting inspection is attached; metadata scoring is used as the fallback."));
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
      const apply = element("a", "primary-btn link-btn", "Apply ↗");
      apply.href = job.url;
      apply.target = "_blank";
      apply.rel = "noopener noreferrer";
      actions.append(apply);
    }
    const saved = element("button", "secondary-btn", state.saved.has(job.id) ? "Saved" : "Save");
    saved.type = "button";
    saved.addEventListener("click", () => {
      if (state.saved.has(job.id)) state.saved.delete(job.id);
      else state.saved.add(job.id);
      persist();
      saved.textContent = state.saved.has(job.id) ? "Saved" : "Save";
      updateStats();
    });
    const applied = element("button", "secondary-btn", "Mark applied");
    applied.type = "button";
    applied.addEventListener("click", async () => {
      state.applied.add(job.id);
      persist();
      applyFilters();
      const panel = document.querySelector("#applyNextPanel");
      if (panel) await renderPanel(panel);
    });
    actions.append(saved, applied);
    card.append(actions);
    return card;
  }

  async function renderQueue(panel, profile) {
    panel.innerHTML = "";
    const heading = element("div", "apply-next-heading");
    const copy = element("div");
    copy.append(
      element("p", "eyebrow", "your next application queue"),
      element("h2", "", "Apply Next"),
      element("p", "muted", profileSummary(profile) || "Private strategy loaded")
    );
    const controls = element("div", "apply-next-profile-actions");
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
    heading.append(copy, controls);
    panel.append(heading);

    const pool = candidatePool(feed.jobs, profile, state);
    const artifact = await loadInspectionArtifact();
    attachInspections(pool, artifact);
    await addBaseDistances(pool, profile);
    const ranked = YartchivesApplyNext.rankJobs(pool, profile, new Date()).slice(0, TOP_N);
    const inspectedCount = ranked.filter(result => result.inspection?.state === "inspected").length;

    const note = element(
      "p",
      "apply-next-note",
      `Showing ${ranked.length} highest-value options from ${pool.length.toLocaleString()} current candidates. ${inspectedCount} of these ${ranked.length || 0} recommendations use authoritative posting evidence; the rest use metadata fallback. Known non-${profile.targetTerm} terms plus applied/hidden jobs are excluded.`
    );
    panel.append(note);

    const list = element("div", "apply-next-list");
    ranked.forEach((result, index) => list.append(recommendationCard(result, index + 1)));
    if (!ranked.length) list.append(element("p", "muted", "No eligible Apply Next candidates are available yet."));
    panel.append(list);
  }

  async function renderPanel(panel) {
    const profile = loadProfile(localStorage);
    if (!profile) setupPanel(panel);
    else await renderQueue(panel, profile);
  }

  function init() {
    if (typeof YartchivesApplyNext === "undefined") return;
    const headerActions = document.querySelector(".header-actions");
    const main = document.querySelector("main");
    if (!headerActions || !main || document.querySelector("#applyNextBtn")) return;

    const button = element("button", "primary-btn apply-next-open", "Apply Next");
    button.id = "applyNextBtn";
    button.type = "button";
    headerActions.prepend(button);

    const panel = element("section", "panel apply-next-panel hidden");
    panel.id = "applyNextPanel";
    const stats = main.querySelector(".stats");
    main.insertBefore(panel, stats ? stats.nextSibling : main.firstChild);

    button.addEventListener("click", async () => {
      const opening = panel.classList.contains("hidden");
      panel.classList.toggle("hidden", !opening);
      button.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) {
        await renderPanel(panel);
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });

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
    INSPECTION_URL,
    TOP_N,
    validateProfile,
    loadProfile,
    saveProfile,
    knownWrongTerm,
    candidatePool,
    profileSummary,
    formatPostedDate,
    emptyInspectionArtifact,
    loadInspectionArtifact,
    attachInspections,
    addBaseDistances,
    componentMax,
    init,
  };
});