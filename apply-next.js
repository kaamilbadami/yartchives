(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.YartchivesApplyNext = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const DEFAULT_WEIGHTS = Object.freeze({
    fit: 25,
    eligibility: 20,
    freshness: 15,
    roi: 15,
    role: 10,
    location: 10,
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
    if (age === null) return { score: 5, detail: "Posting date unknown" };
    if (age <= 2) return { score: 15, detail: "Posted within 2 days" };
    if (age <= 7) return { score: 12, detail: "Posted within 7 days" };
    if (age <= 14) return { score: 9, detail: "Posted within 14 days" };
    if (age <= 30) return { score: 5, detail: "Posted within 30 days" };
    if (age <= 60) return { score: 2, detail: "Posted within 60 days" };
    return { score: 0, detail: "Older than 60 days" };
  }

  function scoreEligibility(job, profile) {
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
    if (!targetTerm) {
      score += 7;
      parts.push("No target term configured");
    } else if (jobTerm === targetTerm) {
      score += 7;
      parts.push(`Matches ${profile.targetTerm}`);
    } else if (!jobTerm) {
      score += 4;
      parts.push("Term unknown");
    } else {
      parts.push(`Known term is ${job.term}, not ${profile.targetTerm}`);
    }
    return { score: Math.min(20, score), excluded: false, detail: parts.join("; ") };
  }

  function scoreFit(job, profile) {
    const text = jobText(job);
    const preferredProfiles = profile?.preferredProfiles || [];
    const jobProfiles = new Set(job?.profiles || []);
    const profileOverlap = preferredProfiles.filter(value => jobProfiles.has(value));
    let score = profileOverlap.length ? 10 : 0;
    const reasons = [];
    if (profileOverlap.length) reasons.push(`Career-area overlap: ${profileOverlap.join(", ")}`);

    const supported = [...new Set((profile?.supportedKeywords || []).map(normalize).filter(Boolean))];
    const matches = supported.filter(keyword => includesKeyword(text, keyword));
    score += Math.min(15, matches.length * 3);
    if (matches.length) reasons.push(`Supported evidence matches: ${matches.slice(0, 5).join(", ")}`);

    const cautious = [...new Set((profile?.cautiousKeywords || []).map(normalize).filter(Boolean))];
    const cautiousMatches = cautious.filter(keyword => includesKeyword(text, keyword));
    if (cautiousMatches.length) reasons.push(`Not credited as strengths: ${cautiousMatches.join(", ")}`);

    if (!reasons.length) reasons.push("No strong evidence match visible in current feed fields");
    return { score: Math.min(25, score), detail: reasons.join("; ") };
  }

  function scoreRole(job, profile) {
    const text = jobText(job);
    const families = profile?.roleFamilies || [];
    let best = null;
    for (const family of families) {
      const keywords = family?.keywords || [];
      if (!keywords.some(keyword => includesKeyword(text, keyword))) continue;
      const priority = Math.max(0, Math.min(1, Number(family.priority ?? 1)));
      const candidate = {
        score: Math.round(10 * priority),
        detail: family.label || family.id || "Preferred role family",
      };
      if (!best || candidate.score > best.score) best = candidate;
    }
    if (best) return best;

    const preferredProfiles = profile?.preferredProfiles || [];
    if ((job?.profiles || []).some(value => preferredProfiles.includes(value))) {
      return { score: 5, detail: "Preferred career area, but no preferred role-family keyword matched" };
    }
    return { score: 2, detail: "Outside explicit preferred role families" };
  }

  function scoreLocation(job, profile) {
    const states = new Set(job?.states || []);
    const preferredStates = profile?.preferredStates || [];
    if (states.has("Remote") && profile?.remoteRelevant !== false) {
      return { score: 9, detail: "Remote opportunity" };
    }
    if (Number.isFinite(job?._distanceMiles)) {
      const near = Number(profile?.nearbyMiles || 50);
      if (job._distanceMiles <= near) return { score: 10, detail: `Within ${near} miles of active base` };
      if (job._distanceMiles <= near * 2) return { score: 8, detail: `Within ${near * 2} miles of active base` };
    }
    const stateMatch = preferredStates.find(value => states.has(value));
    if (stateMatch) return { score: 10, detail: `Preferred state: ${stateMatch}` };
    if (!states.size || states.has("US")) return { score: 5, detail: "Location is broad or unknown" };
    if (profile?.relocationAllowed) return { score: 6, detail: "Relocation is acceptable" };
    return { score: 1, detail: "Outside preferred locations" };
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
    if (freshness.score >= 12) {
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

  function scoreJob(job, profile, now = new Date()) {
    const eligibility = scoreEligibility(job, profile || {});
    if (eligibility.excluded) {
      return {
        job,
        total: 0,
        excluded: true,
        components: { eligibility },
        reasons: [eligibility.detail],
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
    opportunityType,
    educationLevel,
    ageDays,
    scoreFreshness,
    scoreEligibility,
    scoreFit,
    scoreRole,
    scoreLocation,
    linkKind,
    scoreLink,
    scoreRoi,
    scoreJob,
    rankJobs,
  };
});
