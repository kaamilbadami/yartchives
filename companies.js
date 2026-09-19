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

  function sortCompanies(companies, sort = "openings") {
    const list = [...(companies || [])];
    if (sort === "newest") {
      return list.sort((a, b) => {
        const at = a.latestPostedAt ? new Date(a.latestPostedAt).getTime() : 0;
        const bt = b.latestPostedAt ? new Date(b.latestPostedAt).getTime() : 0;
        return bt - at || b.count - a.count || a.name.localeCompare(b.name);
      });
    }
    if (sort === "company") {
      return list.sort((a, b) => a.name.localeCompare(b.name) || b.count - a.count);
    }
    return list.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }

  function groupCompanies(jobs, sort = "openings") {
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
    return sortCompanies([...groups.values()], sort);
  }

  function init() {
    const jobsButton = document.querySelector("#jobsViewBtn");
    const companiesButton = document.querySelector("#companiesViewBtn");
    if (!jobsButton || !companiesButton || typeof renderJobs !== "function") return;

    const params = new URLSearchParams(location.search);
    const directoryState = {
      view: params.get("view") === "companies" ? "companies" : "jobs",
      company: params.get("company") || "",
      sort: ["openings", "newest", "company"].includes(params.get("companySort")) ? params.get("companySort") : "openings",
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
      if (directoryState.view === "companies" && directoryState.sort !== "openings") url.searchParams.set("companySort", directoryState.sort);
      else url.searchParams.delete("companySort");
      history.replaceState(null, "", url);
    }

    const jobSortSelect = document.querySelector("#sortSelect");
    const jobSortField = jobSortSelect?.closest(".sort-field") || null;
    const companySortField = document.createElement("label");
    companySortField.className = "sort-field";
    companySortField.hidden = true;
    companySortField.innerHTML = '<span>Sort</span><select id="companySortSelect" aria-label="Sort companies"><option value="openings">Most openings</option><option value="newest">Newest opening</option><option value="company">Company A–Z</option></select>';
    const companySortSelect = companySortField.querySelector("select");
    companySortSelect.value = directoryState.sort;
    companySortSelect.title = "Sort companies by matching openings, newest opening, or name";
    if (jobSortField?.parentNode) jobSortField.parentNode.insertBefore(companySortField, jobSortField.nextSibling);

    function syncSortControl() {
      const companies = directoryState.view === "companies";
      if (jobSortField) jobSortField.hidden = companies;
      companySortField.hidden = !companies;
      companySortSelect.value = directoryState.sort;
    }

    companySortSelect.addEventListener("change", () => {
      directoryState.sort = ["openings", "newest", "company"].includes(companySortSelect.value)
        ? companySortSelect.value
        : "openings";
      syncUrl();
      renderCompanyDirectory();
    });

    function renderCompanyDirectory() {
      els.jobs.innerHTML = "";
      els.jobs.className = "company-directory";
      els.loadMoreBtn.classList.add("hidden");
      const companies = groupCompanies(filtered, directoryState.sort);

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
      syncSortControl();
      renderJobs();
    });

    companiesButton.addEventListener("click", () => {
      directoryState.company = "";
      directoryState.view = "companies";
      syncUrl();
      setToggle();
      syncSortControl();
      applyFilters();
    });

    document.querySelector("#clearFiltersBtn")?.addEventListener("click", () => {
      directoryState.company = "";
      directoryState.view = "jobs";
      syncUrl();
      setToggle();
      syncSortControl();
    });

    setToggle();
    syncSortControl();
    if (directoryState.company || directoryState.view === "companies") applyFilters();
  }

  return { normalizedCompanyKey, sortCompanies, groupCompanies, init };
});
