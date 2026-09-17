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
      target.SCORE_MAXIMA = api.SCORE_MAXIMA;
      target.scoreJob = api.scoreJob;
      target.rankJobs = api.rankJobs;
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (base) {
  if (!base || typeof base.scoreJob !== "function" || typeof base.rankJobs !== "function") {
    throw new Error("Apply Next scoring dimensions require location scoring first.");
  }

  const SCORE_MAXIMA = Object.freeze({
    fit: 40,
    eligibility: 0,
    freshness: 10,
    roi: 15,
    role: 20,
    location: 15,
    link: 0,
  });

  const LEGACY_MAXIMA = Object.freeze({
    fit: 25,
    freshness: 15,
    roi: 15,
    role: 10,
    location: 10,
  });

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value || 0)));
  }

  function scaleScore(value, fromMax, toMax) {
    if (!toMax) return 0;
    if (!fromMax) return clamp(value, 0, toMax);
    return Math.round((clamp(value, 0, fromMax) / fromMax) * toMax);
  }

  function normalize(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9+#.]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function countListed(detail, label) {
    const match = String(detail || "").match(new RegExp(`${label}: ([^;]+)`, "i"));
    if (!match) return 0;
    return match[1].split(",").map(x => x.trim()).filter(Boolean).length;
  }

  function inspectionForResult(result) {
    return result?.job?._inspection || result?.job?.inspection || null;
  }

  function requirementField(inspection, key) {
    const field = inspection?.requirements?.[key];
    return field && typeof field === "object" ? field : null;
  }

  function evidenceFacts(field, bucket) {
    return Array.isArray(field?.[bucket]) ? field[bucket] : [];
  }

  function explicitGraduateOnlyTitle(job) {
    const title = normalize(job?.title);
    if (!title) return false;
    if (/\b(?:undergrad(?:uate)?|bachelor(?:'s|s)?|freshman|sophomore|junior)\b/.test(title)) return false;
    if (/\bgrad(?:uate)?\s+(?:intern|internship|co ?op)\b/.test(title)) return true;
    if (/\b(?:intern|internship|co ?op)\b.*\b(?:graduate|grad|phd|doctoral|doctorate|master(?:'s|s)?|mba)\b/.test(title)) return true;
    if (/\b(?:phd|doctoral|doctorate|master(?:'s|s)?|mba)\b.*\b(?:intern|internship|co ?op)\b/.test(title)) return true;
    return false;
  }

  function degreeLevel(value) {
    const text = normalize(value);
    if (/\b(?:bachelor|bs|ba)\b/.test(text)) return "bachelor";
    if (/\b(?:master|ms|mba)\b/.test(text)) return "master";
    if (/\b(?:phd|doctoral|doctorate)\b/.test(text)) return "doctoral";
    return null;
  }

  function statementMatchesDegree(statement, level) {
    const text = normalize(statement);
    if (level === "bachelor") return /\b(?:bachelor|undergrad(?:uate)?|bs|ba)\b/.test(text);
    if (level === "master") return /\b(?:master|graduate|ms|mba)\b/.test(text);
    if (level === "doctoral") return /\b(?:phd|doctoral|doctorate)\b/.test(text);
    return false;
  }

  function authoritativeAcademicSupport(result, profile) {
    const inspection = inspectionForResult(result);
    if (inspection?.status !== "inspected") return { bonus: 0, details: [] };

    let bonus = 0;
    const details = [];
    const major = normalize(profile?.facts?.major || profile?.major);
    const degree = degreeLevel(profile?.facts?.degree || profile?.degree);
    const majors = requirementField(inspection, "major_fields");
    const education = requirementField(inspection, "education");

    if (major) {
      const requiredMajors = evidenceFacts(majors, "required");
      const preferredMajors = evidenceFacts(majors, "preferred");
      const requiredMatch = requiredMajors.some(fact => normalize(fact?.statement).includes(major));
      const preferredMatch = preferredMajors.some(fact => normalize(fact?.statement).includes(major));
      if (requiredMatch) {
        bonus += 3;
        details.push(`${profile?.facts?.major || profile?.major} matches a required major`);
      } else if (preferredMatch) {
        bonus += 2;
        details.push(`${profile?.facts?.major || profile?.major} matches a preferred major`);
      }
    }

    if (degree) {
      const requiredEducation = evidenceFacts(education, "required");
      const preferredEducation = evidenceFacts(education, "preferred");
      const requiredMatch = requiredEducation.some(fact => statementMatchesDegree(fact?.statement, degree));
      const preferredMatch = preferredEducation.some(fact => statementMatchesDegree(fact?.statement, degree));
      if (requiredMatch) {
        bonus += 2;
        details.push(`${degree} degree matches a required education level`);
      } else if (preferredMatch) {
        bonus += 1;
        details.push(`${degree} degree matches a preferred education level`);
      }
    }

    return { bonus: Math.min(5, bonus), details };
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

  function qualificationFitLegacy(result, profile) {
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
    const academic = authoritativeAcademicSupport(result, profile || {});
    const support = positive + academic.bonus;
    const penalty = qualificationPenalty(result?.readiness);
    const score = Math.max(0, Math.min(25, 12 + support - penalty));
    const parts = [];
    if (support) parts.push(`Authoritative qualification support: +${support}`);
    if (academic.details.length) parts.push(`Academic qualification match: ${academic.details.join(", ")}`);
    if (penalty) parts.push(`Required qualification gaps: -${penalty}`);
    if (!parts.length) parts.push("No authoritative qualification evidence distinguishes this posting");
    return { score, detail: parts.join("; ") };
  }

  function scoreQualificationFit(result, profile) {
    const legacy = qualificationFitLegacy(result, profile);
    return {
      score: scaleScore(legacy.score, LEGACY_MAXIMA.fit, SCORE_MAXIMA.fit),
      detail: legacy.detail,
    };
  }

  function scoreEligibilityGate(result) {
    const detail = result?.components?.eligibility?.detail || "Eligibility checks passed";
    return { score: 0, detail: `${detail}; passed eligibility is a gate, not a ranking advantage` };
  }

  function scoreApplicationValue(result) {
    const prior = result?.components?.roi || { score: 10, detail: "Neutral application-value baseline" };
    const duplicateQualificationBonus = Math.max(0, Number(result?.competition?.differentiationBonus || 0));
    const score = Math.max(0, Math.min(SCORE_MAXIMA.roi, Number(prior.score || 0) - duplicateQualificationBonus));
    const detail = String(prior.detail || "")
      .split(";")
      .map(x => x.trim())
      .filter(Boolean)
      .filter(x => !/required-skill differentiation:/i.test(x))
      .filter(x => !/specialized role aligns with supported experience/i.test(x))
      .join("; ") || "Neutral application-value baseline";
    return { score, detail };
  }

  function rescaleComponent(component, key) {
    const source = component || { score: 0, detail: "" };
    return {
      ...source,
      score: scaleScore(source.score, LEGACY_MAXIMA[key], SCORE_MAXIMA[key]),
    };
  }

  function graduateTitleExclusion(result, profile) {
    if (!result || profile?.excludeGraduateOnly === false || !explicitGraduateOnlyTitle(result.job)) return null;
    const eligibility = { score: 0, excluded: true, detail: "Graduate-only opportunity (explicit title)" };
    return {
      ...result,
      total: 0,
      excluded: true,
      components: { ...(result.components || {}), eligibility },
      reasons: [eligibility.detail],
    };
  }

  function transform(result, profile = {}) {
    if (!result) return result;
    const gradExcluded = graduateTitleExclusion(result, profile);
    if (gradExcluded) return gradExcluded;
    if (result.excluded || !result.components) return result;
    const fit = scoreQualificationFit(result, profile);
    const eligibility = scoreEligibilityGate(result);
    const freshness = rescaleComponent(result.components.freshness, "freshness");
    const roi = scoreApplicationValue(result);
    const role = rescaleComponent(result.components.role, "role");
    const location = rescaleComponent(result.components.location, "location");
    const link = {
      score: 0,
      detail: `${result.components.link?.detail || "Link provenance unavailable"}; provenance only, not a ranking signal`,
    };
    const components = { fit, eligibility, freshness, roi, role, location, link };
    const total = Math.max(0, Math.min(100,
      Object.values(components).reduce((sum, c) => sum + Number(c?.score || 0), 0)));
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
        location: "logistics/desirability",
        freshness: "timing",
        link: "provenance only",
      },
      scoreMaxima: SCORE_MAXIMA,
    };
  }

  function scoreJob(job, profile, now = new Date(), context = {}) {
    return transform(base.scoreJob(job, profile, now, context), profile || {});
  }

  function rankJobs(jobs, profile, now = new Date()) {
    return base.rankJobs(jobs || [], profile || {}, now)
      .map(result => transform(result, profile || {}))
      .filter(x => !x.excluded)
      .sort((a, b) => b.total - a.total
        || (new Date(b.job?.posted_at || 0) - new Date(a.job?.posted_at || 0))
        || String(a.job?.company || "").localeCompare(String(b.job?.company || "")));
  }

  return {
    SCORE_MAXIMA,
    LEGACY_MAXIMA,
    scaleScore,
    explicitGraduateOnlyTitle,
    authoritativeAcademicSupport,
    scoreQualificationFit,
    scoreEligibilityGate,
    scoreApplicationValue,
    transform,
    scoreJob,
    rankJobs,
  };
});