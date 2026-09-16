/* Progressive enhancements layered on top of the core Yartchives frontend. */
(() => {
  const U = window.YartchivesUtils;
  if (!U) return;

  const PREF_KEY = "yartchives-student-filters-v1";
  const defaults = { education: "undergrad-friendly", opportunityType: "internships" };
  let prefs = { ...defaults };
  try {
    prefs = { ...prefs, ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") };
  } catch (_) {}
  const params = new URLSearchParams(location.search);
  if (params.has("edu")) prefs.education = params.get("edu") || defaults.education;
  if (params.has("type")) prefs.opportunityType = params.get("type") || defaults.opportunityType;

  function savePrefs() {
    localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
  }

  function option(value, label, selected) {
    const el = document.createElement("option");
    el.value = value;
    el.textContent = label;
    el.selected = selected === value;
    return el;
  }

  function injectStudentControls() {
    const grid = document.querySelector(".filter-grid");
    if (!grid) return;

    const existingEducation = document.querySelector("#educationSelect");
    const existingType = document.querySelector("#opportunityTypeSelect");
    if (existingEducation && existingType) {
      existingEducation.value = prefs.education;
      existingType.value = prefs.opportunityType;
      existingEducation.addEventListener("change", () => {
        prefs.education = existingEducation.value; savePrefs(); visibleLimit = PAGE_SIZE; applyFilters();
      });
      existingType.addEventListener("change", () => {
        prefs.opportunityType = existingType.value; savePrefs(); visibleLimit = PAGE_SIZE; applyFilters();
      });
      return;
    }

    const educationLabel = document.createElement("label");
    educationLabel.className = "field student-filter-field";
    educationLabel.innerHTML = "<span>Student level</span>";
    const education = document.createElement("select");
    education.id = "educationSelect";
    [
      ["undergrad-friendly", "Undergrad-friendly"],
      ["explicit-undergrad", "Explicit undergrad only"],
      ["all", "All levels"],
      ["graduate-only", "Graduate-only"],
    ].forEach(([value, label]) => education.appendChild(option(value, label, prefs.education)));
    educationLabel.appendChild(education);

    const typeLabel = document.createElement("label");
    typeLabel.className = "field student-filter-field";
    typeLabel.innerHTML = "<span>Opportunity type</span>";
    const type = document.createElement("select");
    type.id = "opportunityTypeSelect";
    [
      ["internships", "Internships + co-ops"],
      ["all", "All opportunities"],
      ["internship", "Internships only"],
      ["co-op", "Co-ops only"],
      ["fellowship", "Fellowships"],
      ["research", "Research"],
    ].forEach(([value, label]) => type.appendChild(option(value, label, prefs.opportunityType)));
    typeLabel.appendChild(type);

    const freshness = document.querySelector("#freshnessSelect")?.closest("label");
    if (freshness) {
      grid.insertBefore(educationLabel, freshness);
      grid.insertBefore(typeLabel, freshness);
    } else {
      grid.append(educationLabel, typeLabel);
    }

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

  function injectQuickZipButtons() {
    const quick = document.querySelector(".quick-locations");
    if (!quick) return;
    const entries = [
      ["06897", "Wilton · 06897", "Wilton, Connecticut"],
      ["20740", "College Park · 20740", "College Park, Maryland"],
    ];
    const ct = quick.querySelector('[data-location="CT"]');
    let anchor = ct;
    for (const [zip, label, title] of entries) {
      if (quick.querySelector(`[data-location="${zip}"]`)) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.location = zip;
      btn.textContent = label;
      btn.title = title;
      btn.className = "zip-shortcut";
      btn.addEventListener("click", () => {
        state.location = zip;
        visibleLimit = PAGE_SIZE;
        persist();
        syncControls();
        applyFilters();
      });
      if (anchor?.nextSibling) quick.insertBefore(btn, anchor.nextSibling);
      else quick.appendChild(btn);
      anchor = btn;
    }
  }

  // Replace the geo index with the tested helper implementation. This uses exact
  // listing ZIP centroids when a source includes a ZIP, and population-weighted
  // city centroids otherwise.
  loadGeoIndex = async function () {
    if (geoIndex) return geoIndex;
    if (geoLoadingPromise) return geoLoadingPromise;
    geoLoadingPromise = (async () => {
      const response = await fetch(GEO_DATA_URL, { cache: "force-cache", mode: "cors" });
      if (!response.ok) throw new Error(`ZIP data request failed (${response.status})`);
      geoIndex = U.buildGeoIndex(await response.text());
      geoError = null;
      return geoIndex;
    })().catch(error => {
      geoError = error;
      geoLoadingPromise = null;
      throw error;
    });
    return geoLoadingPromise;
  };

  distanceForJob = function (job, origin, geo) {
    const result = U.distanceForJob(job, origin, geo);
    job._distancePrecision = result?.precision || null;
    return result?.miles ?? null;
  };

  const coreApplyFilters = applyFilters;
  applyFilters = async function () {
    await coreApplyFilters();
    filtered = filtered.filter(job =>
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
    if (notes.length) els.resultsNote.textContent = `${notes.join(" ")} ${els.resultsNote.textContent}`.trim();
  };

  const coreRenderJobs = renderJobs;
  renderJobs = function () {
    coreRenderJobs();
    if (!currentZip()) return;
    document.querySelectorAll(".job-card").forEach(card => {
      const job = filtered.find(item => item.id === card.dataset.id);
      const badge = card.querySelector(".age");
      if (!job || !badge || !Number.isFinite(job._distanceMiles)) return;
      const current = badge.textContent.replace(/\s*·\s*\d+\s*mi$/, "");
      badge.textContent = `${current} · ≈${Math.round(job._distanceMiles)} mi`;
      const precision = job._distancePrecision === "zip" ? "listing ZIP centroid" : "population-weighted city centroid";
      badge.title = `${badge.title || ""}${badge.title ? " · " : ""}Straight-line distance using ${precision}`;
    });
  };

  const originalReset = els.clearFiltersBtn?.onclick;
  document.querySelector("#clearFiltersBtn")?.addEventListener("click", () => {
    prefs = { ...defaults };
    savePrefs();
    const education = document.querySelector("#educationSelect");
    const type = document.querySelector("#opportunityTypeSelect");
    if (education) education.value = prefs.education;
    if (type) type.value = prefs.opportunityType;
    applyFilters();
  });
  void originalReset;

  // Preserve the new filters in shared URLs without disturbing the core share behavior.
  document.querySelector("#shareBtn")?.addEventListener("click", () => {
    const url = new URL(location.href);
    if (prefs.education !== defaults.education) url.searchParams.set("edu", prefs.education);
    if (prefs.opportunityType !== defaults.opportunityType) url.searchParams.set("type", prefs.opportunityType);
    history.replaceState(null, "", url);
  }, { capture: true });

  injectStudentControls();
  injectQuickZipButtons();
})();
