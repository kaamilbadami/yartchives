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

  const GENERIC_PROFILE_TERMS = new Set([
    "software", "software engineer", "software developer", "systems", "system", "engineering",
    "engineer", "technology", "technical", "data", "analytics", "testing", "test engineer", "qa",
    "infrastructure", "technical ops", "it",
  ]);

  const CAPABILITY_FAMILIES = Object.freeze({
    programming: ["c", "c++", "c#", "java", "python", "go", "rust"],
    web: ["javascript", "typescript", "react", "node.js", "nodejs"],
    data: ["sql", "postgresql", "mysql", "oracle", "snowflake", "databricks", "spark", "r"],
    cloud: ["aws", "azure", "gcp"],
    containers: ["docker", "kubernetes"],
    os: ["linux", "unix"],
    ci: ["jenkins", "gitlab ci", "github actions"],
    analytics: ["tableau", "power bi", "excel", "r", "sql"],
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
      nodejs: "node.js",
      postgres: "postgresql",
    };
    return aliases[skill] || skill;
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

  function profileSkills(profile, key, fallbackKey) {
    return [...new Set([
      ...(profile?.facts?.[key] || []),
      ...(profile?.[fallbackKey] || []),
    ].map(canonicalSkill).filter(skill => skill && !GENERIC_PROFILE_TERMS.has(skill)))];
  }

  function capabilityFamily(skill) {
    const canonical = canonicalSkill(skill);
    for (const [family, members] of Object.entries(CAPABILITY_FAMILIES)) {
      if (members.includes(canonical)) return family;
    }
    return null;
  }

  function adjacentEvidence(skill, supportedSkills) {
    const family = capabilityFamily(skill);
    if (!family) return null;
    return supportedSkills.find(candidate => candidate !== canonicalSkill(skill) && capabilityFamily(candidate) === family) || null;
  }

  function learnableRequirement(statement) {
    const text = normalize(statement);
    return /\b(?:familiarity|familiar|interest|exposure|foundational|basic understanding|working knowledge|coursework|academic|project experience|school project|willingness to learn|eager to learn)\b/.test(text);
  }

  function analyzeQualificationEvidence(result, profile) {
    const inspection = inspectionForResult(result);
    const skills = requirementField(inspection, "skills");
    const supportedSkills = profileSkills(profile, "supportedSkills", "supportedKeywords");
    const cautiousSkills = profileSkills(profile, "cautiousSkills", "cautiousKeywords");
    const exactRequired = new Set();
    const adjacentRequired = new Map();
    const cautiousRequired = new Set();
    const hardGaps = new Set();
    const learnableGaps = new Set();
    const exactPreferred = new Set();
    const adjacentPreferred = new Map();

    function classify(fact, bucket) {
      const technologies = [...new Set((fact?.technologies || []).map(canonicalSkill).filter(Boolean))];
      const statement = String(fact?.statement || "").trim();
      for (const technology of technologies) {
        if (supportedSkills.includes(technology)) {
          if (bucket === "required") exactRequired.add(technology);
          else exactPreferred.add(technology);
          continue;
        }
        if (bucket === "required" && cautiousSkills.includes(technology)) {
          cautiousRequired.add(technology);
          continue;
        }
        const adjacent = adjacentEvidence(technology, supportedSkills);
        if (adjacent) {
          if (bucket === "required") adjacentRequired.set(technology, adjacent);
          else adjacentPreferred.set(technology, adjacent);
          continue;
        }
        if (bucket === "required") {
          if (learnableRequirement(statement)) learnableGaps.add(technology);
          else hardGaps.add(technology);
        }
      }
    }

    for (const fact of evidenceFacts(skills, "required")) classify(fact, "required");
    for (const fact of evidenceFacts(skills, "preferred")) classify(fact, "preferred");
    for (const fact of evidenceFacts(skills, "unspecified")) classify(fact, "preferred");

    return {
      exactRequired: [...exactRequired],
      adjacentRequired: [...adjacentRequired.entries()],
      cautiousRequired: [...cautiousRequired],
      hardGaps: [...hardGaps],
      learnableGaps: [...learnableGaps],
      exactPreferred: [...exactPreferred],
      adjacentPreferred: [...adjacentPreferred.entries()],
    };
  }

  function unverifiedDomainGapCount(result) {
    const details = Array.isArray(result?.readiness?.details) ? result.readiness.details : [];
    return details.filter(detail => /^Unverified required domain experience:/i.test(String(detail))).length;
  }

  function scoreQualificationFit(result, profile) {
    const inspected = result?.inspection?.state === "inspected";
    if (!inspected) {
      return { score: 19, detail: "Qualification evidence not yet authoritative; neutral qualification-fit score" };
    }

    const academic = authoritativeAcademicSupport(result, profile || {});
    const evidence = analyzeQualificationEvidence(result, profile || {});
    let score = 18 + academic.bonus;

    score += Math.min(9, evidence.exactRequired.length * 3);
    score += Math.min(6, evidence.adjacentRequired.length * 1.5);
    score += Math.min(3, evidence.exactPreferred.length);
    score += Math.min(2, evidence.adjacentPreferred.length * 0.5);
    score -= Math.min(3, evidence.cautiousRequired.length);

    let hardGapPenalty = 0;
    evidence.hardGaps.forEach((_, index) => {
      hardGapPenalty += index === 0 ? 5 : (index === 1 ? 3 : 2);
    });
    score -= Math.min(10, hardGapPenalty);
    score -= Math.min(6, unverifiedDomainGapCount(result) * 3);
    score = Math.round(clamp(score, 0, SCORE_MAXIMA.fit));

    const parts = [];
    if (academic.details.length) parts.push(`Academic match: ${academic.details.join(", ")}`);
    if (evidence.exactRequired.length) parts.push(`Exact required skills: ${evidence.exactRequired.join(", ")}`);
    if (evidence.adjacentRequired.length) {
      parts.push(`Transferable capability: ${evidence.adjacentRequired.map(([needed, evidenceSkill]) => `${evidenceSkill} supports ${needed}`).join(", ")}`);
    }
    if (evidence.exactPreferred.length) parts.push(`Exact preferred skills: ${evidence.exactPreferred.join(", ")}`);
    if (evidence.adjacentPreferred.length) {
      parts.push(`Adjacent preferred skills: ${evidence.adjacentPreferred.map(([needed, evidenceSkill]) => `${evidenceSkill}→${needed}`).join(", ")}`);
    }
    if (evidence.cautiousRequired.length) parts.push(`Required skills only cautiously evidenced: ${evidence.cautiousRequired.join(", ")}`);
    if (evidence.learnableGaps.length) parts.push(`Learnable/low-threshold stack gaps: ${evidence.learnableGaps.join(", ")}`);
    if (evidence.hardGaps.length) parts.push(`Unsupported hard required skills: ${evidence.hardGaps.join(", ")}`);
    const domainGaps = unverifiedDomainGapCount(result);
    if (domainGaps) parts.push(`Unverified required domain experience: ${domainGaps}`);
    if (!parts.length) parts.push("No specific qualification evidence distinguishes this inspected posting");
    return { score, detail: parts.join("; ") };
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
        fit: "qualification evidence: exact screening evidence plus transferable capability",
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
    analyzeQualificationEvidence,
    scoreQualificationFit,
    scoreEligibilityGate,
    scoreApplicationValue,
    transform,
    scoreJob,
    rankJobs,
  };
});