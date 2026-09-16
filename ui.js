/* Lightweight presentation layer for sorting, feed-quality stats, and card polish. */
(() => {
  const UI_KEY = "yartchives-ui-v1";
  const allowedSorts = new Set(["newest", "oldest", "company", "closest"]);
  let uiState = { sort: "newest" };

  try {
    const saved = JSON.parse(localStorage.getItem(UI_KEY) || "{}");
    if (allowedSorts.has(saved.sort)) uiState.sort = saved.sort;
  } catch (_) {}

  const params = new URLSearchParams(location.search);
  if (allowedSorts.has(params.get("sort"))) uiState.sort = params.get("sort");

  function persistUi() {
    localStorage.setItem(UI_KEY, JSON.stringify(uiState));
  }

  function postedTime(job) {
    const value = job?.posted_at ? new Date(job.posted_at).getTime() : 0;
    return Number.isFinite(value) ? value : 0;
  }

  function newestFirst(a, b) {
    const delta = postedTime(b) - postedTime(a);
    return delta || (a.company || "").localeCompare(b.company || "") || (a.title || "").localeCompare(b.title || "");
  }

  function oldestFirst(a, b) {
    const at = postedTime(a) || Number.MAX_SAFE_INTEGER;
    const bt = postedTime(b) || Number.MAX_SAFE_INTEGER;
    const delta = at - bt;
    return delta || (a.company || "").localeCompare(b.company || "") || (a.title || "").localeCompare(b.title || "");
  }

  function companyFirst(a, b) {
    return (a.company || "").localeCompare(b.company || "") || newestFirst(a, b);
  }

  function closestFirst(a, b) {
    const ad = Number.isFinite(a._distanceMiles) ? a._distanceMiles : Infinity;
    const bd = Number.isFinite(b._distanceMiles) ? b._distanceMiles : Infinity;
    return ad - bd || newestFirst(a, b);
  }

  // The enhancement layer intentionally leaves ranking neutral. This adds only
  // explicit user-selected ordering; there is no hidden score or personalization.
  sortFiltered = function (jobs, zipMode) {
    const sort = uiState.sort === "closest" && !zipMode ? "newest" : uiState.sort;
    if (sort === "oldest") jobs.sort(oldestFirst);
    else if (sort === "company") jobs.sort(companyFirst);
    else if (sort === "closest") jobs.sort(closestFirst);
    else jobs.sort(newestFirst);
  };

  function addDirectStat() {
    const stats = document.querySelector(".stats");
    if (!stats || document.querySelector("#directCount")) return;
    const stat = document.createElement("div");
    stat.className = "stat direct-stat";
    stat.innerHTML = '<span id="directCount">0</span><small>direct apply</small>';
    const savedStat = document.querySelector("#savedCount")?.closest(".stat");
    stats.insertBefore(stat, savedStat || null);
  }

  function addSortControl() {
    const header = document.querySelector(".results-header");
    const reset = document.querySelector("#clearFiltersBtn");
    if (!header || !reset || document.querySelector("#sortSelect")) return;

    const tools = document.createElement("div");
    tools.className = "results-tools";
    const label = document.createElement("label");
    label.className = "sort-field";
    label.innerHTML = '<span>Sort</span><select id="sortSelect" aria-label="Sort opportunities"><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="company">Company A–Z</option><option value="closest">Closest</option></select>';
    tools.append(label, reset);
    header.appendChild(tools);

    const select = label.querySelector("select");
    select.value = uiState.sort;
    select.addEventListener("change", () => {
      uiState.sort = allowedSorts.has(select.value) ? select.value : "newest";
      persistUi();
      visibleLimit = PAGE_SIZE;
      applyFilters();
    });
  }

  function updateSortAvailability() {
    const select = document.querySelector("#sortSelect");
    if (!select) return;
    const closest = select.querySelector('option[value="closest"]');
    const zipMode = Boolean(currentZip());
    if (closest) closest.disabled = !zipMode;
    if (!zipMode && uiState.sort === "closest") {
      uiState.sort = "newest";
      select.value = "newest";
      persistUi();
    }
    select.title = zipMode ? "Sort by posting date, company, or ZIP distance" : "Enter a ZIP code to enable distance sorting";
  }

  function isDirect(job) {
    return job?.link_kind === "direct" || (Boolean(job?.url) && job?.link_kind !== "listing" && job?.link_kind !== "source");
  }

  const priorUpdateStats = updateStats;
  updateStats = function () {
    priorUpdateStats();
    const directCount = document.querySelector("#directCount");
    if (!directCount) return;
    const count = filtered.filter(isDirect).length;
    directCount.textContent = count.toLocaleString();
    const pct = filtered.length ? Math.round((count / filtered.length) * 100) : 0;
    directCount.closest(".stat").title = `${pct}% of the current matches have a verified direct application link.`;
  };

  function decorateCards() {
    const visible = new Map(filtered.slice(0, visibleLimit).map(job => [job.id, job]));
    document.querySelectorAll(".job-card").forEach(card => {
      const job = visible.get(card.dataset.id);
      if (!job) return;
      const kind = isDirect(job) ? "direct" : (job.link_kind === "listing" ? "listing" : "source");
      card.dataset.linkKind = kind;
      card.classList.toggle("is-saved", state.saved.has(job.id));
      card.classList.toggle("is-applied", state.applied.has(job.id));

      if (!card.querySelector(".link-quality")) {
        const tag = document.createElement("span");
        tag.className = `tag link-quality ${kind}`;
        if (kind === "direct") tag.textContent = "Direct apply";
        else if (kind === "listing") tag.textContent = "Listing link";
        else tag.textContent = "Source only";
        const tags = card.querySelector(".tags");
        if (tags) tags.prepend(tag);
      }
    });
  }

  const priorRenderJobs = renderJobs;
  renderJobs = function () {
    priorRenderJobs();
    decorateCards();
  };

  const priorSyncControls = syncControls;
  syncControls = function () {
    priorSyncControls();
    updateSortAvailability();
  };

  addDirectStat();
  addSortControl();
  updateSortAvailability();

  document.querySelector("#clearFiltersBtn")?.addEventListener("click", () => {
    uiState.sort = "newest";
    persistUi();
    const select = document.querySelector("#sortSelect");
    if (select) select.value = "newest";
    applyFilters();
  });

  // The core Share view code keeps unknown query parameters, so setting this in
  // capture phase makes the explicit sort choice travel with shared URLs.
  document.querySelector("#shareBtn")?.addEventListener("click", () => {
    const url = new URL(location.href);
    if (uiState.sort !== "newest") url.searchParams.set("sort", uiState.sort);
    else url.searchParams.delete("sort");
    history.replaceState(null, "", url);
  }, { capture: true });

  persistUi();
  updateStats();
})();