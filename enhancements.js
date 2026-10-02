/* Progressive enhancements layered on top of the core Yartchives frontend. */
(() => {
  const U = window.YartchivesUtils;
  if (!U) return;

  const PREF_KEY = "yartchives-student-filters-v2";
  const LEGACY_ENGINEERING_PROFILES = new Set(["mechanical", "aero", "electrical"]);
  const normalizeLegacyProfile = key => LEGACY_ENGINEERING_PROFILES.has(key) ? "engineering" : key;
  const defaults = { education: "undergrad-friendly", opportunityType: "all", profiles: [] };
  let prefs = { ...defaults };
  try {
    const saved = JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
    prefs = { ...prefs, ...saved };
  } catch (_) {}
  if (!Array.isArray(prefs.profiles)) prefs.profiles = [];
  prefs.profiles = prefs.profiles.map(normalizeLegacyProfile).filter(key => key !== "all" && PROFILE_LABELS[key]);
  // Browse is intentionally type-agnostic: students care about relevant current opportunities,
  // not a separate internship/co-op/research taxonomy control.
  prefs.opportunityType = "all";

  const params = new URLSearchParams(location.search);
  if (params.has("edu")) prefs.education = params.get("edu") || defaults.education;
  if (params.has("profiles")) {
    prefs.profiles = (params.get("profiles") || "")
      .split(",")
      .map(normalizeLegacyProfile)
      .filter(key => key !== "all" && PROFILE_LABELS[key]);
  } else if (params.has("profile")) {
    const normalizedProfile = normalizeLegacyProfile(params.get("profile"));
    if (normalizedProfile !== "all" && PROFILE_LABELS[normalizedProfile]) {
      prefs.profiles = [normalizedProfile];
    }
  }

  // Migrate the old single-profile state once, then keep the core profile filter
  // at "all" so the enhancement layer can support match-any multi-select.
  if (!prefs.profiles.length && state.profile && state.profile !== "all" && PROFILE_LABELS[state.profile]) {
    prefs.profiles = [state.profile];
  }
  state.profile = "all";

  function savePrefs() {
    prefs.profiles = [...new Set(prefs.profiles.map(normalizeLegacyProfile))]
      .filter(key => PROFILE_LABELS[key] && key !== "all");
    localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
  }

  function option(value, label, selected) {
    const el = document.createElement("option");
    el.value = value;
    el.textContent = label;
    el.selected = selected === value;
    return el;
  }

  function setLocation(value) {
    state.location = value || "";
    visibleLimit = PAGE_SIZE;
    persist();
    syncControls();
    applyFilters();
  }

  function injectStudentControls() {
    const grid = document.querySelector(".filter-grid");
    if (!grid) return;

    const education = document.querySelector("#educationSelect");
    const type = document.querySelector("#opportunityTypeSelect");
    if (!education || !type) return;

    education.value = prefs.education;
    type.value = "all";
    education.addEventListener("change", () => {
      prefs.education = education.value;
      savePrefs();
      visibleLimit = PAGE_SIZE;
      applyFilters();
    });
  }

  function renderMultiProfiles() {
    if (!els.profileChips) return;
    els.profileChips.innerHTML = "";
    const selected = new Set(prefs.profiles);

    const all = document.createElement("button");
    all.type = "button";
    all.textContent = "All";
    all.classList.toggle("active", selected.size === 0);
    all.setAttribute("aria-pressed", String(selected.size === 0));
    all.addEventListener("click", () => {
      prefs.profiles = [];
      savePrefs();
      visibleLimit = PAGE_SIZE;
      renderMultiProfiles();
      applyFilters();
    });
    els.profileChips.appendChild(all);

    for (const [key, label] of Object.entries(PROFILE_LABELS)) {
      if (key === "all") continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = label;
      const active = selected.has(key);
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", String(active));
      btn.addEventListener("click", () => {
        const next = new Set(prefs.profiles);
        if (next.has(key)) next.delete(key); else next.add(key);
        prefs.profiles = [...next];
        savePrefs();
        visibleLimit = PAGE_SIZE;
        renderMultiProfiles();
        applyFilters();
      });
      els.profileChips.appendChild(btn);
    }
  }

  function injectLocationControls() {
    const input = document.querySelector("#locationInput");
    const label = input?.closest("label");
    const labelText = label?.querySelector("span");
    if (labelText) labelText.textContent = "ZIP / location";
    if (input) input.placeholder = "ZIP code or city";

    const quick = document.querySelector(".quick-locations");
    if (!quick || quick.dataset.enhanced === "true") return;
    quick.dataset.enhanced = "true";

    // Keep only universal shortcuts. Personal ZIPs and state fallbacks made Browse
    // feel preconfigured for one user instead of a general internship browser.
    const buttons = [...quick.querySelectorAll("button")];
    const anywhere = buttons.find(btn => btn.dataset.location === "");
    const remote = buttons.find(btn => btn.dataset.location === "Remote");
    quick.innerHTML = "";
    for (const btn of [anywhere, remote].filter(Boolean)) quick.appendChild(btn);
  }

  // Keep app.js as the single owner of geo-index loading. The canonical loader
  // consumes the deploy-built local JSON artifact, classifies failures, and is
  // shared by Browse and Apply Next.
  distanceForJob = function (job, origin, geo) {
    const result = U.distanceForJob(job, origin, geo);
    job._distancePrecision = result?.precision || null;
    return result?.miles ?? null;
  };

  // No personal-state ranking. With no location selected, newest listings win.
  sortFiltered = function (jobs, zipMode) {
    jobs.sort((a, b) => {
      if (zipMode) {
        const ad = Number.isFinite(a._distanceMiles) ? a._distanceMiles : Infinity;
        const bd = Number.isFinite(b._distanceMiles) ? b._distanceMiles : Infinity;
        if (ad !== bd) return ad - bd;
      }
      const at = a.posted_at ? new Date(a.posted_at).getTime() : 0;
      const bt = b.posted_at ? new Date(b.posted_at).getTime() : 0;
      if (at !== bt) return bt - at;
      return (a.company || "").localeCompare(b.company || "");
    });
  };

  const coreSyncControls = syncControls;
  syncControls = function () {
    coreSyncControls();
    const radiusField = els.radiusInput?.closest(".radius-field");
    if (radiusField) radiusField.classList.toggle("hidden", !currentZip());
  };

  const coreApplyFilters = applyFilters;
  applyFilters = async function () {
    state.profile = "all";
    await coreApplyFilters();
    const selectedProfiles = new Set(prefs.profiles);
    filtered = filtered.filter(job =>
      (selectedProfiles.size === 0 || (job.profiles || []).some(profile => selectedProfiles.has(profile))) &&
      U.matchesEducation(job, prefs.education) &&
      U.matchesOpportunityType(job, prefs.opportunityType)
    );
    sortFiltered(filtered, Boolean(currentZip()));
    renderJobs();
    updateStats();
    updateResultsNote(geoIndex && currentZip() ? geoIndex.zips.get(currentZip()) || null : null);
  };

  const coreUpdateResultsNote = updateResultsNote;
  updateResultsNote = function (origin = null) {
    coreUpdateResultsNote(origin);
    if (!els.resultsNote) return;
    const notes = [];
    if (prefs.education === "undergrad-friendly") {
      notes.push("Undergrad-friendly hides roles explicitly labeled graduate-only; listings with no degree level still need a requirements check.");
    } else if (prefs.education === "explicit-undergrad") {
      notes.push("Showing only listings whose title explicitly signals undergraduate/bachelor/associate eligibility.");
    }
    if (currentZip() && origin) {
      notes.push("ZIP-radius miles are straight-line estimates: listing ZIP centroid when available, otherwise a population-weighted city centroid—not driving distance.");
    }
    if (prefs.profiles.includes("health") || prefs.profiles.includes("policy") || prefs.profiles.includes("aero")) {
      notes.push("Coverage varies by field; sparse results can reflect source coverage, not the full internship market.");
    }
    if (notes.length) els.resultsNote.textContent = `${notes.join(" ")} ${els.resultsNote.textContent}`.trim();
  };

  const coreRenderJobs = renderJobs;
  renderJobs = function () {
    coreRenderJobs();

    const selected = prefs.profiles.map(key => PROFILE_LABELS[key]).filter(Boolean);
    if (els.resultsTitle) els.resultsTitle.textContent = selected.length ? selected.join(" + ") : "All opportunities";

    document.querySelectorAll(".job-card").forEach(card => {
      const job = filtered.find(item => item.id === card.dataset.id);
      if (!job) return;

      const apply = card.querySelector(".apply-btn");
      if (apply) {
        // Clone the anchor to remove the core click listener that used to mark a
        // listing as applied merely because the user opened the application.
        const clean = apply.cloneNode(true);
        if (job.link_kind === "listing" && job.listing_url) {
          clean.href = job.listing_url;
          clean.textContent = "View listing ↗";
          clean.title = "This source does not expose a verified direct employer application URL.";
        } else if (job.url) {
          clean.href = job.url;
          clean.textContent = "Apply ↗";
          clean.title = "Open the direct employer/application page";
        } else {
          clean.href = (job.source_urls || ["https://github.com/kaamilbadami/yartchives"])[0];
          clean.textContent = "Source ↗";
          clean.title = "Open the source listing";
        }
        apply.replaceWith(clean);
      }

      const badge = card.querySelector(".age");
      if (currentZip() && badge && Number.isFinite(job._distanceMiles)) {
        const current = badge.textContent.replace(/\s*·\s*[≈~]?\d+\s*mi$/, "");
        badge.textContent = `${current} · ≈${Math.round(job._distanceMiles)} mi`;
        const precision = job._distancePrecision === "zip" ? "listing ZIP centroid" : "population-weighted city centroid";
        badge.title = `${badge.title || ""}${badge.title ? " · " : ""}Straight-line distance using ${precision}`;
      }
    });
  };

  renderProfiles = renderMultiProfiles;

  document.querySelector("#clearFiltersBtn")?.addEventListener("click", () => {
    prefs = { ...defaults, profiles: [] };
    savePrefs();
    const education = document.querySelector("#educationSelect");
    const type = document.querySelector("#opportunityTypeSelect");
    if (education) education.value = prefs.education;
    if (type) type.value = prefs.opportunityType;
    renderMultiProfiles();
    syncControls();
    applyFilters();
  });

  // Preserve the enhancement filters in shared URLs.
  document.querySelector("#shareBtn")?.addEventListener("click", () => {
    const url = new URL(location.href);
    url.searchParams.delete("profile");
    if (prefs.profiles.length) url.searchParams.set("profiles", prefs.profiles.join(","));
    else url.searchParams.delete("profiles");
    if (prefs.education !== defaults.education) url.searchParams.set("edu", prefs.education);
    else url.searchParams.delete("edu");
    url.searchParams.delete("type");
    history.replaceState(null, "", url);
  }, { capture: true });

  savePrefs();
  injectStudentControls();
  injectLocationControls();
  renderMultiProfiles();
  syncControls();
  applyFilters();
})();