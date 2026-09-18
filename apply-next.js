(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.YartchivesApplyNext = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const DEFAULT_WEIGHTS = Object.freeze({
    fit: 25,
    eligibility: 20,
    freshness: 10,
    roi: 15,
    role: 15,
    location: 20,
    link: 5,
  });

  function normalize(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9+#.]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function jobText(job) {
    return normalize([
      job?.title,
      job?.function_primary,
      job?.section,
      ...(job?.profiles || []),
    ].filter(Boolean).join(" "));
  }

  function includesKeyword(text, keyword) {
    const needle = normalize(keyword);
    if (!needle) return false;
    return (` ${text} `).includes(` ${needle} `) || text.includes(needle);
  }

  function inspectionForJob(job) {
    return job?._inspection || job?.inspection || null;
  }

  function requirementField(inspection, key) {
    const field = inspection?.requirements?.[key];
    return field && typeof field === "object" ? field : null;
  }

  function evidenceFacts(field, bucket) {
    return Array.isArray(field?.[bucket]) ? field[bucket] : [];
  }

  function profileSupportedKeywords(profile) {
    return [...new Set([
      ...(profile?.supportedKeywords || []),
      ...(profile?.facts?.supportedSkills || []),
    ].map(normalize).filter(Boolean))];
  }

  function profileCautiousKeywords(profile) {
    return [...new Set([
      ...(profile?.cautiousKeywords || []),
      ...(profile?.facts?.cautiousSkills || []),
    ].map(normalize).filter(Boolean))];
  }

  function profileFactText(profile) {
    return normalize([
      profile?.facts?.graduation,
      profile?.facts?.degree,
      profile?.facts?.major,
      profile?.facts?.workAuthorization,
      profile?.facts?.citizenship,
      profile?.workAuthorization,
      profile?.citizenship,
    ].filter(Boolean).join(" "));
  }

  function profileGraduationYear(profile) {
    const text = [
      profile?.facts?.graduation,
      profile?.graduation,
    ].filter(Boolean).join(" ");
    const match = text.match(/\b(20\d{2})\b/);
    return match ? Number(match[1]) : null;
  }

  function statementYears(statement) {
    return [...new Set((String(statement || "").match(/\b20\d{2}\b/g) || []).map(Number))].sort();
  }

  function opportunityType(job) {
    if (job?.opportunity_type) return job.opportunity_type;
    const text = normalize(job?.title);
    if (/\bco[ -]?op\b/.test(text)) return "co-op";
    if (/\b(intern|internship|student trainee|pathways)\b/.test(text)) return "internship";
    if (/\bfellow(ship)?\b/.test(text)) return "fellowship";
    if (/\bresearch\b/.test(text)) return "research";
    return "other";
  }

  function educationLevel(job) {
    if (job?.education_level) return job.education_level;
    const text = String(job?.title || "");
    const lower = text.toLowerCase();
    const undergrad = /\b(undergrad(?:uate)?|bachelor(?:'s|s)?|freshman|sophomore|junior)\b/.test(lower)
      || /(?:^|[\s,(\/])B\.?S\.?(?=$|[\s,)/])/i.test(text)
      || /(?:^|[\s,(\/])B\.?A\.?(?=$|[\s,)/])/i.test(text);
    const graduate = /\b(ph\.?d\.?|doctoral|doctorate|master(?:'s|s)?|graduate student|mba)\b/i.test(text)
      || /(?:^|[\s,(\/])M\.?S\.?(?=$|[\s,)/])/i.test(text);
    if (undergrad) return "undergrad";
    if (graduate) return "graduate-only";
    return "unspecified";
  }

  function ageDays(job, now) {
    if (!job?.posted_at) return null;
    const posted = new Date(job.posted_at).getTime();
    const current = new Date(now).getTime();
    if (!Number.isFinite(posted) || !Number.isFinite(current)) return null;
    return Math.max(0, (current - posted) / 86400000);
  }

  function scoreFreshness(job, now) {
    const age = ageDays(job, now);
    if (age === null) return { score: 3, detail: "Posting date unknown" };
    if (age <= 2) return { score: 10, detail: "Posted within 2 days" };
    if (age <= 7) return { score: 8, detail: "Posted within 7 days" };
    if (age <= 14) return { score: 6, detail: "Posted within 14 days" };
    if (age <= 30) return { score: 3, detail: "Posted within 30 days" };
    if (age <= 60) return { score: 1, detail: "Posted within 60 days" };
    return { score: 0, detail: "Older than 60 days" };
  }

  function inspectionAvailability(inspection) {
    if (!inspection) return "unknown";
    if (inspection.status === "unavailable") return "unavailable";
    return inspection?.posting?.application_status || "unknown";
  }

  function graduationAdjustment(inspection, profile) {
    const field = requirementField(inspection, "graduation");
    const gradYear = profileGraduationYear(profile);
    if (!field) return { delta: 0, detail: null };

    const required = evidenceFacts(field, "required");
    const preferred = evidenceFacts(field, "preferred");
    const facts = required.length ? required : preferred;
    if (!facts.length) return { delta: 0, detail: null };

    const bucket = required.length ? "required" : "preferred";
    if (!gradYear) {
      return { delta: 0, detail: `Posting has an explicit ${bucket} graduation condition; profile graduation year is unavailable` };
    }

    const yearSets = facts.map(fact => statementYears(fact.statement)).filter(years => years.length);
    if (!yearSets.length) {
      return { delta: 0, detail: `Posting has an explicit ${bucket} graduation condition` };
    }

    const matches = facts.some(fact => {
      const statement = normalize(fact.statement);
      const years = statementYears(fact.statement);
      if (!years.length) return false;
      if (years.length >= 2) return gradYear >= Math.min(...years) && gradYear <= Math.max(...years);
      const year = years[0];
      if (/\b(?:after|no earlier than)\b/.test(statement)) return gradYear >= year;
      if (/\b(?:before|by|no later than)\b/.test(statement)) return gradYear <= year;
      return gradYear === year;
    });
    if (matches) {
      return { delta: required.length ? 2 : 1, excluded: false, detail: `${gradYear} fits the posting's explicit ${bucket} graduation window` };
    }
    if (required.length) {
      return {
        delta: 0,
        excluded: true,
        detail: `${gradYear} does not match the posting's explicit required graduation year/window`,
      };
    }
    return { delta: 0, excluded: false, detail: `${gradYear} does not match the posting's preferred graduation window` };
  }

  function authorizationAdjustment(inspection, profile) {
    if (!inspection) return { delta: 0, details: [] };
    const profileText = profileFactText(profile);
    const supportsUsAuthorization = /\bu\.?s\.? citizen\b|\bunited states citizen\b|\bpermanent resident\b|\bno sponsorship\b|\bsponsorship (?:is )?not (?:needed|required)\b|\bauthorized to work\b/.test(profileText);
    const needsSponsorship = /\bneeds? sponsorship\b|\brequires? sponsorship\b|\bvisa sponsorship needed\b/.test(profileText);
    let delta = 0;
    const details = [];

    const citizenship = requirementField(inspection, "citizenship");
    const authorization = requirementField(inspection, "work_authorization");
    const requiredFacts = [
      ...evidenceFacts(citizenship, "required"),
      ...evidenceFacts(authorization, "required"),
    ];
    const notRequiredFacts = [
      ...evidenceFacts(citizenship, "not_required"),
      ...evidenceFacts(authorization, "not_required"),
    ];

    if (requiredFacts.length) {
      const text = normalize(requiredFacts.map(fact => fact.statement).join(" "));
      const restrictive = /\bu\.?s\.? (?:citizen|person)\b|\bunited states (?:citizen|person)\b|\bauthorized to work\b|\bdoes not sponsor\b|\bwill not sponsor\b|\bno sponsorship\b/.test(text);
      if (restrictive && supportsUsAuthorization) {
        delta += 2;
        details.push("Profile supports the posting's explicit work-authorization/citizenship requirement");
      } else if (restrictive && needsSponsorship) {
        delta -= 6;
        details.push("Profile conflicts with the posting's explicit work-authorization/sponsorship requirement");
      } else {
        details.push("Posting has explicit work-authorization/citizenship requirements");
      }
    }

    if (notRequiredFacts.length) {
      details.push("Posting explicitly says a citizenship/sponsorship condition is not required");
    }
    return { delta, details };
  }

  function authoritativeSchedule(inspection) {
    const schedule = inspection?.schedule;
    if (!schedule || typeof schedule !== "object") return null;
    const terms = Array.isArray(schedule.terms)
      ? [...new Set(schedule.terms.map(normalize).filter(Boolean))]
      : [];
    const durationEvidence = Array.isArray(schedule.duration_evidence)
      ? schedule.duration_evidence.filter(Boolean)
      : [];
    const dateRangeEvidence = Array.isArray(schedule.date_range_evidence)
      ? schedule.date_range_evidence.filter(Boolean)
      : [];
    if (!terms.length && !durationEvidence.length && !dateRangeEvidence.length) return null;
    return { terms, durationEvidence, dateRangeEvidence };
  }

  function scoreEligibility(job, profile) {
    const inspection = inspectionForJob(job);
    const availability = inspectionAvailability(inspection);
    if (availability === "unavailable") {
      return {
        score: 0,
        excluded: true,
        detail: inspection?.status === "unavailable"
          ? "Authoritative posting is unavailable"
          : "Authoritative posting says applications are unavailable",
      };
    }

    const type = opportunityType(job);
    const level = educationLevel(job);
    const allowedTypes = profile?.opportunityTypes || ["internship", "co-op", "student"];
    if (profile?.excludeGraduateOnly !== false && level === "graduate-only") {
      return { score: 0, excluded: true, detail: "Graduate-only opportunity" };
    }
    if (allowedTypes.length && !allowedTypes.includes(type)) {
      return { score: 0, excluded: true, detail: `Opportunity type ${type} is outside the target set` };
    }

    let score = level === "undergrad" ? 6 : 4;
    const parts = [level === "undergrad" ? "Explicit undergraduate fit" : "Education level not restrictive in feed data"];

    score += 7;
    parts.push(`Opportunity type ${type} is eligible`);

    const targetTerm = normalize(profile?.targetTerm);
    const jobTerm = normalize(job?.term);
    const authoritative = inspection?.status === "inspected" ? authoritativeSchedule(inspection) : null;
    if (!targetTerm) {
      score += 7;
      parts.push("No target term configured");
    } else if (authoritative?.terms?.length) {
      if (authoritative.terms.includes(targetTerm)) {
        score += 7;
        parts.push(`Authoritative posting matches ${profile.targetTerm}`);
      } else {
        const stated = inspection.schedule.terms.join(", ");
        return {
          score: 0,
          excluded: true,
          detail: `Authoritative posting term is ${stated}, not ${profile.targetTerm}`,
        };
      }
    } else if (jobTerm === targetTerm) {
      score += 7;
      parts.push(`Matches ${profile.targetTerm}`);
    } else if (!jobTerm) {
      score += 4;
      parts.push("Term unknown");
    } else {
      parts.push(`Known term is ${job.term}, not ${profile.targetTerm}`);
    }

    if (authoritative?.durationEvidence?.length || authoritative?.dateRangeEvidence?.length) {
      const scheduleEvidence = [
        ...(authoritative.durationEvidence || []),
        ...(authoritative.dateRangeEvidence || []),
      ][0];
      if (scheduleEvidence) parts.push(`Authoritative schedule: ${scheduleEvidence}`);
    }

    if (inspection?.status === "inspected") {
      if (availability === "available") {
        score += 1;
        parts.push("Authoritative posting confirms applications are available");
      }
      const grad = graduationAdjustment(inspection, profile);
      if (grad.excluded) {
        return { score: 0, excluded: true, detail: grad.detail };
      }
      score += grad.delta;
      if (grad.detail) parts.push(grad.detail);

      const auth = authorizationAdjustment(inspection, profile);
      score += auth.delta;
      parts.push(...auth.details);

      const education = requirementField(inspection, "education");
      const student = requirementField(inspection, "student_status");
      const majors = requirementField(inspection, "major_fields");
      if (evidenceFacts(education, "required").length || evidenceFacts(student, "required").length) {
        parts.push("Posting contains explicit education/student-status requirements");
      }
      if (evidenceFacts(majors, "required").length || evidenceFacts(majors, "preferred").length) {
        parts.push("Posting contains explicit degree/major evidence");
      }
    }

    return { score: Math.max(0, Math.min(20, score)), excluded: false, detail: parts.join("; ") };
  }

  function scoreFit(job, profile) {
    const text = jobText(job);
    const preferredProfiles = profile?.preferredProfiles || [];
    const jobProfiles = new Set(job?.profiles || []);
    const profileOverlap = preferredProfiles.filter(value => jobProfiles.has(value));
    let score = profileOverlap.length ? 10 : 0;
    const reasons = [];
    if (profileOverlap.length) reasons.push(`Career-area overlap: ${profileOverlap.join(", ")}`);

    const metadataSupported = [...new Set((profile?.supportedKeywords || []).map(normalize).filter(Boolean))];
    const matches = metadataSupported.filter(keyword => includesKeyword(text, keyword));
    score += Math.min(15, matches.length * 3);
    if (matches.length) reasons.push(`Supported metadata matches: ${matches.slice(0, 5).join(", ")}`);

    const metadataCautious = [...new Set((profile?.cautiousKeywords || []).map(normalize).filter(Boolean))];
    const cautiousMatches = metadataCautious.filter(keyword => includesKeyword(text, keyword));
    if (cautiousMatches.length) reasons.push(`Not credited as strengths: ${cautiousMatches.join(", ")}`);

    const inspection = inspectionForJob(job);
    if (inspection?.status === "inspected") {
      const supported = profileSupportedKeywords(profile);
      const cautious = profileCautiousKeywords(profile);
      const skills = requirementField(inspection, "skills");
      const required = evidenceFacts(skills, "required");
      const preferred = evidenceFacts(skills, "preferred");
      const requiredSupported = new Set();
      const requiredCautious = new Set();
      const requiredUnsupported = new Set();
      const preferredSupported = new Set();

      for (const fact of required) {
        const statement = normalize(fact.statement);
        const technologies = Array.isArray(fact.technologies) ? fact.technologies.map(normalize).filter(Boolean) : [];
        const candidates = technologies.length ? technologies : supported.filter(keyword => includesKeyword(statement, keyword));
        for (const skill of candidates) {
          if (supported.some(keyword => keyword === skill || includesKeyword(skill, keyword) || includesKeyword(keyword, skill))) requiredSupported.add(skill);
          else if (cautious.some(keyword => keyword === skill || includesKeyword(skill, keyword) || includesKeyword(keyword, skill))) requiredCautious.add(skill);
          else if (technologies.length) requiredUnsupported.add(skill);
        }
      }
      for (const fact of preferred) {
        const statement = normalize(fact.statement);
        const technologies = Array.isArray(fact.technologies) ? fact.technologies.map(normalize).filter(Boolean) : [];
        const candidates = technologies.length ? technologies : supported.filter(keyword => includesKeyword(statement, keyword));
        for (const skill of candidates) {
          if (supported.some(keyword => keyword === skill || includesKeyword(skill, keyword) || includesKeyword(keyword, skill))) preferredSupported.add(skill);
        }
      }

      if (requiredSupported.size) {
        score += Math.min(6, requiredSupported.size * 2);
        reasons.push(`Required posting skills supported: ${[...requiredSupported].slice(0, 4).join(", ")}`);
      }
      if (preferredSupported.size) {
        score += Math.min(3, preferredSupported.size);
        reasons.push(`Preferred posting skills supported: ${[...preferredSupported].slice(0, 4).join(", ")}`);
      }
      if (requiredCautious.size) {
        score -= Math.min(3, requiredCautious.size);
        reasons.push(`Required skills only cautiously supported: ${[...requiredCautious].slice(0, 4).join(", ")}`);
      }
      if (requiredUnsupported.size) {
        score -= Math.min(6, requiredUnsupported.size * 2);
        reasons.push(`Required posting skills not supported by profile: ${[...requiredUnsupported].slice(0, 4).join(", ")}`);
      }
    }

    if (!reasons.length) reasons.push("No strong evidence match visible in current feed fields");
    return { score: Math.max(0, Math.min(25, score)), detail: reasons.join("; ") };
  }

  function scoreRole(job, profile) {
    const text = jobText(job);
    const families = profile?.roleFamilies || [];
    let best = null;
    for (const family of families) {
      const keywords = family?.keywords || [];
      if (!keywords.some(keyword => includesKeyword(text, keyword))) continue;
      const priority = Math.max(0, Math.min(1, Number(family.priority ?? 1)));
      const legacyTenPointScore = Math.round(10 * priority);
      const candidate = {
        score: Math.round(legacyTenPointScore * 1.5),
        detail: family.label || family.id || "Preferred role family",
      };
      if (!best || candidate.score > best.score) best = candidate;
    }
    if (best) return best;

    const preferredProfiles = profile?.preferredProfiles || [];
    if ((job?.profiles || []).some(value => preferredProfiles.includes(value))) {
      return { score: 8, detail: "Preferred career area, but no preferred role-family keyword matched" };
    }
    return { score: 3, detail: "Outside explicit preferred role families" };
  }

  function scoreLocation(job, profile) {
    const states = new Set(job?.states || []);
    const preferredStates = profile?.preferredStates || [];
    if (states.has("Remote") && profile?.remoteRelevant !== false) {
      return { score: 18, detail: "Remote opportunity" };
    }
    if (Number.isFinite(job?._distanceMiles)) {
      const near = Number(profile?.nearbyMiles || 50);
      if (job._distanceMiles <= near) return { score: 20, detail: `Within ${near} miles of active base` };
      if (job._distanceMiles <= near * 2) return { score: 16, detail: `Within ${near * 2} miles of active base` };
    }
    const stateMatch = preferredStates.find(value => states.has(value));
    if (stateMatch) return { score: 20, detail: `Preferred state: ${stateMatch}` };
    if (!states.size || states.has("US")) return { score: 10, detail: "Location is broad or unknown" };
    if (profile?.relocationAllowed) return { score: 12, detail: "Relocation is acceptable" };
    return { score: 2, detail: "Outside preferred locations" };
  }

  function linkKind(job) {
    if (job?.link_kind === "direct") return "direct";
    if (job?.link_kind === "listing") return "listing";
    if (job?.link_kind === "source") return "source";
    return job?.url ? "direct" : "source";
  }

  function scoreLink(job) {
    const kind = linkKind(job);
    if (kind === "direct") return { score: 5, detail: "Direct employer/ATS application" };
    if (kind === "listing") return { score: 2, detail: "Intermediary listing link" };
    return { score: 0, detail: "Source-only link" };
  }

  function scoreRoi(job, profile, now) {
    let score = 7;
    const reasons = ["Base application value"];
    const freshness = scoreFreshness(job, now);
    const kind = linkKind(job);
    const targetTerm = normalize(profile?.targetTerm);
    const jobTerm = normalize(job?.term);

    if (kind === "direct") {
      score += 3;
      reasons.push("direct application");
    } else if (kind === "source") {
      score -= 2;
      reasons.push("source-only application friction");
    }
    if (freshness.score >= 8) {
      score += 3;
      reasons.push("fresh posting");
    }
    if (targetTerm && jobTerm === targetTerm) {
      score += 2;
      reasons.push("exact target term");
    }
    if (!job?.posted_at) {
      score -= 1;
      reasons.push("posting date unknown");
    }
    return { score: Math.max(0, Math.min(15, score)), detail: reasons.join("; ") };
  }

  function summarizeInspection(job) {
    const inspection = inspectionForJob(job);
    if (!inspection) return { state: "metadata-only", label: "Metadata only", evidence: [] };
    if (inspection.status === "unavailable" || inspectionAvailability(inspection) === "unavailable") {
      return { state: "unavailable", label: "Posting unavailable", evidence: ["Authoritative posting is no longer available"] };
    }
    if (inspection.status !== "inspected") {
      return { state: "metadata-only", label: "Metadata only", evidence: ["Authoritative posting inspection is not currently available"] };
    }

    const evidence = [];
    if (inspectionAvailability(inspection) === "available") evidence.push("Posting confirmed available");
    const graduation = requirementField(inspection, "graduation");
    const education = requirementField(inspection, "education");
    const major = requirementField(inspection, "major_fields");
    const auth = requirementField(inspection, "work_authorization");
    const citizenship = requirementField(inspection, "citizenship");
    const skills = requirementField(inspection, "skills");
    if (evidenceFacts(graduation, "required").length || evidenceFacts(graduation, "preferred").length) evidence.push("Graduation requirement found");
    if (evidenceFacts(education, "required").length || evidenceFacts(education, "preferred").length
      || evidenceFacts(major, "required").length || evidenceFacts(major, "preferred").length) evidence.push("Degree/major requirement found");
    if (evidenceFacts(auth, "required").length || evidenceFacts(auth, "not_required").length
      || evidenceFacts(citizenship, "required").length || evidenceFacts(citizenship, "not_required").length) evidence.push("Work authorization/citizenship language found");
    if (evidenceFacts(skills, "required").length || evidenceFacts(skills, "preferred").length) evidence.push("Required/preferred skill evidence found");
    return { state: "inspected", label: "Posting inspected", evidence };
  }

  function scoreJob(job, profile, now = new Date()) {
    const eligibility = scoreEligibility(job, profile || {});
    const inspection = summarizeInspection(job);
    if (eligibility.excluded) {
      return {
        job,
        total: 0,
        excluded: true,
        components: { eligibility },
        reasons: [eligibility.detail],
        inspection,
      };
    }

    const components = {
      fit: scoreFit(job, profile || {}),
      eligibility,
      freshness: scoreFreshness(job, now),
      roi: scoreRoi(job, profile || {}, now),
      role: scoreRole(job, profile || {}),
      location: scoreLocation(job, profile || {}),
      link: scoreLink(job),
    };
    const total = Object.values(components).reduce((sum, component) => sum + component.score, 0);
    return {
      job,
      total,
      excluded: false,
      components,
      reasons: Object.entries(components).map(([name, component]) => `${name}: ${component.detail}`),
      inspection,
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
    DEFAULT_WEIGHTS,
    normalize,
    inspectionForJob,
    requirementField,
    evidenceFacts,
    profileSupportedKeywords,
    profileCautiousKeywords,
    profileGraduationYear,
    statementYears,
    opportunityType,
    educationLevel,
    ageDays,
    scoreFreshness,
    authoritativeSchedule,
    scoreEligibility,
    scoreFit,
    scoreRole,
    scoreLocation,
    linkKind,
    scoreLink,
    scoreRoi,
    summarizeInspection,
    scoreJob,
    rankJobs,
  };
});