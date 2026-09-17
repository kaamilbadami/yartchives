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
  const FINAL_LOCATION_MAX = 20;
  const DEFAULT_REMOTE_SCORE = 20;
  const DEFAULT_RELOCATION_SCORE = 8;
  const DEFAULT_UNKNOWN_SCORE = 10;
  const DEFAULT_MIN_COMMUTE_SCORE = 16;
  const LOCATION_PREFERENCES_VERSION = 2;

  const RELOCATION_REGIONS = Object.freeze({
    new_england: Object.freeze({ label: "New England", states: Object.freeze(["CT", "ME", "MA", "NH", "RI", "VT"]) }),
    mid_atlantic: Object.freeze({ label: "Mid-Atlantic", states: Object.freeze(["DE", "DC", "MD", "NJ", "NY", "PA", "VA", "WV"]) }),
    southeast: Object.freeze({ label: "Southeast", states: Object.freeze(["AL", "AR", "FL", "GA", "KY", "LA", "MS", "NC", "SC", "TN"]) }),
    midwest: Object.freeze({ label: "Midwest", states: Object.freeze(["IL", "IN", "IA", "KS", "MI", "MN", "MO", "NE", "ND", "OH", "SD", "WI"]) }),
    south_central: Object.freeze({ label: "South Central", states: Object.freeze(["OK", "TX"]) }),
    mountain_west: Object.freeze({ label: "Mountain West", states: Object.freeze(["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY"]) }),
    west_coast: Object.freeze({ label: "West Coast / Pacific", states: Object.freeze(["AK", "CA", "HI", "OR", "WA"]) }),
  });

  const REGION_BY_STATE = Object.freeze(Object.fromEntries(
    Object.entries(RELOCATION_REGIONS).flatMap(([region, meta]) => meta.states.map(state => [state, region]))
  ));

  function numberOr(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value || 0)));
  }

  function normalizeZip(value) {
    const text = String(value || "").trim();
    return /^\d{5}$/.test(text) ? text : null;
  }

  function clampFinalScore(value, fallback = DEFAULT_UNKNOWN_SCORE) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.round(clamp(parsed, 0, FINAL_LOCATION_MAX)) : fallback;
  }

  function customLocationMode(profile) {
    const mode = String(profile?.locationMode || "").trim().toLowerCase();
    if (mode === "normal" || mode === "default") return false;
    if (mode === "custom") return true;
    return Array.isArray(profile?.locationAnchors) && profile.locationAnchors.length > 0;
  }

  function anchorLabel(anchor, index) {
    const label = String(anchor?.label || "").trim();
    if (label && label !== anchor?.zip) return label;
    const ordinal = index === 0 ? "Primary base" : (index === 1 ? "Secondary base" : `Base ${index + 1}`);
    return anchor?.zip ? `${ordinal} (${anchor.zip})` : ordinal;
  }

  function legacyAnchorScore(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return null;
    return Math.round((clamp(parsed, 0, 15) / 15) * FINAL_LOCATION_MAX);
  }

  function anchorFinalScore(profile, anchor, index) {
    const raw = anchor?.locationScore ?? anchor?.score;
    if (Number.isFinite(Number(raw))) {
      return Number(profile?.locationPreferencesVersion || 0) >= LOCATION_PREFERENCES_VERSION
        ? clampFinalScore(raw)
        : legacyAnchorScore(raw);
    }
    if (!customLocationMode(profile)) return FINAL_LOCATION_MAX;
    if (index === 0) return FINAL_LOCATION_MAX;
    if (index === 1) return 18;
    return 16;
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
        locationScore: anchorFinalScore(profile, anchor, index),
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
      locationScore: FINAL_LOCATION_MAX,
      order: index,
    }));
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
    const explicit = explicitAnchorDistances(job, anchors);
    return explicit.length ? explicit : capturedAnchorDistances(job, anchors);
  }

  function isRemote(job) {
    return (job?.states || []).includes("Remote") || /\bremote\b/i.test(String(job?.location || ""));
  }

  function reliableState(job) {
    const states = typeof base.reliableStates === "function" ? [...base.reliableStates(job)] : [];
    return states.length === 1 ? states[0] : null;
  }

  function regionForState(state) {
    return REGION_BY_STATE[String(state || "").toUpperCase()] || null;
  }

  function regionScore(profile, job) {
    const region = regionForState(reliableState(job));
    const scores = profile?.relocationRegionScores && typeof profile.relocationRegionScores === "object"
      ? profile.relocationRegionScores
      : {};
    if (region && Number.isFinite(Number(scores[region]))) {
      return { score: clampFinalScore(scores[region]), region };
    }
    return { score: clampFinalScore(profile?.relocationScore, DEFAULT_RELOCATION_SCORE), region };
  }

  function defaultCommuteScore(distanceMiles, commuteMiles) {
    const limit = Math.max(5, Number(commuteMiles || 50));
    if (!Number.isFinite(distanceMiles) || distanceMiles < 0) return DEFAULT_UNKNOWN_SCORE;
    if (distanceMiles > limit) return DEFAULT_RELOCATION_SCORE;
    const ratio = clamp(distanceMiles / limit, 0, 1);
    return Math.round(FINAL_LOCATION_MAX - ((FINAL_LOCATION_MAX - DEFAULT_MIN_COMMUTE_SCORE) * ratio));
  }

  function scoreDefaultLocation(job, profile) {
    if (isRemote(job)) return { score: DEFAULT_REMOTE_SCORE, detail: "Remote opportunity" };

    const anchors = orderedAnchors(profile);
    const home = anchors[0];
    if (!home) return { score: DEFAULT_UNKNOWN_SCORE, detail: "Home commute base is not configured" };

    const distances = anchorDistances(job, { ...profile, baseZips: [home.zip], baseLabels: [home.label || home.zip], locationAnchors: [] });
    const distance = distances[0]?.distanceMiles;
    if (!Number.isFinite(distance)) {
      return { score: DEFAULT_UNKNOWN_SCORE, detail: "Commute distance is not yet verified" };
    }

    if (distance <= home.commuteMiles) {
      const score = defaultCommuteScore(distance, home.commuteMiles);
      return {
        score,
        detail: `Commutable from ${anchorLabel(home, 0)}: about ${Math.round(distance)} miles`,
      };
    }

    return {
      score: DEFAULT_RELOCATION_SCORE,
      detail: `Outside the ${home.commuteMiles}-mile commute range; would require moving`,
    };
  }

  function customRemoteScore(profile) {
    if (Number.isFinite(Number(profile?.remoteScore))) return clampFinalScore(profile.remoteScore);
    const legacy = String(profile?.remotePreference || "").trim().toLowerCase();
    if (legacy === "not_preferred") return 6;
    if (legacy === "acceptable") return 16;
    return 20;
  }

  function scoreCustomLocation(job, profile) {
    if (isRemote(job)) {
      const score = customRemoteScore(profile);
      return { score, detail: `Remote score: ${score}/20` };
    }

    const anchors = orderedAnchors(profile);
    if (!anchors.length) return { score: DEFAULT_UNKNOWN_SCORE, detail: "No custom commute bases are configured" };
    const distances = anchorDistances(job, profile);

    if (distances.length === anchors.length) {
      const commutable = distances
        .filter(item => item.distanceMiles <= item.anchor.commuteMiles)
        .sort((a, b) => b.anchor.locationScore - a.anchor.locationScore
          || a.distanceMiles - b.distanceMiles
          || a.index - b.index);
      if (commutable.length) {
        const best = commutable[0];
        return {
          score: best.anchor.locationScore,
          detail: `Within ${best.anchor.commuteMiles} miles of ${anchorLabel(best.anchor, best.index)}`,
          anchor: best.anchor.zip,
        };
      }

      const nearest = distances.slice().sort((a, b) => a.distanceMiles - b.distanceMiles)[0];
      if (profile?.excludeRelocation === true) {
        return {
          score: 0,
          excluded: true,
          detail: `Outside every custom commute base; moving is excluded (nearest base is about ${Math.round(nearest.distanceMiles)} miles away)`,
        };
      }

      const relocation = regionScore(profile, job);
      const regionLabel = relocation.region ? RELOCATION_REGIONS[relocation.region]?.label : null;
      return {
        score: relocation.score,
        detail: regionLabel
          ? `${regionLabel} relocation preference: ${relocation.score}/20`
          : `Default relocation preference: ${relocation.score}/20`,
      };
    }

    return { score: DEFAULT_UNKNOWN_SCORE, detail: "Location is known, but commute distance to custom bases is not yet verified" };
  }

  function scoreLocation(job, profile) {
    return customLocationMode(profile)
      ? scoreCustomLocation(job, profile || {})
      : scoreDefaultLocation(job, profile || {});
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
    FINAL_LOCATION_MAX,
    DEFAULT_REMOTE_SCORE,
    DEFAULT_RELOCATION_SCORE,
    DEFAULT_UNKNOWN_SCORE,
    DEFAULT_MIN_COMMUTE_SCORE,
    LOCATION_PREFERENCES_VERSION,
    RELOCATION_REGIONS,
    orderedAnchors,
    customLocationMode,
    captureGlobalDistanceSamples,
    anchorDistances,
    regionForState,
    defaultCommuteScore,
    scoreDefaultLocation,
    scoreCustomLocation,
    scoreLocation,
    scoreJob,
    rankJobs,
  };
});
