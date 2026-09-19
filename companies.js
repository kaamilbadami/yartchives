(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.YartchivesCompanies = api;
  if (typeof document !== "undefined") api.init();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function normalizedCompanyKey(job) {
    const canonical = String(job?._metadata_normalized_company || "").trim().toLowerCase();
    if (canonical) return canonical;
    return String(job?.company || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  function groupCompanies(jobs) {
    const groups = new Map();
    for (const job of jobs || []) {
      const name = String(job?.company || "").trim();
      const key = normalizedCompanyKey(job);
      if (!name || !key) continue;
      const current = groups.get(key) || { key, name, count: 0, latestPostedAt: null };
      current.count += 1;
      if (name.length < current.name.length) current.name = name;
      const posted = job?.posted_at ? new Date(job.posted_at).getTime() : NaN;
      const latest = current.latestPostedAt ? new Date(current.latestPostedAt).getTime() : NaN;
      if (Number.isFinite(posted) && (!Number.isFinite(latest) || posted > latest)) current.latestPostedAt = job.posted_at;
      groups.set(key, current);
    }
    return [...groups.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }

  function init() {
    const jobsButton = document.querySelector("#jobsViewBtn");
    const companiesButton = document.querySelector("#companiesViewBtn");
    if (!jobsButton || !companiesButton || typeof renderJobs !== "function") return;

    const params = new URLSearchParams(location.search);
    const directoryState = {
      view: params.get("view") === "companies" ? "companies" : "jobs",
      company: params.get("company") || "",
    };
    globalThis.companyDirectoryState = directoryState;

    const baseRenderJobs = renderJobs;
    const baseApplyFilters = applyFilters;

    function setToggle() {
      const companies = directoryState.view === "companies";
      jobsButton.classList.toggle("active", !companies);
      companiesButton.classList.toggle("active", companies);
      jobsButton.setAttribute("aria-pressed", String(!companies));
      companiesButton.setAttribute("aria-pressed", String(companies));
    }

    function syncUrl() {
      const url = new URL(location.href);
      if (directoryState.view === "companies") url.searchParams.set("view", "companies");
      else url.searchParams.delete("view");
      if (directoryState.company) url.searchParams.set("company", directoryState.company);
      else url.searchParams.delete("company");
      history.replaceState(null, "", url);
    }

    function renderCompanyDirectory() {
      els.jobs.innerHTML = "";
      els.jobs.className = "company-directory";
      els.loadMoreBtn.classList.add("hidden");
      const companies = groupCompanies(filtered);

      if (!companies.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.innerHTML = "<strong>No companies match these filters.</strong><br>Broaden the current filters to see more employers.";
        els.jobs.appendChild(empty);
      } else {
        const fragment = document.createDocumentFragment();
        for (const company of companies) {
          const card = document.createElement("article");
          card.className = "company-directory-card";
          const info = document.createElement("div");
          const name = document.createElement("h3");
          name.textContent = company.name;
          const meta = document.createElement("p");
          meta.textContent = `${company.count.toLocaleString()} ${company.count === 1 ? "matching opening" : "matching openings"}`;
          info.append(name, meta);

          const open = document.createElement("button");
          open.type = "button";
          open.className = "secondary-btn";
          open.textContent = "View openings";
          open.addEventListener("click", () => {
            directoryState.company = company.key;
            directoryState.view = "jobs";
            syncUrl();
            setToggle();
            applyFilters();
          });

          card.append(info, open);
          fragment.appendChild(card);
        }
        els.jobs.appendChild(fragment);
      }

      if (els.resultsTitle) els.resultsTitle.textContent = `Companies · ${companies.length.toLocaleString()}`;
      if (els.resultsNote) els.resultsNote.textContent = "Company counts reflect the current job filters.";
    }

    renderJobs = function () {
      if (directoryState.view === "companies") {
        renderCompanyDirectory();
        return;
      }
      els.jobs.className = "jobs";
      baseRenderJobs();
    };

    applyFilters = async function () {
      await baseApplyFilters();
      if (directoryState.company) {
        filtered = filtered.filter(job => normalizedCompanyKey(job) === directoryState.company);
        sortFiltered(filtered, Boolean(currentZip()));
        renderJobs();
        updateStats();
        if (els.resultsNote && directoryState.view === "jobs") {
          const companyName = filtered[0]?.company || "Selected company";
          els.resultsNote.textContent = `Showing openings from ${companyName}. Reset filters to clear this company selection.`;
        }
      } else if (directoryState.view === "companies") {
        renderCompanyDirectory();
      }
    };

    jobsButton.addEventListener("click", () => {
      directoryState.view = "jobs";
      syncUrl();
      setToggle();
      renderJobs();
    });

    companiesButton.addEventListener("click", () => {
      directoryState.company = "";
      directoryState.view = "companies";
      syncUrl();
      setToggle();
      applyFilters();
    });

    document.querySelector("#clearFiltersBtn")?.addEventListener("click", () => {
      directoryState.company = "";
      directoryState.view = "jobs";
      syncUrl();
      setToggle();
    });

    setToggle();
    if (directoryState.company || directoryState.view === "companies") applyFilters();
  }

  return { normalizedCompanyKey, groupCompanies, init };
});
