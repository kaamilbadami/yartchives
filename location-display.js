(function (root, factory) {
  const api = factory(root?.YartchivesUtils);
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesLocationDisplay = api;
    if (typeof document !== "undefined") api.init();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (U) {
  function splitLocations(raw) {
    return String(raw || "")
      .split(/\s*(?:;|\||\s\/\s)\s*/)
      .map(value => value.trim())
      .filter(Boolean);
  }

  function cleanLocationPrefix(value) {
    return String(value || "").replace(/^\d+\s+locations?\s*/i, "").trim();
  }

  function normalized(value) {
    if (U?.normalizePlace) return U.normalizePlace(value);
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
  }

  function pointMatchesPiece(piece, point) {
    if (!point?.city || !point?.state) return false;
    const text = ` ${normalized(cleanLocationPrefix(piece))} `;
    const city = normalized(point.city);
    const state = normalized(point.state);
    const stateName = normalized(U?.STATE_NAMES?.[point.state] || "");
    const cityMatch = city && text.includes(` ${city} `);
    const stateMatch = (state && text.includes(` ${state} `)) || (stateName && text.includes(` ${stateName} `));
    return Boolean(cityMatch && stateMatch);
  }

  function summarizeLocationForMatch(raw, point) {
    const full = String(raw || "Location not listed").trim();
    const pieces = splitLocations(full);
    if (pieces.length <= 1 || !point) return { matched: false, text: full, full, multiple: pieces.length > 1 };

    let index = pieces.findIndex(piece => pointMatchesPiece(piece, point));
    if (index < 0 && point?.city) {
      const city = normalized(point.city);
      const cityMatches = pieces
        .map((piece, i) => [i, ` ${normalized(cleanLocationPrefix(piece))} `])
        .filter(([, text]) => city && text.includes(` ${city} `));
      if (cityMatches.length === 1) index = cityMatches[0][0];
    }
    if (index < 0) return { matched: false, text: full, full, multiple: true };

    const matchedText = cleanLocationPrefix(pieces[index]);
    return {
      matched: true,
      matchedText,
      text: `${matchedText} + ${pieces.length - 1} more`,
      full,
      multiple: true,
    };
  }

  function init() {
    if (!U || typeof renderJobs !== "function") return;
    const priorRenderJobs = renderJobs;
    renderJobs = function () {
      priorRenderJobs();
      if (typeof currentZip !== "function" || !currentZip() || !geoIndex) return;
      const origin = geoIndex.zips?.get(currentZip());
      if (!origin) return;

      const visible = new Map((filtered || []).slice(0, visibleLimit).map(job => [job.id, job]));
      document.querySelectorAll(".job-card").forEach(card => {
        const job = visible.get(card.dataset.id);
        const locationEl = card.querySelector(".location");
        if (!job || !locationEl) return;
        const result = U.distanceForJob(job, origin, geoIndex);
        const summary = summarizeLocationForMatch(job.location, result?.point);
        if (!summary.matched) return;
        locationEl.textContent = summary.text;
        locationEl.title = `Nearest listed location to ${currentZip()}: ${summary.matchedText} · All locations: ${summary.full}`;
        locationEl.classList.add("multi-location");
      });
    };
  }

  return {
    splitLocations,
    cleanLocationPrefix,
    pointMatchesPiece,
    summarizeLocationForMatch,
    init,
  };
});
