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

  function roleDemandKey(job) {
    const title = titleKey(job);
    if (!title) return "unknown";
    const families = [
      ["embedded/firmware", /\b(embedded|firmware|fpga|hardware)\b/],
      ["security", /\b(security|cyber)\b/],
      ["testing/quality", /\b(test|testing|quality|qa|verification|validation)\b/],
      ["data/analytics", /\b(data|analytics|business intelligence|bi)\b/],
      ["infrastructure/cloud", /\b(infrastructure|devops|site reliability|sre|cloud|network)\b/],
      ["systems/platform", /\b(systems?|platform|database|compiler)\b/],
      ["software engineering", /\b(software|swe|developer|engineering)\b/],
    ];
    const match = families.find(([, pattern]) => pattern.test(title));
    if (match) return match[0];
    const stripped = title
      .replace(/\b(20\d{2}|summer|spring|fall|winter|intern|internship|co op|undergraduate|student|junior|senior)\b/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return stripped || "other";
  }

  function postingKey(job) {
    return String(job?.id || job?.url || `${titleKey(job)}|${normalize(job?.location)}`);
  }

  function buildCompetitionContext(jobs) {
    const employerTitles = new Map();
    const employerRolePostings = new Map();
    for (const job of jobs || []) {
      const company = employerKey(job);
      if (!company) continue;
      if (!employerTitles.has(company)) employerTitles.set(company, new Set());
      const title = titleKey(job) || String(job?.id || "");
      employerTitles.get(company).add(title);

      const role = roleDemandKey(job);
      const roleKey = `${company}::${role}`;
      if (!employerRolePostings.has(roleKey)) employerRolePostings.set(roleKey, new Set());
      employerRolePostings.get(roleKey).add(postingKey(job));
    }
    const employerCounts = {};
    for (const [company, titles] of employerTitles.entries()) employerCounts[company] = titles.size;
    const employerRoleCounts = {};
    for (const [roleKey, postings] of employerRolePostings.entries()) employerRoleCounts[roleKey] = postings.size;
    return { employerCounts, employerRoleCounts };
  }

  function observedDemand(job, context = {}) {
    const company = employerKey(job);
    const role = roleDemandKey(job);
    const count = Number(context?.employerRoleCounts?.[`${company}::${role}`] || 0);
    if (count >= 4) {
      return {
        observed: true,
        bonus: 5,
        count,
        role,
        detail: `observed employer demand: ${count} current ${role} openings`,
      };
    }
    if (count >= 2) {
      return {
        observed: true,
        bonus: 3,
        count,
        role,
        detail: `observed employer demand: ${count} current ${role} openings`,
      };
    }
    return { observed: false, bonus: 0, count, role, detail: null };
  }

  function scoreRoi(job, profile, context = {}) {
    let score = 10;
    const reasons = ["Neutral application-value baseline"];
    let competitionPenalty = 0;
    const differentiationBonus = 0;
    let demandBonus = 0;

    const demand = observedDemand(job, context);
    if (demand.observed) {
      demandBonus = demand.bonus;
      reasons.push(demand.detail);
    } else {
      if (isGenericRole(job)) {
        competitionPenalty += 2;
        reasons.push("broad generic internship title (fallback competition heuristic)");
      }

      const market = marketPressure(job);
      competitionPenalty += market.penalty;
      reasons.push(...market.reasons.map(reason => `${reason} (fallback competition heuristic)`));

      const companyCount = Number(context?.employerCounts?.[employerKey(job)] || 0);
      if (companyCount >= 8) {
        competitionPenalty += 2;
        reasons.push(`large current hiring footprint (${companyCount} distinct listings; fallback competition heuristic)`);
      } else if (companyCount >= 4) {
        competitionPenalty += 1;
        reasons.push(`broad current hiring footprint (${companyCount} distinct listings; fallback competition heuristic)`);
      }
    }

    competitionPenalty = Math.min(5, competitionPenalty);
    demandBonus = Math.min(5, demandBonus);
    score = Math.max(0, Math.min(15, score - competitionPenalty + demandBonus));

    if (!demand.observed && !competitionPenalty) {
      reasons.push("no observed employer/role demand evidence or strong fallback competition signal available");
    }
    return {
      score,
      detail: reasons.join("; "),
      competitionPenalty,
      differentiationBonus,
      demandBonus,
      observedDemand: demand.observed ? { count: demand.count, role: demand.role } : null,
    };
  }

  function isWorkdayUrl(job) {
    return /\.myworkdayjobs\.com(?:\/|$)/i.test(String(job?.url || ""));
  }

  function isIcimsUrl(job) {
    return /(?:^|\.)icims\.com(?:\/|$)/i.test(String(job?.url || "").replace(/^https?:\/\//i, ""));
  }

  function isGreenhouseUrl(job) {
    return /^(?:job-boards|boards)\.greenhouse\.io(?:\/|$)/i.test(
      String(job?.url || "").replace(/^https?:\/\//i, "")
    );
  }

  function inspectionProvider(job) {
    const inspection = inspectionForJob(job);
    const explicit = normalize(inspection?.provider || inspection?.provenance?.provider || inspection?.queue?.provider);
    if (["workday", "icims", "greenhouse"].includes(explicit)) return explicit;
    if (isWorkdayUrl(job)) return "workday";
    if (isIcimsUrl(job)) return "icims";
    if (isGreenhouseUrl(job)) return "greenhouse";
    return null;
  }

  function postingInspectionStatus(job) {
    const provider = inspectionProvider(job);
    if (!provider) return null;
    const providerLabel = ({ workday: "Workday", icims: "iCIMS", greenhouse: "Greenhouse" })[provider];
    const inspection = inspectionForJob(job);
    if (!inspection) {
      return {
        label: provider === "icims" ? "Unsupported iCIMS URL" : "Metadata only",
        detail: `${providerLabel} link is not currently recognized by the authoritative posting inspector.`,
      };
    }
    if (inspection.status === "inspected" || inspection.status === "unavailable") return null;

    const queue = inspection?.queue && typeof inspection.queue === "object" ? inspection.queue : {};
    const rank = Number(queue.rank);
    const rankText = Number.isFinite(rank) && rank > 0 ? ` (public priority #${rank})` : "";
    const reasons = Array.isArray(queue.reasons)
      ? queue.reasons.filter(Boolean).slice(0, 4)
      : [];

    if (inspection.status === "unsupported_url" || queue.state === "unsupported_url") {
      return {
        label: ({ icims: "Unsupported iCIMS URL", greenhouse: "Unsupported Greenhouse URL" })[provider]
          || "Unsupported posting URL",
        detail: `${providerLabel} URL shape is not recognized by the authoritative posting inspector.`,
      };
    }
    if (inspection.status === "queued") {
      const detail = `Queued for bounded ${providerLabel} inspection${rankText}.`;
      return {
        label: "Queued for inspection",
        detail: reasons.length ? `${detail} Priority signals: ${reasons.join(", ")}.` : detail,
      };
    }
    if (queue.state === "retry_cooldown") {
      return {
        label: "Inspection retry cooldown",
        detail: `${providerLabel} inspection was attempted but could not retrieve authoritative data; retry is cooling down before another bounded attempt.`,
      };
    }

    const detail = `${providerLabel} inspection was attempted but could not retrieve authoritative data; it remains queued for retry${rankText}.`;
    return {
      label: "Inspection retry queued",
      detail: reasons.length ? `${detail} Priority signals: ${reasons.join(", ")}.` : detail,
    };
  }

  function workdayInspectionStatus(job) {
    if (!isWorkdayUrl(job)) return null;
    return postingInspectionStatus(job)?.detail || null;
  }

  function decorateInspectionStatus(result) {
    if (!result || result?.inspection?.state !== "metadata-only") return result;
    const status = postingInspectionStatus(result.job);
    if (!status) return result;
    return {
      ...result,
      inspection: {
        ...result.inspection,
        label: status.label,
        evidence: [status.detail],
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
        demandBonus: roi.demandBonus,
        observedDemand: roi.observedDemand,
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
    roleDemandKey,
    observedDemand,
    buildCompetitionContext,
    requiredSkillSupport,
    isWorkdayUrl,
    isIcimsUrl,
    isGreenhouseUrl,
    inspectionProvider,
    postingInspectionStatus,
    workdayInspectionStatus,
    decorateInspectionStatus,
    scoreRoi,
    scoreJob,
    rankJobs,
  };
});
