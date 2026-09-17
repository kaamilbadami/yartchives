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
    throw new Error("Apply Next location scoring requires competition scoring first.");
  }

  const originalScoreJob = base.scoreJob;
  const STATE_NAMES = {
    Alabama: "AL", Alaska: "AK", Arizona: "AZ", Arkansas: "AR", California: "CA",
    Colorado: "CO", Connecticut: "CT", Delaware: "DE", Florida: "FL", Georgia: "GA",
    Hawaii: "HI", Idaho: "ID", Illinois: "IL", Indiana: "IN", Iowa: "IA", Kansas: "KS",
    Kentucky: "KY", Louisiana: "LA", Maine: "ME", Maryland: "MD", Massachusetts: "MA",
    Michigan: "MI", Minnesota: "MN", Mississippi: "MS", Missouri: "MO", Montana: "MT",
    Nebraska: "NE", Nevada: "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND",
    Ohio: "OH", Oklahoma: "OK", Oregon: "OR", Pennsylvania: "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", Tennessee: "TN", Texas: "TX", Utah: "UT",
    Vermont: "VT", Virginia: "VA", Washington: "WA", "West Virginia": "WV", Wisconsin: "WI",
    Wyoming: "WY", "District of Columbia": "DC",
  };
  const STATE_CODES = new Set(Object.values(STATE_NAMES));
  const STATE_CODE_BY_NAME = Object.fromEntries(
    Object.entries(STATE_NAMES).map(([name, code]) => [name.toLowerCase(), code])
  );

  function explicitLocationStates(job) {
    const raw = String(job?.location || "");
    const found = new Set();
    for (const [name, code] of Object.entries(STATE_NAMES)) {
      if (new RegExp(`\\b${name.replace(/ /g, "\\s+")}\\b`, "i").test(raw)) found.add(code);
    }
    for (const code of STATE_CODES) {
      if (new RegExp(`(?:^|[\\s,(/-])${code}(?:$|[\\s,)/-])`, "i").test(raw)) found.add(code);
    }
    return [...found];
  }

  function reliableStates(job) {
    const explicit = explicitLocationStates(job);
    if (explicit.length) return new Set(explicit);
    const metadata = [...new Set((job?.states || []).filter(value => STATE_CODES.has(value)))];
    return metadata.length === 1 ? new Set(metadata) : new Set();
  }

  function inspectionForJob(job) {
    return job?._inspection || job?.inspection || null;
  }

  function titleCaseWords(value) {
    return String(value || "").toLowerCase().replace(/\b[a-z]/g, ch => ch.toUpperCase());
  }

  function stateCode(value) {
    const text = String(value || "").trim();
    if (STATE_CODES.has(text.toUpperCase())) return text.toUpperCase();
    return STATE_CODE_BY_NAME[text.toLowerCase()] || null;
  }

  function normalizeAuthoritativeLocation(value, { globalRemote = false } = {}) {
    const raw = String(value || "").replace(/\s+/g, " ").trim();
    if (!raw) return null;
    if (/^(?:united states|usa|us)\s*-\s*remote$/i.test(raw) || /^remote$/i.test(raw)) return "Remote";

    const remoteOffice = raw.match(/^(.+?)\s*-\s*remote office$/i);
    if (remoteOffice) {
      const code = stateCode(remoteOffice[1]);
      if (globalRemote) return null;
      return code ? `Remote (${code})` : `Remote (${remoteOffice[1].trim()})`;
    }

    const workdayParts = raw.split(/\s+-\s+/).map(part => part.trim()).filter(Boolean);
    if (workdayParts.length >= 3 && /^(?:united states|usa|us)$/i.test(workdayParts[0])) {
      const code = stateCode(workdayParts[1]);
      const city = workdayParts[2];
      if (code && city && !/^remote$/i.test(city)) return `${city}, ${code}`;
      if (/^remote$/i.test(city)) return globalRemote ? null : "Remote";
    }

    const facility = raw.match(/^\d+\s+(.+?)\s+([A-Z]{2})$/);
    if (facility && STATE_CODES.has(facility[2])) {
      return `${titleCaseWords(facility[1])}, ${facility[2]}`;
    }

    const cityStateCountry = raw.match(/^(.+?),\s*([A-Z]{2})(?:,\s*(?:US|USA|United States))$/i);
    if (cityStateCountry && STATE_CODES.has(cityStateCountry[2].toUpperCase())) {
      return `${cityStateCountry[1].trim()}, ${cityStateCountry[2].toUpperCase()}`;
    }

    return raw;
  }

  function normalizeAuthoritativeLocations(values) {
    const raw = Array.isArray(values)
      ? values.map(value => String(value || "").trim()).filter(Boolean)
      : [];
    const globalRemote = raw.some(value => /^(?:united states|usa|us)\s*-\s*remote$/i.test(value) || /^remote$/i.test(value));
    const normalized = [];
    const seen = new Set();
    for (const value of raw) {
      const cleaned = normalizeAuthoritativeLocation(value, { globalRemote });
      if (!cleaned) continue;
      const key = cleaned.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      normalized.push(cleaned);
    }
    return normalized;
  }

  function workdayTitleSlug(value) {
    return String(value || "")
      .trim()
      .replace(/[^A-Za-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function authoritativeWorkdayUrl(job, posting) {
    const raw = String(job?.url || "").trim();
    const requisition = String(posting?.requisition_id || "").trim();
    const titleSlug = workdayTitleSlug(posting?.title);
    if (!raw || !requisition || !titleSlug) return raw;
    try {
      const parsed = new URL(raw);
      if (!/myworkdayjobs\.com$/i.test(parsed.hostname)) return raw;
      const parts = parsed.pathname.split("/");
      const final = decodeURIComponent(parts[parts.length - 1] || "");
      const escaped = requisition.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (!new RegExp(`_${escaped}$`, "i").test(final)) return raw;
      parts[parts.length - 1] = `${titleSlug}_${requisition}`;
      parsed.pathname = parts.join("/");
      parsed.search = "";
      parsed.hash = "";
      return parsed.toString();
    } catch (_) {
      return raw;
    }
  }

  function authoritativePostingView(job) {
    const inspection = inspectionForJob(job);
    if (inspection?.status !== "inspected" || !inspection.posting) return job;
    const posting = inspection.posting;
    const view = { ...job };

    if (posting.title) view.title = posting.title;

    const locations = posting.locations;
    const values = locations?.status === "authoritative" && Array.isArray(locations.values)
      ? normalizeAuthoritativeLocations(locations.values)
      : [];
    if (values.length) {
      view.location = values.join(" · ");
      const states = explicitLocationStates(view);
      const remote = /\bremote\b/i.test(view.location);
      view.states = [...states, ...(remote ? ["Remote"] : [])];
    }

    view.url = authoritativeWorkdayUrl(view, posting);
    return view;
  }

  function normalizeUrl(job) {
    const raw = String(job?.url || "").trim();
    if (!raw) return "";
    try {
      const parsed = new URL(raw);
      const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
      let path = decodeURIComponent(parsed.pathname).replace(/\/+$/, "");

      const greenhouseId = parsed.searchParams.get("gh_jid") || path.match(/\/jobs\/(\d+)(?:\/|$)/i)?.[1];
      if (/greenhouse\.io$/i.test(host) && greenhouseId) return `greenhouse:${host}:${greenhouseId}`;

      if (host === "jobs.ashbyhq.com") {
        const parts = path.split("/").filter(Boolean);
        if (parts.length >= 2 && /^[0-9a-f-]{32,36}$/i.test(parts[1])) {
          return `ashby:${parts[0].toLowerCase()}:${parts[1].toLowerCase()}`;
        }
      }

      const icimsId = path.match(/\/jobs\/(\d+)(?:\/|$)/i)?.[1];
      if (/icims\.com$/i.test(host) && icimsId) return `icims:${host}:${icimsId}`;

      if (/myworkdayjobs\.com$/i.test(host)) {
        path = path.replace(/\/application$/i, "");
        const req = path.match(/_([A-Za-z]+-?\d{4,})$/i)?.[1];
        if (req) {
          const site = path.split("/").filter(Boolean)[0] || "";
          return `workday:${host}:${site.toLowerCase()}:${req.toLowerCase()}`;
        }
        return `workday:${host}:${path.toLowerCase()}`;
      }

      path = path.replace(/\/application$/i, "");
      return `${host}:${path.toLowerCase()}`;
    } catch (_) {
      return raw.toLowerCase().replace(/[?#].*$/, "").replace(/\/application\/?$/i, "").replace(/\/+$/, "");
    }
  }

  function canonicalPostingKey(job) {
    const urlKey = normalizeUrl(job);
    if (urlKey) return urlKey;
    if (job?.id) return `id:${job.id}`;
    return [job?.company, job?.title, job?.location]
      .map(value => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim())
      .join("|");
  }

  function inspectionRank(job) {
    const status = job?._inspection?.status || job?.inspection?.status;
    if (status === "inspected") return 3;
    if (status === "queued" || status === "failed") return 2;
    return 1;
  }

  function hasAuthoritativeInspection(job) {
    return inspectionRank(job) === 3;
  }

  function preferDuplicate(current, candidate) {
    const currentRank = inspectionRank(current);
    const candidateRank = inspectionRank(candidate);
    if (candidateRank !== currentRank) return candidateRank > currentRank ? candidate : current;
    const currentTime = current?.posted_at ? new Date(current.posted_at).getTime() : 0;
    const candidateTime = candidate?.posted_at ? new Date(candidate.posted_at).getTime() : 0;
    return candidateTime > currentTime ? candidate : current;
  }

  function dedupeCanonicalJobs(jobs) {
    const byKey = new Map();
    for (const job of jobs || []) {
      const key = canonicalPostingKey(job);
      if (!byKey.has(key)) byKey.set(key, job);
      else byKey.set(key, preferDuplicate(byKey.get(key), job));
    }
    return [...byKey.values()];
  }

  function scoreLocation(job, profile) {
    const rawStates = new Set(job?.states || []);
    const states = reliableStates(job);
    const preferredStates = profile?.preferredStates || [];
    const stateMatch = preferredStates.find(value => states.has(value));
    if (stateMatch) return { score: 10, detail: `Preferred state: ${stateMatch}` };

    if ((rawStates.has("Remote") || /\bremote\b/i.test(String(job?.location || ""))) && profile?.remoteRelevant !== false) {
      return { score: 9, detail: "Remote opportunity" };
    }

    const distance = Number(job?._distanceMiles);
    const hasTrustedDistance = job?._distanceMilesBasis === "apply-next-profile"
      && Number.isFinite(distance)
      && distance >= 0;
    const near = Math.max(5, Number(profile?.nearbyMiles || 50));
    if (hasTrustedDistance) {
      if (distance <= near) return { score: 10, detail: `Within ${near} miles of active base` };
      if (distance <= near * 2) return { score: 8, detail: `Within ${near * 2} miles of active base` };
    }

    if (!states.size && (!rawStates.size || rawStates.has("US"))) {
      return { score: 4, detail: "Location is broad or unknown" };
    }

    if ((rawStates.has("Remote") || /\bremote\b/i.test(String(job?.location || ""))) && profile?.remoteRelevant === false) {
      return { score: 2, detail: "Remote work is not preferred" };
    }

    if (profile?.relocationAllowed) {
      if (!hasTrustedDistance) return { score: 4, detail: "Relocation is acceptable; profile-base distance is unknown" };
      const rounded = Math.round(distance);
      if (distance <= near * 4) return { score: 7, detail: `Relocation about ${rounded} miles from active base` };
      if (distance <= near * 8) return { score: 5, detail: `Relocation about ${rounded} miles from active base` };
      return { score: 3, detail: `Long-distance relocation about ${rounded} miles from active base` };
    }

    return { score: 1, detail: "Outside preferred locations" };
  }

  function scoreJob(job, profile, now = new Date(), context = {}) {
    const effectiveJob = authoritativePostingView(job);
    const result = originalScoreJob(effectiveJob, profile, now, context);
    if (!result || result.excluded || !result.components) return result;

    const location = scoreLocation(effectiveJob, profile || {});
    const prior = Number(result.components?.location?.score || 0);
    const components = { ...result.components, location };
    const total = Math.max(0, Math.min(100, Number(result.total || 0) - prior + location.score));
    const reasons = Array.isArray(result.reasons)
      ? result.reasons.map(reason => String(reason).startsWith("location:")
        ? `location: ${location.detail}`
        : reason)
      : [];

    return { ...result, job: effectiveJob, total, components, reasons };
  }

  function rankJobs(jobs, profile, now = new Date()) {
    const pool = dedupeCanonicalJobs(jobs || []);
    const context = typeof base.buildCompetitionContext === "function"
      ? base.buildCompetitionContext(pool.filter(hasAuthoritativeInspection))
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
    explicitLocationStates,
    reliableStates,
    normalizeAuthoritativeLocation,
    normalizeAuthoritativeLocations,
    authoritativeWorkdayUrl,
    authoritativePostingView,
    canonicalPostingKey,
    dedupeCanonicalJobs,
    hasAuthoritativeInspection,
    scoreLocation,
    scoreJob,
    rankJobs,
  };
});
