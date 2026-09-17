(function (root, factory) {
  const locationBase = typeof module === "object" && module.exports
    ? require("./apply-next-location.js")
    : (root.YartchivesApplyNextLocation || root.YartchivesApplyNext);
  const competitionBase = typeof module === "object" && module.exports
    ? require("./apply-next-competition.js")
    : (root.YartchivesApplyNextCompetition || root.YartchivesApplyNext);
  const api = factory(locationBase, competitionBase);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.YartchivesApplyNextLocationPreferences = api;
    root.YartchivesApplyNextLocation = api;
    const target = root.YartchivesApplyNext;
    if (target && api) {
      target.scoreLocation = api.scoreLocation;
      target.scoreJob = api.scoreJob;
      target.rankJobs = api.rankJobs;
    }
    api.captureGlobalDistanceSamples(root);
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (base, competition) {
  if (!base || typeof base.scoreJob !== "function" || typeof base.scoreLocation !== "function") {
    throw new Error("Apply Next location preferences require base location scoring first.");
  }

  const MAX_CAPTURED_SAMPLES = 24;

  function numberOr(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function normalizeZip(value) {
    const text = String(value || "").trim();
    return /^\d{5}$/.test(text) ? text : null;
  }

  function clampLocationScore(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, Math.min(15, parsed)) : null;
  }

  function customLocationMode(profile) {
    const mode = String(profile?.locationMode || "").trim().toLowerCase();
    if (mode === "normal") return false;
    if (mode === "custom") return true;
    return Array.isArray(profile?.locationAnchors) && profile.locationAnchors.length > 0;
  }

  function anchorLabel(anchor, index) {
    const label = String(anchor?.label || "").trim();
    if (label && label !== anchor?.zip) return label;
    const ordinal = index === 0 ? "Primary base" : (index === 1 ? "Secondary base" : `Base ${index + 1}`);
    return anchor?.zip ? `${ordinal} (${anchor.zip})` : ordinal;
  }

  function orderedAnchors(profile) {
    const commonMiles = Math.max(5, Math.min(500, numberOr(profile?.nearbyMiles, 50)));
    const explicit = customLocationMode(profile) && Array.isArray(profile?.locationAnchors) ? profile.locationAnchors : [];
    const anchors = explicit.map((anchor, index) => {
      const zip = normalizeZip(anchor?.zip || anchor?.baseZip);
      if (!zip) return null;
      return {
        zip,
        label: String(anchor?.label || "").trim() || null,
        commuteMiles: Math.max(5, Math.min(500, numberOr(anchor?.commuteMiles ?? anchor?.nearbyMiles, commonMiles))),
        locationScore: clampLocationScore(anchor?.locationScore ?? anchor?.score),
        order: index,
      };
    }).filter(Boolean);
    if (anchors.length) return anchors;

    const zips = (profile?.baseZips || []).map(normalizeZip).filter(Boolean);
    const labels = Array.isArray(profile?.baseLabels) ? profile.baseLabels : [];
    return zips.map((zip, index) => ({
      zip,
      label: String(labels[index] || "").trim() || null,
      commuteMiles: commonMiles,
      locationScore: null,
      order: index,
    }));
  }

  function relocationPreference(profile) {
    const explicit = String(profile?.relocationPreference || "").trim().toLowerCase();
    if (["not_open", "open", "preferred"].includes(explicit)) return explicit;
    return profile?.relocationAllowed === false ? "not_open" : "open";
  }

  function remotePreference(profile) {
    const explicit = String(profile?.remotePreference || "").trim().toLowerCase();
    if (["preferred", "acceptable", "not_preferred"].includes(explicit)) return explicit;
    return profile?.remoteRelevant === false ? "not_preferred" : "acceptable";
  }

  function captureGlobalDistanceSamples(scope) {
    if (!scope || typeof scope.distanceForJob !== "function") return false;
    if (scope.distanceForJob.__yartchivesAnchorCapture) return true;
    const prior = scope.distanceForJob;
    const wrapped = function (job, origin, geo) {
      const distance = prior(job, origin, geo);
      if (job && typeof job === "object" && origin) {
        const samples = Array.isArray(job._applyNextAnchorDistanceSamples)
          ? job._applyNextAnchorDistanceSamples
          : [];
        samples.push({
          distanceMiles: Number.isFinite(distance) ? distance : null,
          originState: origin.state || null,
          originCity: origin.city || null,
        });
        if (samples.length > MAX_CAPTURED_SAMPLES) {
          samples.splice(0, samples.length - MAX_CAPTURED_SAMPLES);
        }
        job._applyNextAnchorDistanceSamples = samples;
      }
      return distance;
    };
    wrapped.__yartchivesAnchorCapture = true;
    wrapped.__yartchivesPriorDistanceForJob = prior;
    scope.distanceForJob = wrapped;
    return true;
  }

  function explicitAnchorDistances(job, anchors) {
    const values = Array.isArray(job?._locationAnchorDistances) ? job._locationAnchorDistances : [];
    if (!values.length) return [];
    const byZip = new Map();
    for (const item of values) {
      const zip = normalizeZip(item?.zip || item?.baseZip);
      const rawDistance = item?.distanceMiles ?? item?.miles;
      if (rawDistance === null || rawDistance === undefined || rawDistance === "") continue;
      const distance = Number(rawDistance);
      if (zip && Number.isFinite(distance) && distance >= 0) byZip.set(zip, distance);
    }
    if (byZip.size) {
      return anchors
        .map((anchor, index) => byZip.has(anchor.zip) ? { anchor, index, distanceMiles: byZip.get(anchor.zip) } : null)
        .filter(Boolean);
    }
    if (values.length < anchors.length) return [];
    return anchors.map((anchor, index) => {
      const rawDistance = values[index]?.distanceMiles ?? values[index]?.miles ?? values[index];
      if (rawDistance === null || rawDistance === undefined || rawDistance === "") return null;
      const distance = Number(rawDistance);
      return Number.isFinite(distance) && distance >= 0 ? { anchor, index, distanceMiles: distance } : null;
    }).filter(Boolean);
  }

  function capturedAnchorDistances(job, anchors) {
    const samples = Array.isArray(job?._applyNextAnchorDistanceSamples)
      ? job._applyNextAnchorDistanceSamples
      : [];
    if (!anchors.length || samples.length < anchors.length) return [];
    const recent = samples.slice(-anchors.length);
    return anchors.map((anchor, index) => {
      const rawDistance = recent[index]?.distanceMiles;
      if (rawDistance === null || rawDistance === undefined || rawDistance === "") return null;
      const distance = Number(rawDistance);
      return Number.isFinite(distance) && distance >= 0 ? { anchor, index, distanceMiles: distance } : null;
    }).filter(Boolean);
  }

  function anchorDistances(job, profile) {
    const anchors = orderedAnchors(profile);
    if (!anchors.length) return [];
    return explicitAnchorDistances(job, anchors).length
      ? explicitAnchorDistances(job, anchors)
      : capturedAnchorDistances(job, anchors);
  }

  function isRemote(job) {
    return (job?.states || []).includes("Remote") || /\bremote\b/i.test(String(job?.location || ""));
  }

  function remoteScore(profile) {
    const preference = remotePreference(profile);
    if (preference === "preferred") return { score: 10, detail: "Remote work is preferred" };
    if (preference === "acceptable") return { score: 8, detail: "Remote work is acceptable" };
    return { score: 3, detail: "Remote work is not preferred" };
  }

  function anchorScore(anchor, index) {
    if (Number.isFinite(anchor?.locationScore)) return anchor.locationScore / 1.5;
    if (index <= 0) return 10;
    if (index === 1) return 9;
    return 8;
  }

  function scoreWithAnchors(job, profile, anchors) {
    if (isRemote(job)) return remoteScore(profile);

    const distances = anchorDistances(job, profile);
    if (distances.length === anchors.length) {
      const commutable = distances
        .filter(item => item.distanceMiles <= item.anchor.commuteMiles)
        .sort((a, b) => anchorScore(b.anchor, b.index) - anchorScore(a.anchor, a.index)
          || a.index - b.index
          || a.distanceMiles - b.distanceMiles);
      if (commutable.length) {
        const best = commutable[0];
        return {
          score: anchorScore(best.anchor, best.index),
          detail: `Within ${best.anchor.commuteMiles} miles of ${anchorLabel(best.anchor, best.index)}`,
          anchor: best.anchor.zip,
        };
      }

      const relocation = relocationPreference(profile);
      const nearest = distances.slice().sort((a, b) => a.distanceMiles - b.distanceMiles)[0];
      const rounded = Math.round(nearest.distanceMiles);
      if (relocation === "not_open") {
        return {
          score: 0,
          excluded: true,
          detail: `Outside all commute bases; relocation is turned off (nearest is about ${rounded} miles from ${anchorLabel(nearest.anchor, nearest.index)})`,
        };
      }

      const ratio = nearest.distanceMiles / Math.max(5, nearest.anchor.commuteMiles);
      if (relocation === "preferred") {
        const score = ratio <= 2 ? 8 : (ratio <= 4 ? 7 : 6);
        return { score, detail: `Relocation is preferred; nearest base is about ${rounded} miles away` };
      }
      const score = ratio <= 2 ? 6 : (ratio <= 4 ? 4 : 2);
      return { score, detail: `Relocation is acceptable; nearest base is about ${rounded} miles away` };
    }

    const states = typeof base.reliableStates === "function" ? base.reliableStates(job) : new Set();
    const preferredStates = profile?.preferredStates || [];
    const stateMatch = preferredStates.find(value => states.has(value));
    if (stateMatch) {
      return { score: 6, detail: `Preferred state: ${stateMatch}; commute to an anchor is not yet verified` };
    }

    const rawStates = new Set(job?.states || []);
    if (!states.size && (!rawStates.size || rawStates.has("US"))) {
      return { score: 4, detail: "Location is broad or unknown; anchor commute cannot be verified" };
    }

    if (relocationPreference(profile) === "not_open") {
      return { score: 2, detail: "Location is outside known anchor evidence; relocation is turned off but distance is unverified" };
    }
    return { score: 4, detail: "Anchor commute distance is unavailable; relocation remains possible" };
  }

  function scoreLocation(job, profile) {
    const anchors = orderedAnchors(profile);
    if (!anchors.length) return base.scoreLocation(job, profile || {});
    return scoreWithAnchors(job, profile || {}, anchors);
  }

  function scoreJob(job, profile, now = new Date(), context = {}) {
    const result = base.scoreJob(job, profile, now, context);
    if (!result || result.excluded || !result.components) return result;
    const effectiveJob = result.job || job;
    const location = scoreLocation(effectiveJob, profile || {});
    const prior = Number(result.components?.location?.score || 0);
    const components = { ...result.components, location: { score: location.score, detail: location.detail } };
    if (location.excluded) {
      return {
        ...result,
        total: 0,
        excluded: true,
        components,
        reasons: [location.detail, ...(result.reasons || [])],
        locationDecision: location,
      };
    }
    const total = Math.max(0, Math.min(100, Number(result.total || 0) - prior + location.score));
    const reasons = Array.isArray(result.reasons)
      ? result.reasons.map(reason => String(reason).startsWith("location:")
        ? `location: ${location.detail}`
        : reason)
      : [];
    return { ...result, total, components, reasons, locationDecision: location };
  }

  function rankJobs(jobs, profile, now = new Date()) {
    const pool = typeof base.dedupeCanonicalJobs === "function"
      ? base.dedupeCanonicalJobs(jobs || []).filter(base.hasAuthoritativeInspection)
      : (jobs || []);
    const context = typeof competition?.buildCompetitionContext === "function"
      ? competition.buildCompetitionContext(pool)
      : {};
    return pool
      .map(job => scoreJob(job, profile || {}, now, context))
      .filter(result => !result.excluded)
      .sort((a, b) => {
        if (b.total !== a.total) return b.total - a.total;
        const bPosted = b.job?.posted_at ? new Date(b.job.posted_at).getTime() : 0;
        const aPosted = a.job?.posted_at ? new Date(a.job.posted_at).getTime() : 0;
        if (bPosted !== aPosted) return bPosted - aPosted;
        return String(a.job?.company || "").localeCompare(String(b.job?.company || ""))
          || String(a.job?.title || "").localeCompare(String(b.job?.title || ""));
      });
  }

  return {
    ...base,
    orderedAnchors,
    relocationPreference,
    remotePreference,
    customLocationMode,
    captureGlobalDistanceSamples,
    anchorDistances,
    scoreLocation,
    scoreJob,
    rankJobs,
  };
});