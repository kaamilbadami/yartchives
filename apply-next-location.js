(function (root, factory) {
  const base = typeof module === "object" && module.exports
    ? require("./apply-next-competition.js")
    : (root.YartchivesApplyNextCompetition || root.YartchivesApplyNext);
  const api = factory(base);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.YartchivesApplyNextLocation = api;
    const target = root.YartchivesApplyNext;
    if (target && api) {
      target.scoreLocation = api.scoreLocation;
      target.scoreJob = api.scoreJob;
      target.rankJobs = api.rankJobs;
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (base) {
  if (!base || typeof base.scoreJob !== "function") {
    throw new Error("Apply Next location scoring requires competition scoring to load first.");
  }

  const originalScoreJob = base.scoreJob;

  function scoreLocation(job, profile) {
    const states = new Set(job?.states || []);
    const preferredStates = profile?.preferredStates || [];
    const stateMatch = preferredStates.find(value => states.has(value));
    if (stateMatch) return { score: 10, detail: `Preferred state: ${stateMatch}` };

    if (states.has("Remote") && profile?.remoteRelevant !== false) {
      return { score: 9, detail: "Remote opportunity" };
    }

    const distance = Number(job?._distanceMiles);
    const hasDistance = Number.isFinite(distance) && distance >= 0;
    const near = Math.max(5, Number(profile?.nearbyMiles || 50));
    if (hasDistance) {
      if (distance <= near) return { score: 10, detail: `Within ${near} miles of active base` };
      if (distance <= near * 2) return { score: 8, detail: `Within ${near * 2} miles of active base` };
    }

    if (!states.size || states.has("US")) {
      return { score: 4, detail: "Location is broad or unknown" };
    }

    if (states.has("Remote") && profile?.remoteRelevant === false) {
      return { score: 2, detail: "Remote work is not preferred" };
    }

    if (profile?.relocationAllowed) {
      if (!hasDistance) return { score: 4, detail: "Relocation is acceptable; distance is unknown" };
      const rounded = Math.round(distance);
      if (distance <= near * 4) {
        return { score: 7, detail: `Relocation about ${rounded} miles from active base` };
      }
      if (distance <= near * 8) {
        return { score: 5, detail: `Relocation about ${rounded} miles from active base` };
      }
      return { score: 3, detail: `Long-distance relocation about ${rounded} miles from active base` };
    }

    return { score: 1, detail: "Outside preferred locations" };
  }

  function scoreJob(job, profile, now = new Date(), context = {}) {
    const result = originalScoreJob(job, profile, now, context);
    if (!result || result.excluded || !result.components) return result;

    const location = scoreLocation(job, profile || {});
    const prior = Number(result.components?.location?.score || 0);
    const components = { ...result.components, location };
    const total = Math.max(0, Math.min(100, Number(result.total || 0) - prior + location.score));
    const reasons = Array.isArray(result.reasons)
      ? result.reasons.map(reason => String(reason).startsWith("location:")
        ? `location: ${location.detail}`
        : reason)
      : [];

    return { ...result, total, components, reasons };
  }

  function rankJobs(jobs, profile, now = new Date()) {
    const pool = jobs || [];
    const context = typeof base.buildCompetitionContext === "function"
      ? base.buildCompetitionContext(pool)
      : {};
    return pool
      .map(job => scoreJob(job, profile, now, context))
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
    scoreLocation,
    scoreJob,
    rankJobs,
  };
});
