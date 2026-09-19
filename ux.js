/* Final UX layer: clearer career areas, readable cards, filter-aware stats,
   explicit posted/distance labels, and reversible local hiding. */
(() => {
  const UX_KEY = "yartchives-ux-v1";
  const LEGACY_PREF_KEY = "yartchives-student-filters-v2";

  const CAREER_AREAS = [
    ["cs", "Computer Science"],
  ];
  // Maintain the full set of valid areas so legacy state/URLs remain valid
  // even though we hide them from the primary beta UI selection.
  const ALL_KNOWN_AREAS = [
    ["cs", "Computer Science"],
    ["product-analytics", "Product / Analytics"],
    ["it-consulting", "IT / Tech Consulting"],
    ["finance-econ", "Finance / Econ"],
    ["mechanical", "Mechanical"],
    ["aero", "Aero / Astro"],
    ["electrical", "Electrical"],
    ["policy", "Policy / Government"],
    ["health", "Premed / Health"],
  ];
  const AREA_LABELS = Object.fromEntries(ALL_KNOWN_AREAS);
  const VALID_AREAS = new Set(ALL_KNOWN_AREAS.map(([key]) => key));

  function loadUxState() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(UX_KEY) || "{}"); } catch (_) {}

    let selected = Array.isArray(saved.areas) ? saved.areas.filter(key => VALID_AREAS.has(key)) : [];
    if (!selected.length) {
      const params = new URLSearchParams(location.search);
      if (params.has("areas")) {
        selected = (params.get("areas") || "").split(",").filter(key => VALID_AREAS.has(key));
      } else {
        let legacy = {};
        try { legacy = JSON.parse(localStorage.getItem(LEGACY_PREF_KEY) || "{}"); } catch (_) {}
        const legacyAreas = params.has("profiles")
          ? (params.get("profiles") || "").split(",")
          : (Array.isArray(legacy.profiles) ? legacy.profiles : []);
        for (const key of legacyAreas) {
          if (key === "tech-business") selected.push("product-analytics", "it-consulting");
          else if (VALID_AREAS.has(key)) selected.push(key);
        }

        // Beta defaults to CS-first for new visitors
        if (!selected.length) {
          selected.push("cs");
        }
      }
    }
    return { areas: [...new Set(selected)] };
  }

  let uxState = loadUxState();

  function saveUxState() {
    localStorage.setItem(UX_KEY, JSON.stringify({ areas: uxState.areas }));
  }

  function jobBlob(job) {
    return [job?.title, job?.section, job?.function_primary, job?.company]
      .filter(Boolean).join(" ").toLowerCase();
  }

  function matchesProductAnalytics(job) {
    const text = jobBlob(job);
    return /\b(product (?:manager|management|analyst|operations|strategy)|business analyst|data analyst|business intelligence|bi analyst|analytics|strategy and analytics|strategy & analytics|operations analyst|business operations|revenue operations|commercial analytics|go-to-market)\b/.test(text);
  }

  function matchesItConsulting(job) {
    const text = jobBlob(job);
    return /\b(information technology|information systems|business systems analyst|systems analyst|technology analyst|solutions engineer|sales engineer|solution consultant|technical consultant|technology consultant|implementation consultant|implementation intern|technology strategy|digital transformation|technical account|consulting intern|consultant intern)\b/.test(text);
  }

  function matchesCareerArea(job, area) {
    if (area === "product-analytics") return matchesProductAnalytics(job);
    if (area === "it-consulting") return matchesItConsulting(job);
    return (job?.profiles || []).includes(area);
  }

  function clearLegacyCareerFilter() {
    const all = [...document.querySelectorAll("#profileChips button")]
      .find(button => button.textContent.trim() === "All");
    if (all && !all.classList.contains("active")) all.click();
    else {
      try {
        const legacy = JSON.parse(localStorage.getItem(LEGACY_PREF_KEY) || "{}");
        legacy.profiles = [];
        localStorage.setItem(LEGACY_PREF_KEY, JSON.stringify(legacy));
      } catch (_) {}
    }
  }

  function renderCareerAreas() {
    if (!els.profileChips) return;
    els.profileChips.innerHTML = "";
    const selected = new Set(uxState.areas);

    const all = document.createElement("button");
    all.type = "button";
    all.textContent = "All";
    all.classList.toggle("active", selected.size === 0);
    all.setAttribute("aria-pressed", String(selected.size === 0));
    all.addEventListener("click", () => {
      uxState.areas = [];
      saveUxState();
      visibleLimit = PAGE_SIZE;
      renderCareerAreas();
      applyFilters();
    });
    els.profileChips.appendChild(all);

    for (const [key, label] of CAREER_AREAS) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      const active = selected.has(key);
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
      button.addEventListener("click", () => {
        const next = new Set(uxState.areas);
        if (next.has(key)) next.delete(key); else next.add(key);
        uxState.areas = [...next];
        saveUxState();
        visibleLimit = PAGE_SIZE;
        renderCareerAreas();
        applyFilters();
      });
      els.profileChips.appendChild(button);
    }
  }

  function relabelUi() {
    const label = document.querySelector(".profile-block .control-label-row label");
    const helper = document.querySelector(".profile-block .control-label-row .muted");
    if (label) label.textContent = "Career area";
    if (helper) helper.textContent = "Choose one or more areas. Roles can appear in multiple areas.";

    const hint = document.querySelector(".focus-hint div");
    if (hint) {
      hint.innerHTML = "<strong>Start narrow.</strong> Undergraduate-friendly internships/co-ops are the default; then narrow by career area, location, and freshness.";
    }

    const directStat = document.querySelector("#directCount")?.closest(".stat");
    directStat?.remove();

    const labels = [
      ["shownCount", "matches"],
      ["totalCount", "companies"],
      ["newCount", "saved"],
      ["savedCount", "applied"],
      ["hiddenCount", "hidden"],
    ];
    for (const [id, text] of labels) {
      const small = document.querySelector(`#${id}`)?.closest(".stat")?.querySelector("small");
      if (small) small.textContent = text;
    }

    setupStatNavigation();
  }

  function setupStatNavigation() {
    const tiles = [
      { id: "#shownCount", targetStatus: "all" },
      { id: "#newCount", targetStatus: "saved" },
      { id: "#savedCount", targetStatus: "applied" },
      { id: "#hiddenCount", targetStatus: "hidden" },
    ];

    for (const { id, targetStatus } of tiles) {
      const tile = document.querySelector(id)?.closest(".stat");
      if (!tile || tile.dataset.statNav === "true") continue;
      tile.dataset.statNav = "true";
      tile.classList.add("stat-nav");
      tile.setAttribute("role", "button");
      tile.setAttribute("tabindex", "0");

      const handleToggle = () => {
        if (targetStatus === "all") {
          state.status = "all";
        } else {
          state.status = state.status === targetStatus ? "all" : targetStatus;
        }
        visibleLimit = PAGE_SIZE;
        persist();
        syncControls();
        applyFilters();
      };

      tile.addEventListener("click", handleToggle);
      tile.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          handleToggle();
        }
      });
    }
    syncStatTiles();
  }

  function syncStatTiles() {
    const matchesTile = document.querySelector("#shownCount")?.closest(".stat");
    const savedTile = document.querySelector("#newCount")?.closest(".stat");
    const appliedTile = document.querySelector("#savedCount")?.closest(".stat");
    const hiddenTile = document.querySelector("#hiddenCount")?.closest(".stat");

    if (matchesTile) {
      const active = state.status === "all";
      matchesTile.classList.toggle("is-active", active);
      matchesTile.setAttribute("aria-pressed", String(active));
      matchesTile.title = active ? "Showing all matches" : "Click to view all matches";
    }

    if (savedTile) {
      const active = state.status === "saved";
      savedTile.classList.toggle("is-active", active);
      savedTile.setAttribute("aria-pressed", String(active));
      savedTile.title = active
        ? "Showing saved internships (click to clear status filter)"
        : "Click to filter to saved internships";
    }

    if (appliedTile) {
      const active = state.status === "applied";
      appliedTile.classList.toggle("is-active", active);
      appliedTile.setAttribute("aria-pressed", String(active));
      appliedTile.title = active
        ? "Showing applied internships (click to clear status filter)"
        : "Click to filter to applied internships";
    }

    if (hiddenTile) {
      const active = state.status === "hidden";
      hiddenTile.classList.toggle("is-active", active);
      hiddenTile.setAttribute("aria-pressed", String(active));
      hiddenTile.title = active
        ? "Showing hidden internships (click to clear status filter)"
        : "Click to filter to hidden internships";
    }
  }

  function addLocalStateNote() {
    if (document.querySelector(".local-state-note")) return;
    const controls = document.querySelector(".controls");
    if (!controls) return;
    const note = document.createElement("p");
    note.className = "local-state-note muted";
    note.textContent = "Saved, applied, and hidden are stored only in this browser.";
    controls.appendChild(note);
  }

  function showToast(message, actionLabel, action) {
    document.querySelector(".ux-toast")?.remove();
    const toast = document.createElement("div");
    toast.className = "ux-toast";
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    if (actionLabel && action) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = actionLabel;
      button.addEventListener("click", () => {
        action();
        toast.remove();
      });
      toast.appendChild(button);
    }
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 6000);
  }

  function summarizeLocation(raw) {
    const value = String(raw || "Location not listed").trim();
    const pieces = value.split(/\s*(?:;|\||\s\/\s)\s*/).map(x => x.trim()).filter(Boolean);
    if (pieces.length <= 1) return { text: value, full: value, multiple: false };
    return {
      text: `${pieces[0]} + ${pieces.length - 1} more`,
      full: value,
      multiple: true,
    };
  }

  function exactPosted(job) {
    if (!job?.posted_at) return "Posting date unavailable from this source";
    try {
      return `Posted ${new Date(job.posted_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`;
    } catch (_) {
      return `Posted ${new Date(job.posted_at).toLocaleString()}`;
    }
  }

  function replaceTechBusinessTag(card, job) {
    const tags = card.querySelector(".tags");
    if (!tags) return;
    [...tags.querySelectorAll(".tag:not(.link-quality)")].forEach(tag => {
      if (tag.textContent.trim() === "Tech + Business") tag.remove();
    });
    const labels = [];
    if (matchesProductAnalytics(job)) labels.push("Product / Analytics");
    if (matchesItConsulting(job)) labels.push("IT / Tech Consulting");
    for (const label of labels.reverse()) {
      if ([...tags.querySelectorAll(".tag")].some(tag => tag.textContent.trim() === label)) continue;
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = label;
      const quality = tags.querySelector(".link-quality");
      if (quality?.nextSibling) tags.insertBefore(tag, quality.nextSibling);
      else tags.appendChild(tag);
    }
  }

  function decorateCard(card, job) {
    const locationEl = card.querySelector(".location");
    const summary = summarizeLocation(job.location);
    if (locationEl) {
      locationEl.textContent = summary.text;
      locationEl.title = summary.full;
      locationEl.classList.toggle("multi-location", summary.multiple);
    }

    const badge = card.querySelector(".age");
    if (badge) {
      const posted = job.posted_at ? `Posted ${relativeAge(job)} ago` : "Posted date unknown";
      const hasDistance = currentZip() && Number.isFinite(job._distanceMiles);
      const distance = hasDistance ? `Distance ≈${Math.round(job._distanceMiles)} mi` : "";
      badge.textContent = distance ? `${posted} · ${distance}` : posted;
      const notes = [exactPosted(job)];
      if (hasDistance) {
        const precision = job._distancePrecision === "zip" ? "listing ZIP centroid" : "population-weighted city centroid";
        notes.push(`Straight-line distance from ${currentZip()} using ${precision}`);
        if (summary.multiple) notes.push("For multi-location roles, distance uses the nearest recognized listed location");
      }
      badge.title = notes.join(" · ");
    }

    replaceTechBusinessTag(card, job);

    const hide = card.querySelector(".hide-btn");
    if (hide) {
      const clean = hide.cloneNode(false);
      clean.className = "hide-btn secondary-btn";
      clean.type = "button";
      const isHiddenView = state.status === "hidden";
      clean.textContent = isHiddenView ? "Restore" : "Hide";
      clean.title = isHiddenView ? "Restore this listing" : "Hide this listing on this browser";
      clean.setAttribute("aria-label", clean.title);
      clean.addEventListener("click", () => {
        if (isHiddenView) {
          state.hidden.delete(job.id);
          persist();
          applyFilters();
          return;
        }
        state.hidden.add(job.id);
        persist();
        applyFilters();
        showToast("Listing hidden on this browser.", "Undo", () => {
          state.hidden.delete(job.id);
          persist();
          applyFilters();
        });
      });
      hide.replaceWith(clean);
    }
  }

  const priorRenderJobs = renderJobs;
  renderJobs = function () {
    priorRenderJobs();
    const visible = new Map(filtered.slice(0, visibleLimit).map(job => [job.id, job]));
    document.querySelectorAll(".job-card").forEach(card => {
      const job = visible.get(card.dataset.id);
      if (job) decorateCard(card, job);
    });

    const selected = uxState.areas.map(key => AREA_LABELS[key]).filter(Boolean);
    if (els.resultsTitle) {
      const base = selected.length ? selected.join(" + ") : "All opportunities";
      els.resultsTitle.textContent = state.status === "hidden" ? `${base} · Hidden` : base;
    }
  };

  updateStats = function () {
    if (!els?.shownCount) return;
    els.shownCount.textContent = filtered.length.toLocaleString();
    const companies = new Set(filtered.map(job => job.company).filter(Boolean));
    els.totalCount.textContent = companies.size.toLocaleString();
    els.newCount.textContent = filtered.filter(job => state.saved.has(job.id)).length.toLocaleString();
    els.savedCount.textContent = filtered.filter(job => state.applied.has(job.id)).length.toLocaleString();
    if (els.hiddenCount) {
      const ids = new Set((feed?.jobs || []).map(job => job.id));
      const count = [...state.hidden].filter(id => ids.has(id)).length;
      els.hiddenCount.textContent = count.toLocaleString();
    }
    syncStatTiles();
  };

  const priorSyncControls = syncControls;
  syncControls = function () {
    priorSyncControls();
    syncStatTiles();
  };

  updateFeedMeta = function () {
    if (!els.feedMeta) return;
    if (!feed?.generated_at) {
      els.feedMeta.textContent = "Feed has not been built yet.";
      return;
    }
    const jobs = Array.isArray(feed.jobs) ? feed.jobs : [];
    const direct = jobs.filter(job => job.link_kind === "direct").length;
    const pct = jobs.length ? (100 * direct / jobs.length).toFixed(1) : "0.0";
    const active = Object.values(feed.sources || {}).filter(source => source.ok && source.configured !== false).length;
    const when = new Date(feed.generated_at);
    els.feedMeta.textContent = `${jobs.length.toLocaleString()} indexed · ${pct}% direct links · Updated ${when.toLocaleString()} · ${active} active sources`;
  };

  const priorApplyFilters = applyFilters;
  applyFilters = async function () {
    await priorApplyFilters();

    const activeAreas = uxState.areas.length
      ? uxState.areas
      : CAREER_AREAS.map(([key]) => key);
    filtered = filtered.filter(job => activeAreas.some(area => matchesCareerArea(job, area)));
    sortFiltered(filtered, Boolean(currentZip()));
    renderJobs();
    updateStats();
    updateResultsNote(geoIndex && currentZip() ? geoIndex.zips.get(currentZip()) || null : null);
  };

  const priorUpdateResultsNote = updateResultsNote;
  updateResultsNote = function (origin = null) {
    priorUpdateResultsNote(origin);
    if (!els.resultsNote) return;
    if (state.status === "hidden") {
      els.resultsNote.textContent = `Showing listings you hid on this browser. ${els.resultsNote.textContent}`.trim();
    }
    if (uxState.areas.some(area => ["health", "policy", "aero"].includes(area))) {
      const coverage = "Coverage varies by career area; sparse results can reflect source coverage, not the full internship market.";
      if (!els.resultsNote.textContent.includes(coverage)) {
        els.resultsNote.textContent = `${coverage} ${els.resultsNote.textContent}`.trim();
      }
    }
  };

  renderProfiles = renderCareerAreas;

  document.querySelector("#clearFiltersBtn")?.addEventListener("click", () => {
    uxState.areas = [];
    saveUxState();
    renderCareerAreas();
  });

  document.querySelector("#shareBtn")?.addEventListener("click", () => {
    const url = new URL(location.href);
    url.searchParams.delete("profile");
    url.searchParams.delete("profiles");
    if (uxState.areas.length) url.searchParams.set("areas", uxState.areas.join(","));
    else url.searchParams.delete("areas");
    history.replaceState(null, "", url);
  }, { capture: true });

  clearLegacyCareerFilter();
  relabelUi();
  renderCareerAreas();
  addLocalStateNote();
  saveUxState();
  updateStats();
})();