/* Progressive enhancements layered on top of the core Yartchives frontend. */
(() => {
  const U = window.YartchivesUtils;
  if (!U) return;

  const PREF_KEY = "yartchives-student-filters-v2";
  const defaults = { education: "undergrad-friendly", opportunityType: "internships", profiles: [] };
  let prefs = { ...defaults };
  try {
    const saved = JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
    prefs = { ...prefs, ...saved };
  } catch (_) {}
  if (!Array.isArray(prefs.profiles)) prefs.profiles = [];

  const params = new URLSearchParams(location.search);
  if (params.has("edu")) prefs.education = params.get("edu") || defaults.education;
  if (params.has("type")) prefs.opportunityType = params.get("type") || defaults.opportunityType;
  if (params.has("profiles")) {
    prefs.profiles = (params.get("profiles") || "").split(",").filter(key => key !== "all" && PROFILE_LABELS[key]);
  } else if (params.has("profile") && params.get("profile") !== "all" && PROFILE_LABELS[params.get("profile")]) {
    prefs.profiles = [params.get("profile")];
  }

  // Migrate the old single-profile state once, then keep the core profile filter
  // at "all" so the enhancement layer can support match-any multi-select.
  if (!prefs.profiles.length && state.profile && state.profile !== "all" && PROFILE_LABELS[state.profile]) {
    prefs.profiles = [state.profile];
  }
  state.profile = "all";

  function savePrefs() {
    prefs.profiles = [...new Set(prefs.profiles)].filter(key => PROFILE_LABELS[key] && key !== "all");
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
    type.value = prefs.opportunityType;
    education.addEventListener("change", () => {
      prefs.education = education.value;
      savePrefs();
      visibleLimit = PAGE_SIZE;
      applyFilters();
    });
    type.addEventListener("change", () => {
      prefs.opportunityType = type.value;
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
    if (input) input.placeholder = "ZIP code (best), city, or state...";

    const quick = document.querySelector(".quick-locations");
    if (!quick || quick.dataset.enhanced === "true") return;
    quick.dataset.enhanced = "true";

    const buttons = [...quick.querySelectorAll("button")];
    const anywhere = buttons.find(btn => btn.dataset.location === "");
    const wilton = buttons.find(btn => btn.dataset.location === "06897");
    const collegePark = buttons.find(btn => btn.dataset.location === "20740");
    const remote = buttons.find(btn => btn.dataset.location === "Remote");
    const stateButtons = buttons.filter(btn => /^[A-Z]{2}$/.test(btn.dataset.location || ""));

    if (anywhere) anywhere.textContent = "Anywhere";
    const ct = stateButtons.find(btn => btn.dataset.location === "CT");
    if (ct) {
      ct.textContent = "CT";
      ct.title = "State fallback";
    }

    quick.innerHTML = "";
    for (const btn of [anywhere, wilton, collegePark, remote].filter(Boolean)) quick.appendChild(btn);

    const details = document.createElement("details");
    details.className = "state-backup";
    const summary = document.createElement("summary");
    summary.textContent = "State fallback";
    const inner = document.createElement("div");
    inner.className = "quick-locations state-locations";
    details.append(summary, inner);

    const existingStates = new Map(stateButtons.map(btn => [btn.dataset.location, btn]));
    if (!existingStates.has("WI")) {
      const wi = document.createElement("button");
      wi.type = "button";
      wi.dataset.location = "WI";
      wi.textContent = "WI";
      wi.addEventListener("click", () => setLocation("WI"));
      existingStates.set("WI", wi);
    }
    for (const code of ["CT", "MD", "DC", "VA", "WI", "NY", "NJ", "MA"]) {
      const btn = existingStates.get(code);
      if (btn) inner.appendChild(btn);
    }
    quick.insertAdjacentElement("afterend", details);
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
    if (prefs.opportunityType !== defaults.opportunityType) url.searchParams.set("type", prefs.opportunityType);
    else url.searchParams.delete("type");
    history.replaceState(null, "", url);
  }, { capture: true });

  savePrefs();
  injectStudentControls();
  injectLocationControls();
  renderMultiProfiles();
  syncControls();
  applyFilters();
})();