(function (root, factory) {
  const base = typeof module === "object" && module.exports
    ? require("./apply-next-readiness.js")
    : (root.YartchivesApplyNextReadiness || root.YartchivesApplyNext);
  const api = factory(base);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.YartchivesApplyNextCompetition = api;
    const target = root.YartchivesApplyNext;
    if (target && api) {
      target.scoreRoi = api.scoreRoi;
      target.scoreJob = api.scoreJob;
      target.rankJobs = api.rankJobs;
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (base) {
  if (!base || typeof base.scoreJob !== "function") {
    throw new Error("Apply Next competition scoring requires readiness scoring to load first.");
  }

  const originalScoreJob = base.scoreJob;

  function normalize(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9+#.]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function inspectionForJob(job) {
    return job?._inspection || job?.inspection || null;
  }

  function evidenceFacts(field, bucket) {
    return Array.isArray(field?.[bucket]) ? field[bucket] : [];
  }

  function canonicalSkill(value) {
    const skill = normalize(value);
    const aliases = {
      cpp: "c++",
      "c plus plus": "c++",
      csharp: "c#",
      "c sharp": "c#",
      js: "javascript",
      ts: "typescript",
      golang: "go",
    };
    return aliases[skill] || skill;
  }

  function profileSupportedSkills(profile) {
    return [...new Set([
      ...(profile?.supportedKeywords || []),
      ...(profile?.facts?.supportedSkills || []),
    ].map(canonicalSkill).filter(Boolean))];
  }

  function profileCautiousSkills(profile) {
    return [...new Set([
      ...(profile?.cautiousKeywords || []),
      ...(profile?.facts?.cautiousSkills || []),
    ].map(canonicalSkill).filter(Boolean))];
  }

  function skillMatchesProfile(skill, supported, cautious) {
    const candidate = canonicalSkill(skill);
    if (!candidate) return "none";
    if (supported.includes(candidate)) return "supported";
    if (cautious.includes(candidate)) return "cautious";
    return "none";
  }

  function requiredSkillSupport(job, profile) {
    const inspection = inspectionForJob(job);
    const skills = inspection?.requirements?.skills;
    if (!inspection || inspection.status !== "inspected" || !skills) {
      return { supported: [], cautious: [] };
    }
    const supportedProfile = profileSupportedSkills(profile);
    const cautiousProfile = profileCautiousSkills(profile);
    const supported = new Set();
    const cautious = new Set();

    for (const fact of evidenceFacts(skills, "required")) {
      const technologies = Array.isArray(fact?.technologies)
        ? fact.technologies.map(canonicalSkill).filter(Boolean)
        : [];
      for (const skill of technologies) {
        const state = skillMatchesProfile(skill, supportedProfile, cautiousProfile);
        if (state === "supported") supported.add(skill);
        else if (state === "cautious") cautious.add(skill);
      }
    }
    return { supported: [...supported].sort(), cautious: [...cautious].sort() };
  }

  function isGenericRole(job) {
    const title = normalize(job?.title);
    if (!title) return false;
    const specialized = /\b(embedded|firmware|systems?|infrastructure|platform|devops|site reliability|sre|test|testing|quality|qa|security|cyber|data|analytics|machine learning|ml|ai|hpc|scientific|signal|graphics|compiler|database|network|cloud|hardware|fpga|gpu|robotics|controls|simulation|verification|validation)\b/.test(title);
    if (specialized) return false;
    return /\b(software (engineer|engineering|developer)|swe|technology|engineering)\b/.test(title)
      && /\b(intern|internship|co op)\b/.test(title);
  }

  function isSpecializedRole(job) {
    const title = normalize(job?.title);
    return /\b(embedded|firmware|systems?|infrastructure|platform|devops|site reliability|sre|test|testing|quality|qa|security|cyber|data|analytics|hpc|scientific|signal|compiler|database|network|cloud|fpga|gpu|robotics|verification|validation)\b/.test(title);
  }

  function marketPressure(job) {
    const states = new Set(job?.states || []);
    const location = normalize(job?.location);
    const reasons = [];
    let penalty = 0;

    if (states.has("Remote") || /\bremote\b/.test(location)) {
      penalty += 2;
      reasons.push("remote role can draw a broad applicant pool");
    }
    if (/\b(new york|nyc|manhattan|san francisco|bay area|seattle|boston)\b/.test(location)) {
      penalty += 2;
      reasons.push("dense applicant market");
    }
    if (/\b(united states|nationwide|multiple locations|various locations)\b/.test(location)) {
      penalty += 1;
      reasons.push("broad geographic applicant pool");
    }
    return { penalty: Math.min(3, penalty), reasons };
  }

  function employerKey(job) {
    return normalize(job?.company);
  }

  function titleKey(job) {
    return normalize(job?.title);
  }

  function buildCompetitionContext(jobs) {
    const employerTitles = new Map();
    for (const job of jobs || []) {
      const company = employerKey(job);
      if (!company) continue;
      if (!employerTitles.has(company)) employerTitles.set(company, new Set());
      const title = titleKey(job) || String(job?.id || "");
      employerTitles.get(company).add(title);
    }
    const employerCounts = {};
    for (const [company, titles] of employerTitles.entries()) employerCounts[company] = titles.size;
    return { employerCounts };
  }

  function scoreRoi(job, profile, context = {}) {
    let score = 10;
    const reasons = ["Neutral application-value baseline"];
    let competitionPenalty = 0;
    let differentiationBonus = 0;

    if (isGenericRole(job)) {
      competitionPenalty += 2;
      reasons.push("broad generic internship title");
    }

    const market = marketPressure(job);
    competitionPenalty += market.penalty;
    reasons.push(...market.reasons);

    const companyCount = Number(context?.employerCounts?.[employerKey(job)] || 0);
    if (companyCount >= 8) {
      competitionPenalty += 2;
      reasons.push(`large current hiring footprint (${companyCount} distinct listings)`);
    } else if (companyCount >= 4) {
      competitionPenalty += 1;
      reasons.push(`broad current hiring footprint (${companyCount} distinct listings)`);
    }

    const skillSupport = requiredSkillSupport(job, profile || {});
    if (skillSupport.supported.length >= 2) {
      differentiationBonus += 3;
      reasons.push(`strong required-skill differentiation: ${skillSupport.supported.slice(0, 3).join(", ")}`);
    } else if (skillSupport.supported.length === 1) {
      differentiationBonus += 2;
      reasons.push(`required-skill differentiation: ${skillSupport.supported[0]}`);
    }

    if (isSpecializedRole(job) && skillSupport.supported.length) {
      differentiationBonus += 2;
      reasons.push("specialized role aligns with supported experience");
    }

    competitionPenalty = Math.min(5, competitionPenalty);
    differentiationBonus = Math.min(5, differentiationBonus);
    score = Math.max(0, Math.min(15, score - competitionPenalty + differentiationBonus));

    if (!competitionPenalty && !differentiationBonus) reasons.push("no strong competition or differentiation signal available");
    return {
      score,
      detail: reasons.join("; "),
      competitionPenalty,
      differentiationBonus,
    };
  }

  function isWorkdayUrl(job) {
    return /\.myworkdayjobs\.com(?:\/|$)/i.test(String(job?.url || ""));
  }

  function workdayInspectionStatus(job) {
    if (!isWorkdayUrl(job)) return null;
    const inspection = inspectionForJob(job);
    if (!inspection) {
      return "Workday link is not currently recognized by the authoritative posting inspector.";
    }
    if (inspection.status === "inspected" || inspection.status === "unavailable") return null;

    const queue = inspection?.queue && typeof inspection.queue === "object" ? inspection.queue : {};
    const rank = Number(queue.rank);
    const rankText = Number.isFinite(rank) && rank > 0 ? ` (public priority #${rank})` : "";
    const reasons = Array.isArray(queue.reasons)
      ? queue.reasons.filter(Boolean).slice(0, 4)
      : [];

    if (inspection.status === "queued") {
      const detail = `Queued for bounded Workday inspection${rankText}.`;
      return reasons.length ? `${detail} Priority signals: ${reasons.join(", ")}.` : detail;
    }

    if (queue.state === "retry_cooldown") {
      return "Workday inspection was attempted but could not retrieve authoritative data; retry is cooling down before another bounded attempt.";
    }

    const detail = `Workday inspection was attempted but could not retrieve authoritative data; it remains queued for retry${rankText}.`;
    return reasons.length ? `${detail} Priority signals: ${reasons.join(", ")}.` : detail;
  }

  function decorateInspectionStatus(result) {
    if (!result || result?.inspection?.state !== "metadata-only") return result;
    const detail = workdayInspectionStatus(result.job);
    if (!detail) return result;
    return {
      ...result,
      inspection: {
        ...result.inspection,
        evidence: [detail],
      },
    };
  }

  function scoreJob(job, profile, now = new Date(), context = {}) {
    const baseResult = originalScoreJob(job, profile, now);
    if (baseResult.excluded) return baseResult;

    const roi = scoreRoi(job, profile || {}, context);
    const components = { ...baseResult.components, roi };
    const readinessDelta = Number(baseResult?.readiness?.delta || 0);
    const componentTotal = Object.values(components).reduce((sum, component) => sum + Number(component?.score || 0), 0);
    const total = Math.max(0, Math.min(100, componentTotal + readinessDelta));
    const reasons = Object.entries(components).map(([name, component]) => `${name}: ${component.detail}`);
    if (baseResult.readiness) {
      reasons.push(`readiness: ${baseResult.readiness.label}${readinessDelta ? ` (${readinessDelta})` : ""}`);
    }
    return decorateInspectionStatus({
      ...baseResult,
      total,
      components,
      reasons,
      competition: {
        penalty: roi.competitionPenalty,
        differentiationBonus: roi.differentiationBonus,
      },
    });
  }

  function rankJobs(jobs, profile, now = new Date()) {
    const pool = jobs || [];
    const context = buildCompetitionContext(pool);
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
    isGenericRole,
    isSpecializedRole,
    marketPressure,
    buildCompetitionContext,
    requiredSkillSupport,
    isWorkdayUrl,
    workdayInspectionStatus,
    decorateInspectionStatus,
    scoreRoi,
    scoreJob,
    rankJobs,
  };
});
