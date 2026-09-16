/* Canonical share-view behavior. Local-only state (saved/applied/hidden) is never shared. */
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
    if (String(state.freshness || "7") !== "7") url.searchParams.set("fresh", state.freshness);

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