/* Canonical public-filter behavior. Local-only state (saved/applied/hidden) is never shared. */
(() => {
  const AREA_LABELS = {
    cs: "Computer Science",
    "product-analytics": "Product / Analytics",
    "it-consulting": "IT / Tech Consulting",
    "finance-econ": "Finance / Econ",
    mechanical: "Mechanical",
    aero: "Aero / Astro",
    electrical: "Electrical",
    policy: "Policy / Government",
    health: "Premed / Health",
  };

  const EDUCATION_LABELS = {
    "undergrad-friendly": "Undergrad-friendly",
    "explicit-undergrad": "Explicit undergrad",
    "graduate-only": "Graduate-only",
  };
  const OPPORTUNITY_LABELS = {
    internships: "internships + co-ops",
    internship: "internships",
    "co-op": "co-ops",
    fellowship: "fellowships",
    research: "research opportunities",
  };
  const FRESHNESS_LABELS = {
    "1": "Past 24 hours",
    "3": "Past 3 days",
    "7": "Past 7 days",
    "30": "Past 30 days",
  };
  const STALE_CT_NOTE = "Connecticut listings are ranked first when no location filter is selected.";
  const NO_LOCATION_NOTE = "No location filter is selected. Enter a ZIP code to use radius filtering or sort by distance.";

  function selectedAreaLabels() {
    return [...document.querySelectorAll("#profileChips button.active")]
      .map(button => button.textContent.trim())
      .filter(label => label && label !== "All");
  }

  function audienceOpportunityLabel() {
    const education = document.querySelector("#educationSelect")?.value || "undergrad-friendly";
    const type = document.querySelector("#opportunityTypeSelect")?.value || "internships";
    if (education === "all" && type === "all") return "All opportunities";
    const audience = EDUCATION_LABELS[education] || "";
    const opportunity = OPPORTUNITY_LABELS[type] || (type === "all" ? "opportunities" : "opportunities");
    return [audience, opportunity].filter(Boolean).join(" ");
  }

  function compactValue(value, max = 36) {
    const text = String(value || "").trim();
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  }

  function updateResultsTitle() {
    if (!els?.resultsTitle) return;
    const parts = [];
    const areas = selectedAreaLabels();
    if (areas.length) parts.push(areas.join(" + "));
    parts.push(audienceOpportunityLabel());

    const freshness = String(state.freshness || "all");
    if (FRESHNESS_LABELS[freshness]) parts.push(FRESHNESS_LABELS[freshness]);

    const locationValue = compactValue(state.location);
    if (locationValue) parts.push(locationValue);

    const query = compactValue(state.search);
    if (query) parts.push(`Search: “${query}”`);

    if (state.status === "saved") parts.push("Saved");
    else if (state.status === "applied") parts.push("Applied");
    else if (state.status === "hidden") parts.push("Hidden");

    els.resultsTitle.textContent = parts.filter(Boolean).join(" · ") || "All opportunities";
  }

  // The core layer still contains copy for an older CT-first ranking rule. The
  // final public-filter layer replaces it after all other result-note decorators run.
  const priorUpdateResultsNote = updateResultsNote;
  updateResultsNote = function (origin = null) {
    priorUpdateResultsNote(origin);
    if (els?.resultsNote) {
      els.resultsNote.textContent = els.resultsNote.textContent.replace(STALE_CT_NOTE, NO_LOCATION_NOTE);
    }
  };

  const priorRenderJobs = renderJobs;
  renderJobs = function () {
    priorRenderJobs();
    updateResultsTitle();
  };

  // A shared URL should win over a recipient's previously saved career-area state.
  const initial = new URLSearchParams(location.search);
  if (initial.has("areas")) {
    const requested = (initial.get("areas") || "").split(",").filter(key => AREA_LABELS[key]);
    const buttons = [...document.querySelectorAll("#profileChips button")];
    const all = buttons.find(button => button.textContent.trim() === "All");
    const activeLabels = new Set(buttons.filter(button => button.classList.contains("active")).map(button => button.textContent.trim()));
    const wantedLabels = new Set(requested.map(key => AREA_LABELS[key]));
    const alreadyMatches = activeLabels.size === wantedLabels.size && [...wantedLabels].every(label => activeLabels.has(label));
    if (!alreadyMatches) {
      if (all && !all.classList.contains("active")) all.click();
      for (const key of requested) {
        const button = [...document.querySelectorAll("#profileChips button")]
          .find(candidate => candidate.textContent.trim() === AREA_LABELS[key]);
        if (button && !button.classList.contains("active")) button.click();
      }
    }
  }

  updateResultsTitle();

  const share = document.querySelector("#shareBtn");
  if (!share) return;

  share.addEventListener("click", async event => {
    // Earlier enhancement layers also listen to Share. They run first in capture
    // order, then this canonical handler replaces their intermediate URL and stops
    // the old bubble-phase handler from wiping newer filter parameters.
    event.preventDefault();
    event.stopImmediatePropagation();

    const url = new URL(location.href);
    url.search = "";

    if (state.search) url.searchParams.set("q", state.search);
    if (state.location) url.searchParams.set("loc", state.location);
    if (currentZip() && String(state.radius || "50") !== "50") url.searchParams.set("miles", state.radius);
    if (String(state.freshness || "all") !== "all") url.searchParams.set("fresh", state.freshness);

    try {
      const ux = JSON.parse(localStorage.getItem("yartchives-ux-v1") || "{}");
      const areas = Array.isArray(ux.areas) ? ux.areas.filter(key => AREA_LABELS[key]) : [];
      if (areas.length) url.searchParams.set("areas", areas.join(","));
    } catch (_) {}

    const education = document.querySelector("#educationSelect")?.value || "undergrad-friendly";
    if (education !== "undergrad-friendly") url.searchParams.set("edu", education);

    const type = document.querySelector("#opportunityTypeSelect")?.value || "internships";
    if (type !== "internships") url.searchParams.set("type", type);

    const sort = document.querySelector("#sortSelect")?.value || "newest";
    if (sort !== "newest") url.searchParams.set("sort", sort);

    history.replaceState(null, "", url);
    try {
      await navigator.clipboard.writeText(url.toString());
      const old = share.textContent;
      share.textContent = "Copied";
      setTimeout(() => { share.textContent = old; }, 1200);
    } catch (_) {
      prompt("Copy this link:", url.toString());
    }
  }, { capture: true });
})();
