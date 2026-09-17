(function (root, factory) {
  const base = typeof module === "object" && module.exports
    ? require("./apply-next-location.js")
    : (root.YartchivesApplyNextLocation || root.YartchivesApplyNext);
  const api = factory(base);
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesApplyNextDimensions = api;
    const target = root.YartchivesApplyNext;
    if (target) {
      target.scoreJob = api.scoreJob;
      target.rankJobs = api.rankJobs;
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (base) {
  if (!base || typeof base.scoreJob !== "function" || typeof base.rankJobs !== "function") {
    throw new Error("Apply Next scoring dimensions require location scoring first.");
  }

  const NEUTRAL_LINK_OFFSET = 5;

  function countListed(detail, label) {
    const match = String(detail || "").match(new RegExp(`${label}: ([^;]+)`, "i"));
    if (!match) return 0;
    return match[1].split(",").map(x => x.trim()).filter(Boolean).length;
  }

  function qualificationPenalty(readiness) {
    const details = Array.isArray(readiness?.details) ? readiness.details : [];
    const unsupported = details.filter(x => /^Required gap:/i.test(x)).length;
    const cautious = details.filter(x => /^Required skill only cautiously supported:/i.test(x)).length;
    const domain = details.filter(x => /^Unverified required domain experience:/i.test(x)).length;
    let unsupportedPenalty = 0;
    for (let i = 0; i < unsupported; i += 1) unsupportedPenalty += i === 0 ? 10 : (i === 1 ? 6 : 4);
    return Math.min(30,
      Math.min(20, unsupportedPenalty)
      + Math.min(8, cautious * 4)
      + Math.min(12, domain * 6));
  }

  function scoreQualificationFit(result) {
    const prior = result?.components?.fit || { score: 0, detail: "" };
    const detail = String(prior.detail || "");
    const inspected = result?.inspection?.state === "inspected";
    if (!inspected) {
      return { score: 12, detail: "Qualification evidence not yet authoritative; neutral qualification-fit score" };
    }

    let positive = Number(prior.score || 0);
    if (/Career-area overlap:/i.test(detail)) positive -= 10;
    positive -= Math.min(15, countListed(detail, "Supported metadata matches") * 3);
    positive = Math.max(0, positive);
    const penalty = qualificationPenalty(result?.readiness);
    const score = Math.max(0, Math.min(25, 12 + positive - penalty));
    const parts = [];
    if (positive) parts.push(`Authoritative qualification support: +${positive}`);
    if (penalty) parts.push(`Required qualification gaps: -${penalty}`);
    if (!parts.length) parts.push("No authoritative qualification evidence distinguishes this posting");
    return { score, detail: parts.join("; ") };
  }

  function scoreEligibilityGate(result) {
    const detail = result?.components?.eligibility?.detail || "Eligibility checks passed";
    return { score: 20, detail: `${detail}; passed eligibility is a gate, not a ranking advantage` };
  }

  function scoreApplicationValue(result) {
    const prior = result?.components?.roi || { score: 10, detail: "Neutral application-value baseline" };
    const duplicateQualificationBonus = Math.max(0, Number(result?.competition?.differentiationBonus || 0));
    const score = Math.max(0, Math.min(15, Number(prior.score || 0) - duplicateQualificationBonus));
    const detail = String(prior.detail || "")
      .split(";")
      .map(x => x.trim())
      .filter(Boolean)
      .filter(x => !/required-skill differentiation:/i.test(x))
      .filter(x => !/specialized role aligns with supported experience/i.test(x))
      .join("; ") || "Neutral application-value baseline";
    return { score, detail };
  }

  function transform(result) {
    if (!result || result.excluded || !result.components) return result;
    const fit = scoreQualificationFit(result);
    const eligibility = scoreEligibilityGate(result);
    const roi = scoreApplicationValue(result);
    const link = {
      score: 0,
      detail: `${result.components.link?.detail || "Link provenance unavailable"}; provenance only, not a ranking signal`,
    };
    const components = { ...result.components, fit, eligibility, roi, link };
    const total = Math.max(0, Math.min(100,
      Object.values(components).reduce((sum, c) => sum + Number(c?.score || 0), 0) + NEUTRAL_LINK_OFFSET));
    const inspection = result.inspection && Array.isArray(result.inspection.evidence)
      ? { ...result.inspection, evidence: result.inspection.evidence.filter(x => !/^Qualification readiness adjustment:/i.test(String(x))) }
      : result.inspection;
    return {
      ...result,
      total,
      components,
      inspection,
      reasons: Object.entries(components).map(([name, c]) => `${name}: ${c.detail}`),
      competition: { ...(result.competition || {}), differentiationBonus: 0 },
      scoringSemantics: {
        fit: "qualification evidence only",
        role: "role preference only",
        eligibility: "gate",
        applicationValue: "market evidence only",
        link: "provenance only",
        neutralScaleOffset: NEUTRAL_LINK_OFFSET,
      },
    };
  }

  function scoreJob(job, profile, now = new Date(), context = {}) {
    return transform(base.scoreJob(job, profile, now, context));
  }

  function rankJobs(jobs, profile, now = new Date()) {
    return base.rankJobs(jobs || [], profile || {}, now)
      .map(transform)
      .filter(x => !x.excluded)
      .sort((a, b) => b.total - a.total
        || (new Date(b.job?.posted_at || 0) - new Date(a.job?.posted_at || 0))
        || String(a.job?.company || "").localeCompare(String(b.job?.company || "")));
  }

  return { NEUTRAL_LINK_OFFSET, scoreQualificationFit, scoreEligibilityGate, scoreApplicationValue, transform, scoreJob, rankJobs };
});
