(function (root, factory) {
  const base = typeof module === "object" && module.exports
    ? require("./apply-next.js")
    : root.YartchivesApplyNext;
  const api = factory(base);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.YartchivesApplyNextReadiness = api;
    if (base && api) {
      base.scoreFit = api.scoreFit;
      base.scoreJob = api.scoreJob;
      base.rankJobs = api.rankJobs;
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (base) {
  if (!base || typeof base.scoreJob !== "function") {
    throw new Error("Apply Next readiness requires apply-next.js to load first.");
  }

  const originalScoreJob = base.scoreJob;
  const GENERIC_REQUIREMENT_MATCH_TERMS = new Set([
    "software",
    "system",
    "systems",
    "data",
    "it",
    "technology",
    "technologies",
    "engineering",
    "engineer",
    "analysis",
    "analytics",
    "programming",
    "development",
    "computer",
    "technical",
  ]);

  function normalize(value) {
    if (typeof base.normalize === "function") return base.normalize(value);
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9+#.]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function inspectionForJob(job) {
    if (typeof base.inspectionForJob === "function") return base.inspectionForJob(job);
    return job?._inspection || job?.inspection || null;
  }

  function requirementField(inspection, key) {
    if (typeof base.requirementField === "function") return base.requirementField(inspection, key);
    const field = inspection?.requirements?.[key];
    return field && typeof field === "object" ? field : null;
  }

  function evidenceFacts(field, bucket) {
    if (typeof base.evidenceFacts === "function") return base.evidenceFacts(field, bucket);
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

  function exactContains(text, keyword) {
    const haystack = normalize(text);
    const needle = canonicalSkill(keyword);
    if (!haystack || !needle) return false;
    return (` ${haystack} `).includes(` ${needle} `);
  }

  function jobText(job) {
    return normalize([
      job?.title,
      job?.function_primary,
      job?.section,
      ...(job?.profiles || []),
    ].filter(Boolean).join(" "));
  }

  function isDomainRequirementStatement(statement) {
    const text = normalize(statement);
    if (!text) return false;
    const domainEvidence = /\b(?:experience|knowledge|familiarity|familiar|proficiency|proficient|expertise|coursework|background)\b/.test(text);
    if (!domainEvidence) return false;
    const softSkillOnly = /\b(?:communication|interpersonal|organizational|collaboration|teamwork|time management)\b/.test(text)
      && !/\b(?:technical|domain|industry|tool|platform|product|language|framework|database|gis|cad|laboratory|lab)\b/.test(text);
    return !softSkillOnly;
  }

  function analyzeRequiredSkills(job, profile) {
    const inspection = inspectionForJob(job);
    const skills = requirementField(inspection, "skills");
    const supportedProfile = profileSupportedSkills(profile);
    const cautiousProfile = profileCautiousSkills(profile);
    const supported = new Set();
    const cautious = new Set();
    const unsupported = new Set();
    const preferredSupported = new Set();
    const unverifiedDomainRequirements = new Set();

    function classifyFact(fact, bucket) {
      const technologies = Array.isArray(fact?.technologies)
        ? fact.technologies.map(canonicalSkill).filter(Boolean)
        : [];
      const statement = normalize(fact?.statement);
      const domainRequirement = bucket === "required"
        && !technologies.length
        && isDomainRequirementStatement(statement);
      let candidates = technologies;
      if (!candidates.length) {
        candidates = [...new Set([
          ...supportedProfile.filter(skill => exactContains(statement, skill)),
          ...cautiousProfile.filter(skill => exactContains(statement, skill)),
        ])];
        if (domainRequirement) {
          candidates = candidates.filter(skill => !GENERIC_REQUIREMENT_MATCH_TERMS.has(skill));
        }
      }
      for (const skill of candidates) {
        if (supportedProfile.includes(skill)) {
          if (bucket === "preferred") preferredSupported.add(skill);
          else supported.add(skill);
        } else if (bucket === "required" && cautiousProfile.includes(skill)) {
          cautious.add(skill);
        } else if (bucket === "required" && technologies.length) {
          unsupported.add(skill);
        }
      }
      if (domainRequirement && !candidates.length && fact?.statement) {
        unverifiedDomainRequirements.add(String(fact.statement).trim());
      }
    }

    for (const fact of evidenceFacts(skills, "required")) classifyFact(fact, "required");
    for (const fact of evidenceFacts(skills, "preferred")) classifyFact(fact, "preferred");

    return {
      supported: [...supported].sort(),
      cautious: [...cautious].sort(),
      unsupported: [...unsupported].sort(),
      preferredSupported: [...preferredSupported].sort(),
      unverifiedDomainRequirements: [...unverifiedDomainRequirements],
    };
  }

  function scoreFit(job, profile) {
    const text = jobText(job);
    const preferredProfiles = profile?.preferredProfiles || [];
    const jobProfiles = new Set(job?.profiles || []);
    const profileOverlap = preferredProfiles.filter(value => jobProfiles.has(value));
    let score = profileOverlap.length ? 10 : 0;
    const reasons = [];
    if (profileOverlap.length) reasons.push(`Career-area overlap: ${profileOverlap.join(", ")}`);

    const metadataSupported = [...new Set((profile?.supportedKeywords || []).map(canonicalSkill).filter(Boolean))];
    const matches = metadataSupported.filter(keyword => exactContains(text, keyword));
    score += Math.min(15, matches.length * 3);
    if (matches.length) reasons.push(`Supported metadata matches: ${matches.slice(0, 5).join(", ")}`);

    const metadataCautious = [...new Set((profile?.cautiousKeywords || []).map(canonicalSkill).filter(Boolean))];
    const cautiousMatches = metadataCautious.filter(keyword => exactContains(text, keyword));
    if (cautiousMatches.length) reasons.push(`Not credited as strengths: ${cautiousMatches.join(", ")}`);

    const skillAnalysis = analyzeRequiredSkills(job, profile);
    if (skillAnalysis.supported.length) {
      score += Math.min(6, skillAnalysis.supported.length * 2);
      reasons.push(`Required posting skills supported: ${skillAnalysis.supported.slice(0, 4).join(", ")}`);
    }
    if (skillAnalysis.preferredSupported.length) {
      score += Math.min(3, skillAnalysis.preferredSupported.length);
      reasons.push(`Preferred posting skills supported: ${skillAnalysis.preferredSupported.slice(0, 4).join(", ")}`);
    }
    if (skillAnalysis.cautious.length) {
      reasons.push(`Required skills only cautiously supported: ${skillAnalysis.cautious.slice(0, 4).join(", ")}`);
    }
    if (skillAnalysis.unsupported.length) {
      reasons.push(`Required posting skills not supported by profile: ${skillAnalysis.unsupported.slice(0, 4).join(", ")}`);
    }
    if (skillAnalysis.unverifiedDomainRequirements.length) {
      reasons.push(`Required domain experience not verified: ${skillAnalysis.unverifiedDomainRequirements.length} requirement${skillAnalysis.unverifiedDomainRequirements.length === 1 ? "" : "s"}`);
    }

    if (!reasons.length) reasons.push("No strong evidence match visible in current feed fields");
    return { score: Math.max(0, Math.min(25, score)), detail: reasons.join("; ") };
  }

  function profileAuthorizationText(profile) {
    return normalize([
      profile?.facts?.workAuthorization,
      profile?.facts?.citizenship,
      profile?.workAuthorization,
      profile?.citizenship,
    ].filter(Boolean).join(" "));
  }

  function authorizationGate(job, profile) {
    const inspection = inspectionForJob(job);
    const citizenship = requirementField(inspection, "citizenship");
    const authorization = requirementField(inspection, "work_authorization");
    const facts = [
      ...evidenceFacts(citizenship, "required"),
      ...evidenceFacts(authorization, "required"),
    ];
    if (!facts.length) return { excluded: false, penalty: 0, details: [] };

    const requirementText = normalize(facts.map(fact => fact.statement).join(" "));
    const restrictive = /\bcitizen\b|\bu\.?s\.? person\b|\bauthorized to work\b|\bno sponsorship\b|\bdoes not sponsor\b|\bwill not sponsor\b/.test(requirementText);
    if (!restrictive) return { excluded: false, penalty: 0, details: [] };

    const profileText = profileAuthorizationText(profile);
    if (!profileText) {
      return { excluded: false, penalty: 5, details: ["Unverified requirement: work authorization/citizenship"] };
    }

    const requiresCitizenship = /\bcitizenship (?:is )?required\b|\bu\.?s\.? citizen\b|\bunited states citizen\b/.test(requirementText);
    const explicitlyNotCitizen = /\bnot (?:a )?u\.?s\.? citizen\b|\bnon[- ]?u\.?s\.? citizen\b/.test(profileText);
    if (requiresCitizenship && explicitlyNotCitizen) {
      return { excluded: true, penalty: 0, details: ["Known eligibility conflict: posting requires U.S. citizenship"] };
    }

    const noSponsorship = /\bno sponsorship\b|\bdoes not sponsor\b|\bwill not sponsor\b|\bwithout sponsorship\b/.test(requirementText);
    const needsSponsorship = /\bneeds? (?:visa )?sponsorship\b|\brequires? (?:visa )?sponsorship\b|\bvisa sponsorship needed\b/.test(profileText);
    if (noSponsorship && needsSponsorship) {
      return { excluded: true, penalty: 0, details: ["Known eligibility conflict: posting does not provide required sponsorship"] };
    }

    return { excluded: false, penalty: 0, details: [] };
  }

  function profileClearanceText(profile) {
    return normalize([
      profile?.facts?.securityClearance,
      profile?.facts?.clearance,
      profile?.securityClearance,
      profile?.clearance,
    ].filter(Boolean).join(" "));
  }

  function profileClassStanding(profile) {
    const text = normalize(profile?.facts?.classStanding || profile?.classStanding);
    if (!text || /unknown|not provided/.test(text)) return "";
    if (/\b(?:freshman|first year|first-year)\b/.test(text)) return "freshman";
    if (/\bsophomore\b/.test(text)) return "sophomore";
    if (/\bjunior\b/.test(text)) return "junior";
    if (/\b(?:senior|final year|final-year)\b/.test(text)) return "senior";
    if (/\bgraduate\b/.test(text)) return "graduate";
    return "";
  }

  function classStandingGate(job, profile) {
    const inspection = inspectionForJob(job);
    const standing = requirementField(inspection, "class_standing");
    const required = evidenceFacts(standing, "required");
    if (!required.length) return { excluded: false, penalty: 0, details: [] };

    const requirementText = normalize(required.map(fact => fact.statement).join(" "));
    const accepted = new Set();
    if (/\b(?:freshman|first year|first-year)\b/.test(requirementText)) accepted.add("freshman");
    if (/\bsophomore\b/.test(requirementText)) accepted.add("sophomore");
    if (/\bjunior\b/.test(requirementText)) accepted.add("junior");
    if (/\b(?:senior|final year|final-year)\b/.test(requirementText)) accepted.add("senior");
    if (/\bgraduate\b/.test(requirementText)) accepted.add("graduate");
    if (!accepted.size) return { excluded: false, penalty: 0, details: [] };

    const profileStanding = profileClassStanding(profile);
    const label = [...accepted].join(" or ");
    if (!profileStanding) {
      return { excluded: false, penalty: 5, details: [`Unverified requirement: ${label} class standing`] };
    }
    if (!accepted.has(profileStanding)) {
      return { excluded: true, penalty: 0, details: [`Known eligibility conflict: posting requires ${label} class standing`] };
    }
    return { excluded: false, penalty: 0, details: [] };
  }

  function clearanceGate(job, profile) {
    const inspection = inspectionForJob(job);
    const other = requirementField(inspection, "other_eligibility");
    const required = evidenceFacts(other, "required").filter(fact => {
      const text = normalize(fact?.statement);
      return /\bclearance\b/.test(text)
        && /\b(active|existing|current|already|possess|hold|held)\b/.test(text);
    });
    if (!required.length) return { excluded: false, penalty: 0, details: [] };

    const requirementText = normalize(required.map(fact => fact.statement).join(" "));
    const profileText = profileClearanceText(profile);
    if (!profileText) {
      return { excluded: false, penalty: 5, details: ["Unverified requirement: active security clearance"] };
    }
    if (/\b(no|none|without|not cleared|no clearance)\b/.test(profileText)) {
      return { excluded: true, penalty: 0, details: ["Known eligibility conflict: posting requires an active security clearance"] };
    }
    if (/\b(eligible|ability) to obtain\b/.test(profileText) && /\b(active|existing|current)\b/.test(requirementText)) {
      return { excluded: true, penalty: 0, details: ["Known eligibility conflict: posting requires an existing active security clearance"] };
    }

    const requirementLevel = /\btop secret\b|\bts\/sci\b/.test(requirementText)
      ? "top secret"
      : (/\bsecret\b/.test(requirementText) ? "secret" : null);
    const hasActive = /\b(active|current|existing)\b/.test(profileText);
    const profileLevel = /\btop secret\b|\bts\/sci\b/.test(profileText)
      ? "top secret"
      : (/\bsecret\b/.test(profileText) ? "secret" : null);
    const levelSatisfied = !requirementLevel
      || profileLevel === requirementLevel
      || (requirementLevel === "secret" && profileLevel === "top secret");
    if (hasActive && levelSatisfied) return { excluded: false, penalty: 0, details: [] };

    return { excluded: false, penalty: 5, details: ["Unverified requirement: active security clearance"] };
  }

  function scoreReadiness(job, profile) {
    const inspection = inspectionForJob(job);
    if (!inspection || inspection.status !== "inspected") {
      return { delta: 0, excluded: false, label: "Metadata only", details: [] };
    }

    const skills = analyzeRequiredSkills(job, profile);
    let skillPenalty = 0;
    const details = [];
    skills.unsupported.forEach((skill, index) => {
      const penalty = index === 0 ? 10 : (index === 1 ? 6 : 4);
      skillPenalty += penalty;
      details.push(`Required gap: ${skill}`);
    });
    skillPenalty = Math.min(20, skillPenalty);

    const cautiousPenalty = Math.min(8, skills.cautious.length * 4);
    for (const skill of skills.cautious) details.push(`Required skill only cautiously supported: ${skill}`);

    const domainPenalty = Math.min(12, skills.unverifiedDomainRequirements.length * 6);
    for (const statement of skills.unverifiedDomainRequirements) {
      details.push(`Unverified required domain experience: ${statement}`);
    }

    const auth = authorizationGate(job, profile);
    if (auth.excluded) {
      return { delta: 0, excluded: true, label: "Known requirement conflict", details: auth.details };
    }
    const clearance = clearanceGate(job, profile);
    if (clearance.excluded) {
      return { delta: 0, excluded: true, label: "Known requirement conflict", details: clearance.details };
    }
    const classStanding = classStandingGate(job, profile);
    if (classStanding.excluded) {
      return { delta: 0, excluded: true, label: "Known requirement conflict", details: classStanding.details };
    }

    details.push(...auth.details, ...clearance.details, ...classStanding.details);
    const unverifiedPenalty = Math.min(10, auth.penalty + clearance.penalty + classStanding.penalty);
    const totalPenalty = Math.min(30, skillPenalty + cautiousPenalty + domainPenalty + unverifiedPenalty);
    const label = totalPenalty >= 16 || skills.unsupported.length >= 2
      ? "Major required gaps"
      : (totalPenalty > 0 ? "Some required gaps" : "Ready on known requirements");

    return { delta: totalPenalty ? -totalPenalty : 0, excluded: false, label, details };
  }

  function decorateInspection(summary, readiness) {
    if (!summary || summary.state !== "inspected") return summary;
    const evidence = [...(summary.evidence || [])];
    if (readiness.delta) evidence.unshift(`Qualification readiness adjustment: ${readiness.delta} points`);
    for (let index = readiness.details.length - 1; index >= 0; index -= 1) {
      evidence.unshift(readiness.details[index]);
    }
    return {
      ...summary,
      label: `${summary.label} · ${readiness.label}`,
      evidence,
    };
  }

  function scoreJob(job, profile, now = new Date()) {
    const baseResult = originalScoreJob(job, profile, now);
    if (baseResult.excluded) return { ...baseResult, readiness: { delta: 0, excluded: false, label: "Excluded", details: [] } };

    const correctedFit = scoreFit(job, profile || {});
    const components = { ...baseResult.components, fit: correctedFit };
    const readiness = scoreReadiness(job, profile || {});
    const inspection = decorateInspection(baseResult.inspection, readiness);
    if (readiness.excluded) {
      return {
        ...baseResult,
        total: 0,
        excluded: true,
        components,
        reasons: [...(baseResult.reasons || []), ...readiness.details.map(detail => `readiness: ${detail}`)],
        inspection,
        readiness,
      };
    }

    const componentTotal = Object.values(components).reduce((sum, component) => sum + Number(component?.score || 0), 0);
    const total = Math.max(0, Math.min(100, componentTotal + readiness.delta));
    return {
      ...baseResult,
      total,
      excluded: false,
      components,
      reasons: [...(baseResult.reasons || []), `readiness: ${readiness.label}${readiness.delta ? ` (${readiness.delta})` : ""}`],
      inspection,
      readiness,
    };
  }

  function rankJobs(jobs, profile, now = new Date()) {
    return (jobs || [])
      .map(job => scoreJob(job, profile, now))
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
    canonicalSkill,
    exactContains,
    isDomainRequirementStatement,
    analyzeRequiredSkills,
    scoreFit,
    authorizationGate,
    clearanceGate,
    profileClassStanding,
    classStandingGate,
    scoreReadiness,
    scoreJob,
    rankJobs,
  };
});
