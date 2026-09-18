(function (root, factory) {
  const scoringSource = typeof module === "object" && module.exports
    ? require("./apply-next-dimensions.js")
    : root.YartchivesApplyNext;
  const scoring = scoringSource && typeof scoringSource === "object"
    ? { ...scoringSource }
    : scoringSource;
  const locationPreferences = typeof module === "object" && module.exports
    ? require("./apply-next-location-preferences.js")
    : root.YartchivesApplyNextLocationPreferences;
  const utils = typeof module === "object" && module.exports
    ? require("./frontend-utils.js")
    : root.YartchivesUtils;
  const api = factory(scoring, locationPreferences, utils);
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesApplyNextPresentation = api;
    if (root.YartchivesApplyNext) {
      root.YartchivesApplyNext.scoreJob = api.scoreJob;
      root.YartchivesApplyNext.rankJobs = api.rankJobs;
    }
    api.captureMatchedLocationPoints(root);
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (scoring, locationPreferences, utils) {
  if (!scoring || typeof scoring.scoreJob !== "function" || typeof scoring.rankJobs !== "function") {
    throw new Error("Apply Next presentation requires final scoring dimensions first.");
  }

  const STATE_NAMES = utils?.STATE_NAMES || {};
  const STATE_BY_NAME = Object.fromEntries(
    Object.entries(STATE_NAMES).map(([code, name]) => [String(name).toLowerCase(), code])
  );

  function titleCase(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/\b[a-z]/g, ch => ch.toUpperCase());
  }

  function providerLocationText(value) {
    const parts = String(value || "").split(/\s*-\s*/).map(part => part.trim()).filter(Boolean);
    if (parts.length < 2) return null;

    const first = parts[0].toUpperCase();
    if (STATE_NAMES[first] && parts[1]) return `${titleCase(parts[1])}, ${first}`;

    if (["US", "USA", "UNITED STATES"].includes(first)) {
      if (parts.length >= 3) {
        const code = STATE_BY_NAME[parts[1].toLowerCase()];
        if (code && parts[2]) return `${titleCase(parts[2])}, ${code}`;
      }
      if (parts[1]) return titleCase(parts[1]);
    }
    return null;
  }

  function captureMatchedLocationPoints(scope) {
    if (!scope || typeof scope.distanceForJob !== "function" || !utils?.distanceForJob) return false;
    if (scope.distanceForJob.__yartchivesMatchedPointCapture) return true;
    const prior = scope.distanceForJob;
    const wrapped = function (job, origin, geo) {
      const fallbackDistance = prior(job, origin, geo);
      try {
        const authoritativeValues = typeof utils.authoritativeLocationValues === "function"
          ? utils.authoritativeLocationValues(job)
          : [];
        const resolved = utils.distanceForJob(job, origin, geo);
        const authoritativeDistance = Number(resolved?.miles);
        const hasAuthoritativeLocations = authoritativeValues.length > 0;
        const distance = hasAuthoritativeLocations
          ? (Number.isFinite(authoritativeDistance) ? authoritativeDistance : null)
          : fallbackDistance;
        const samples = Array.isArray(job?._applyNextAnchorDistanceSamples)
          ? job._applyNextAnchorDistanceSamples
          : [];
        const latest = samples[samples.length - 1];
        if (latest && hasAuthoritativeLocations) {
          latest.distanceMiles = Number.isFinite(authoritativeDistance) ? authoritativeDistance : null;
          latest.point = resolved?.point ? {
            city: resolved.point.city || null,
            state: resolved.point.state || null,
          } : null;
        } else if (latest && resolved?.point) {
          latest.point = {
            city: resolved.point.city || null,
            state: resolved.point.state || null,
          };
        }
        return distance;
      } catch (_) {
        return fallbackDistance;
      }
    };
    wrapped.__yartchivesMatchedPointCapture = true;
    wrapped.__yartchivesPriorDistanceForJob = prior;
    scope.distanceForJob = wrapped;
    return true;
  }

  function canonicalApplyUrl(job) {
    const inspection = job?._inspection || job?.inspection;
    const provider = String(inspection?.provider || inspection?.provenance?.provider || "").toLowerCase();
    const canonical = String(inspection?.provenance?.canonical_job_url || "").trim();
    if (provider === "workday" && /^https:\/\/[^/]+\.myworkdayjobs\.com\//i.test(canonical)) {
      return canonical;
    }
    return String(job?.url || "").trim();
  }

  function humanizeLocationPiece(value) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return null;
    if (/\bremote\b/i.test(text) && /^(?:us|usa|united states)?\s*-?\s*remote/i.test(text)) return "Remote";
    const providerLocation = providerLocationText(text);
    if (providerLocation) return providerLocation;

    const cityStateCountry = text.match(/^([^,]+),\s*([A-Z]{2}),\s*(?:US|USA|United States)$/i);
    if (cityStateCountry) return `${titleCase(cityStateCountry[1].trim())}, ${cityStateCountry[2].toUpperCase()}`;

    const cityStateNameCountry = text.match(/^([^,]+),\s*([A-Za-z ]+),\s*(?:US|USA|United States)$/i);
    if (cityStateNameCountry) {
      const code = STATE_BY_NAME[cityStateNameCountry[2].trim().toLowerCase()];
      if (code) return `${titleCase(cityStateNameCountry[1].trim())}, ${code}`;
    }

    const streetCityState = text.match(/^(?:\d+\s+)?[^,]+,\s*([^,]+),+\s*([A-Z]{2})$/i);
    if (streetCityState) return `${titleCase(streetCityState[1].trim())}, ${streetCityState[2].toUpperCase()}`;

    const cityStateName = text.match(/^([^,]+),\s*([A-Za-z ]+)$/);
    if (cityStateName) {
      const code = STATE_BY_NAME[cityStateName[2].trim().toLowerCase()];
      if (code) return `${titleCase(cityStateName[1].trim())}, ${code}`;
    }

    const cityState = text.match(/^([^,]+),\s*([A-Z]{2})$/i);
    if (cityState) return `${titleCase(cityState[1].trim())}, ${cityState[2].toUpperCase()}`;

    return text;
  }

  function rawLocationValues(job) {
    const authoritative = typeof utils?.authoritativeLocationValues === "function"
      ? utils.authoritativeLocationValues(job)
      : [];
    return authoritative.length ? authoritative : [String(job?.location || "")];
  }

  function locationPieces(job) {
    const pieces = rawLocationValues(job)
      .flatMap(raw => String(raw || "").split(/\s*·\s*|\s*;\s*|\s*\|\s*/))
      .map(humanizeLocationPiece)
      .filter(Boolean);
    const out = [];
    const seen = new Set();
    for (const piece of pieces) {
      const cityOnly = piece.match(/^([^,]+)$/)?.[1]?.toLowerCase();
      if (cityOnly && out.some(existing => existing.toLowerCase().startsWith(`${cityOnly},`))) continue;
      const key = piece.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(piece);
    }
    return out;
  }

  function matchedPointForResult(result, profile) {
    const anchorZip = result?.locationDecision?.anchor;
    if (!anchorZip || !locationPreferences?.orderedAnchors) return null;
    const anchors = locationPreferences.orderedAnchors(profile || {});
    const index = anchors.findIndex(anchor => anchor.zip === anchorZip);
    if (index < 0) return null;
    const samples = Array.isArray(result?.job?._applyNextAnchorDistanceSamples)
      ? result.job._applyNextAnchorDistanceSamples
      : [];
    if (samples.length < anchors.length) return null;
    return samples.slice(-anchors.length)[index]?.point || null;
  }

  function displayLocation(result, profile) {
    const pieces = locationPieces(result?.job);
    const point = matchedPointForResult(result, profile);
    const matched = point?.city && point?.state
      ? pieces.find(piece => piece.toLowerCase() === `${titleCase(point.city)}, ${String(point.state).toUpperCase()}`.toLowerCase()) || null
      : null;
    const ordered = matched
      ? [matched, ...pieces.filter(piece => piece.toLowerCase() !== matched.toLowerCase())]
      : pieces;
    const preferred = matched || ordered[0] || "Location not listed";
    return {
      text: ordered.length ? ordered.join(" · ") : preferred,
      preferred,
      all: ordered,
      matched: matched || null,
    };
  }

  function presentResult(result, profile) {
    if (!result?.job) return result;
    const location = displayLocation(result, profile || {});
    const job = {
      ...result.job,
      url: canonicalApplyUrl(result.job),
      location: location.text,
      _displayLocation: location,
    };
    return { ...result, job };
  }

  function scoreJob(job, profile, now = new Date(), context = {}) {
    return presentResult(scoring.scoreJob(job, profile, now, context), profile || {});
  }

  function rankJobs(jobs, profile, now = new Date()) {
    return scoring.rankJobs(jobs || [], profile || {}, now).map(result => presentResult(result, profile || {}));
  }

  return {
    captureMatchedLocationPoints,
    canonicalApplyUrl,
    providerLocationText,
    humanizeLocationPiece,
    rawLocationValues,
    locationPieces,
    matchedPointForResult,
    displayLocation,
    presentResult,
    scoreJob,
    rankJobs,
  };
});