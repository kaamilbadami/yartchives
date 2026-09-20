(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesApplyNextUI = api;
    if (typeof document !== "undefined") api.init();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const STORAGE_KEY = "yartchives-apply-next-profile-v1";
  const INSPECTION_URL = "data/workday-inspections.json";
  const TOP_N = 10;
  const FRESH_MAX_AGE_DAYS = 3;
  const FRESH_MIN_SCORE = 55;
  let inspectionArtifactPromise = null;
  let lastRankedResults = [];
  let lastProfile = null;
  let lastTotalEligibleCount = 0;
  let activeQueueView = "recommended";
  let queueVisibleCounts = { recommended: TOP_N, fresh: TOP_N };

  function normalize(value) {
    return String(value || "").trim();
  }

  function postedAgeDays(value, nowValue = new Date()) {
    if (!value) return null;
    const date = new Date(value);
    const now = nowValue instanceof Date ? nowValue : new Date(nowValue);
    if (!Number.isFinite(date.getTime()) || !Number.isFinite(now.getTime())) return null;

    const postedUtcDay = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
    const nowUtcDay = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    return Math.max(0, Math.floor((nowUtcDay - postedUtcDay) / 86400000));
  }

  function formatPostedDate(value, isAuthoritative, nowValue = new Date()) {
    if (!value) return "";
    const date = new Date(value);
    const daysAgo = postedAgeDays(value, nowValue);
    if (!Number.isFinite(date.getTime()) || daysAgo === null) return "";

    const monthDay = `${date.getUTCMonth() + 1}/${date.getUTCDate()}`;
    const ageLabel = `${daysAgo} ${daysAgo === 1 ? "day" : "days"} ago`;
    return isAuthoritative ? `Posted ${monthDay} · ${ageLabel}` : ageLabel;
  }

  function freshRankedResults(ranked, nowValue = new Date()) {
    return (ranked || []).filter(result => {
      if (!result || result.excluded || Number(result.total || 0) < FRESH_MIN_SCORE) return false;
      const age = postedAgeDays(result.job?.posted_at, nowValue);
      return age !== null && age <= FRESH_MAX_AGE_DAYS;
    });
  }

  function queueResults(ranked, view = "recommended", nowValue = new Date()) {
    return view === "fresh"
      ? freshRankedResults(ranked, nowValue)
      : (ranked || []);
  }

  function visibleQueueResults(ranked, view = "recommended", nowValue = new Date(), visibleCount = TOP_N) {
    return queueResults(ranked, view, nowValue).slice(0, Math.max(TOP_N, Number(visibleCount || TOP_N)));
  }

  function validateProfile(profile) {
    if (!profile || typeof profile !== "object" || Array.isArray(profile)) {
      return { ok: false, error: "Profile must be a JSON object." };
    }
    if (!normalize(profile.targetTerm)) {
      return { ok: false, error: "Profile must include targetTerm." };
    }
    if (!Array.isArray(profile.roleFamilies) || !profile.roleFamilies.length) {
      return { ok: false, error: "Profile must include at least one role family." };
    }
    return { ok: true, profile };
  }

  function loadProfile(storage) {
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return validateProfile(parsed).ok ? parsed : null;
    } catch (_) {
      return null;
    }
  }

  function saveProfile(storage, profile) {
    const checked = validateProfile(profile);
    if (!checked.ok) throw new Error(checked.error);
    storage.setItem(STORAGE_KEY, JSON.stringify(profile));
    return profile;
  }

  function knownWrongTerm(job, profile) {
    const target = normalize(profile?.targetTerm).toLowerCase();
    const term = normalize(job?.term).toLowerCase();
    return Boolean(target && term && target !== term);
  }

  function candidatePool(jobs, profile, localState) {
    const applied = localState?.applied || new Set();
    const hidden = localState?.hidden || new Set();
    return (jobs || []).filter(job => {
      if (!job || applied.has(job.id) || hidden.has(job.id)) return false;
      if (knownWrongTerm(job, profile)) return false;
      return true;
    });
  }

  function eligiblePoolCount(jobs, profile) {
    return (jobs || []).filter(job => {
      if (!job || knownWrongTerm(job, profile)) return false;
      return true;
    }).length;
  }


  function explainProfileChange(oldProfile, newProfile, oldTopId, newTopId) {
    if (!oldProfile || !newProfile) return null;
    if (JSON.stringify(oldProfile) === JSON.stringify(newProfile)) return null;

    const changes = [];
    const changedLoc = JSON.stringify(oldProfile.baseZips) !== JSON.stringify(newProfile.baseZips) ||
      JSON.stringify(oldProfile.preferredStates) !== JSON.stringify(newProfile.preferredStates) ||
      oldProfile.relocationAllowed !== newProfile.relocationAllowed ||
      oldProfile.remoteRelevant !== newProfile.remoteRelevant ||
      oldProfile.nearbyMiles !== newProfile.nearbyMiles;
    if (changedLoc) changes.push("location");

    const oldRoleIds = (oldProfile.roleFamilies || []).map(f => f.id);
    const newRoleIds = (newProfile.roleFamilies || []).map(f => f.id);
    const changedRoles = JSON.stringify(oldRoleIds) !== JSON.stringify(newRoleIds) ||
      JSON.stringify(oldProfile.opportunityTypes) !== JSON.stringify(newProfile.opportunityTypes);
    if (changedRoles) changes.push("role");

    const changedFit = JSON.stringify(oldProfile.facts?.supportedSkills) !== JSON.stringify(newProfile.facts?.supportedSkills) ||
      JSON.stringify(oldProfile.facts?.cautiousSkills) !== JSON.stringify(newProfile.facts?.cautiousSkills) ||
      oldProfile.major !== newProfile.major ||
      oldProfile.degree !== newProfile.degree ||
      oldProfile.graduation !== newProfile.graduation ||
      JSON.stringify(oldProfile.supportedKeywords) !== JSON.stringify(newProfile.supportedKeywords) ||
      JSON.stringify(oldProfile.cautiousKeywords) !== JSON.stringify(newProfile.cautiousKeywords);
    if (changedFit) changes.push("skills/background");

    const changedTerm = oldProfile.targetTerm !== newProfile.targetTerm;
    if (changedTerm) changes.push("target term");

    const changedEligibility = oldProfile.citizenship !== newProfile.citizenship ||
      oldProfile.workAuthorization !== newProfile.workAuthorization ||
      oldProfile.securityClearance !== newProfile.securityClearance;
    if (changedEligibility) changes.push("eligibility");

    if (changes.length === 0) return "Recommendations re-evaluated after profile changes.";

    let changedList = changes.join(", ");
    if (changes.length > 1) {
        changedList = changes.slice(0, -1).join(", ") + " and " + changes[changes.length - 1];
    }

    let msg = `Recommendations re-evaluated after ${changedList} changes.`;

    if (oldTopId && newTopId && oldTopId !== newTopId) {
      if (changes.length === 1) {
        msg += ` This new top recommendation is stronger under your updated ${changes[0]} preferences.`;
      } else {
        msg += ` This new top recommendation is a better match for your updated profile.`;
      }
    }
    return msg;
  }

  function profileSummary(profile) {
    const families = (profile?.roleFamilies || [])
      .slice()
      .sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0))
      .map(family => family.label || family.id)
      .filter(Boolean)
      .slice(0, 4);
    const bases = (profile?.baseLabels || []).filter(Boolean);
    return [profile?.targetTerm, families.join(" · "), bases.join(" + ")].filter(Boolean).join(" · ");
  }

  function emptyInspectionArtifact() {
    return { version: 1, entries: {}, listing_index: {} };
  }

  async function fetchInspectionArtifact(fetchImpl) {
    const client = fetchImpl || (typeof fetch === "function" ? fetch : null);
    if (!client) return emptyInspectionArtifact();
    try {
      const response = await client(INSPECTION_URL, { cache: "no-store" });
      if (!response || !response.ok) return emptyInspectionArtifact();
      const payload = await response.json();
      if (!payload || typeof payload !== "object") return emptyInspectionArtifact();
      return {
        version: payload.version || 1,
        entries: payload.entries && typeof payload.entries === "object" ? payload.entries : {},
        listing_index: payload.listing_index && typeof payload.listing_index === "object" ? payload.listing_index : {},
      };
    } catch (_) {
      return emptyInspectionArtifact();
    }
  }

  function loadInspectionArtifact(fetchImpl) {
    if (fetchImpl) return fetchInspectionArtifact(fetchImpl);
    if (!inspectionArtifactPromise) inspectionArtifactPromise = fetchInspectionArtifact();
    return inspectionArtifactPromise;
  }

  function attachInspections(jobs, artifact) {
    const index = artifact?.listing_index || {};
    const entries = artifact?.entries || {};
    for (const job of jobs || []) {
      if (!job || typeof job !== "object") continue;
      delete job._inspection;
      const canonical = index[job.id];
      const inspection = canonical && entries[canonical]?.inspection;
      if (inspection && typeof inspection === "object") {
        job._inspection = inspection;
        const authoritativePostedAt = normalize(inspection?.posting?.posted_at);
        if (authoritativePostedAt) {
          if (!("_metadataPostedAt" in job)) job._metadataPostedAt = job.posted_at || null;
          job.posted_at = authoritativePostedAt;
          job._postedAtBasis = "authoritative";
        }
      }
    }
    return jobs;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function setProfileError(message) {
    const box = document.querySelector("#applyNextProfileError");
    if (!box) return;
    box.textContent = message || "";
    box.classList.toggle("hidden", !message);
  }

  function setProfileSetupMode(active) {
    const main = document.querySelector("main");
    if (!main) return;
    main.classList.toggle("apply-next-profile-mode", Boolean(active));
  }

  function setupPanel(panel) {
    setProfileSetupMode(true);
    panel.innerHTML = "";
    const header = element("div", "apply-next-heading");
    const copy = element("div");
    copy.append(
      element("p", "eyebrow", "private browser profile"),
      element("h2", "", "Apply Next"),
      element("p", "muted", "Import your private strategy once. It stays in this browser's local storage and is never added to the public feed or shared URL.")
    );
    header.append(copy);
    panel.append(header);

    const textarea = element("textarea", "apply-next-profile-input");
    textarea.id = "applyNextProfileInput";
    textarea.rows = 12;
    textarea.placeholder = "Paste your Apply Next profile JSON here…";
    textarea.setAttribute("aria-label", "Paste your Apply Next profile JSON here");
    textarea.autocomplete = "off";
    textarea.spellcheck = false;
    panel.append(textarea);

    const error = element("p", "error-box hidden");
    error.id = "applyNextProfileError";
    panel.append(error);

    const actions = element("div", "apply-next-profile-actions");
    const save = element("button", "primary-btn", "Save private profile");
    save.type = "button";
    save.addEventListener("click", async () => {
      try {
        const parsed = JSON.parse(textarea.value);
        saveProfile(localStorage, parsed);
        setProfileError("");
        await renderPanel(panel);
      } catch (error) {
        setProfileError(error.message || "Invalid profile JSON.");
      }
    });
    actions.append(save);
    panel.append(actions);
  }

  function locationValueText(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string" || typeof value === "number") return normalize(value);
    if (Array.isArray(value)) {
      return value.map(locationValueText).filter(Boolean).join(" · ");
    }
    if (typeof value !== "object") return "";

    if (Array.isArray(value.values)) {
      const values = value.values.map(locationValueText).filter(Boolean);
      if (values.length) return values.join(" · ");
    }

    for (const key of ["text", "label", "display_name", "displayName", "formatted", "formatted_address", "name"]) {
      const text = locationValueText(value[key]);
      if (text) return text;
    }

    const city = locationValueText(value.city);
    const stateValue = locationValueText(value.state || value.region || value.state_code);
    const country = locationValueText(value.country || value.country_code);
    const parts = [city, stateValue, country].filter(Boolean);
    return parts.join(", ");
  }

  function locationDisplayValues(job) {
    const authoritative = (typeof YartchivesUtils !== "undefined" && YartchivesUtils.authoritativeLocationValues)
      ? YartchivesUtils.authoritativeLocationValues(job)
      : [];
    if (authoritative.length > 1) return authoritative;
    const raw = locationValueText(job?._displayLocation) || locationValueText(job?.location);
    if (!raw) return authoritative.length ? authoritative : [];
    const split = raw.split(/\s*(?:;|\||·)\s*/).map(normalize).filter(Boolean);
    return split.length > 1 ? split : [raw];
  }

  function cardLocationText(job) {
    return locationValueText(job?._displayLocation)
      || locationValueText(job?.location)
      || "Location not listed";
  }

  function orderLocationValues(values, primaryDistances, fallbackDistances) {
    return (values || [])
      .map((value, index) => ({
        value,
        index,
        primary: Number.isFinite(primaryDistances?.[index]) ? primaryDistances[index] : Infinity,
        fallback: Number.isFinite(fallbackDistances?.[index]) ? fallbackDistances[index] : Infinity,
      }))
      .sort((a, b) => (
        a.primary - b.primary
        || a.fallback - b.fallback
        || a.index - b.index
      ))
      .map(item => item.value);
  }

  async function addBaseDistances(jobs, profile) {
    for (const job of jobs || []) {
      if (!job || typeof job !== "object") continue;
      job._distanceMiles = null;
      delete job._distanceMilesBasis;
    }

    const zips = (profile?.baseZips || []).filter(value => /^\d{5}$/.test(String(value)));
    if (!zips.length || typeof loadGeoIndex !== "function" || typeof distanceForJob !== "function") return;
    try {
      const geo = await loadGeoIndex();
      const origins = zips.map(zip => geo.zips.get(zip)).filter(Boolean);
      if (!origins.length) return;
      for (const job of jobs) {
        const values = locationDisplayValues(job);
        const perLocation = values.map(value => {
          const pseudoJob = { ...job, location: value, _inspection: null };
          delete pseudoJob._geo;
          return origins.map(origin => distanceForJob(pseudoJob, origin, geo));
        });
        const finiteDistances = perLocation.flat().filter(value => Number.isFinite(value));
        if (finiteDistances.length) {
          job._distanceMiles = Math.min(...finiteDistances);
          job._distanceMilesBasis = "apply-next-profile";
        }
        if (values.length > 1) {
          const primary = perLocation.map(distances => distances[0]);
          const fallback = perLocation.map(distances => {
            const finite = distances.filter(value => Number.isFinite(value));
            return finite.length ? Math.min(...finite) : Infinity;
          });
          job._displayLocation = orderLocationValues(values, primary, fallback).join(" · ");
        } else {
          delete job._displayLocation;
        }
      }
    } catch (_) {
      // Location scoring still has state/remote/relocation fallbacks if ZIP data is unavailable.
    }
  }

  function componentLabel(key) {
    return ({
      fit: "How well you match",
      eligibility: "Eligibility",
      freshness: "How recent it is",
      roi: "Worth applying",
      role: "Role",
      location: "Location convenience",
      link: "Link",
    })[key] || key;
  }

  function componentExplanation(key) {
    return ({
      fit: "Based on your skills, major, degree level, and the job\'s known requirements.",
      freshness: "Newer postings score higher because timing can affect how crowded the applicant pool is.",
      roi: "Balances how valuable this role is for you with the opportunity and competition signals we know.",
      location: "Based on commute distance, remote status, and your location preferences.",
    })[key] || "";
  }

  function scoreBand(key, score, max) {
    if (!max) return "";
    const ratio = Number(score || 0) / max;
    if (key === "fit") return ratio >= 0.75 ? "Strong match" : (ratio >= 0.55 ? "Good match" : "Possible match");
    if (key === "freshness") return ratio >= 0.8 ? "Very recent" : (ratio >= 0.5 ? "Recent" : "Older posting");
    if (key === "roi") return ratio >= 0.75 ? "High value" : (ratio >= 0.55 ? "Worth considering" : "Lower value");
    if (key === "location") return ratio >= 0.75 ? "Very convenient" : (ratio >= 0.55 ? "Manageable" : "Less convenient");
    return "";
  }

  function totalScoreBandClass(score) {
    if (score < 55) return "apply-next-score-low";
    if (score < 75) return "apply-next-score-medium";
    return "apply-next-score-high";
  }

  function decisionHighlights(result) {
    if (result?.excluded || result?.components?.eligibility?.excluded) {
      return ["Excluded by eligibility constraints"];
    }

    const highlights = [];
    const concerns = [];

    const fitRatio = (result?.components?.fit?.score || 0) / (componentMax("fit") || 1);
    if (fitRatio >= 0.75) highlights.push("Strong match");
    else if (fitRatio < 0.55) concerns.push("weak match");

    const roiRatio = (result?.components?.roi?.score || 0) / (componentMax("roi") || 1);
    if (roiRatio >= 0.75) highlights.push("High value");
    else if (roiRatio < 0.55) concerns.push("lower value");

    const freshnessRatio = (result?.components?.freshness?.score || 0) / (componentMax("freshness") || 1);
    if (freshnessRatio >= 0.8) highlights.push("Very recent");
    else if (freshnessRatio >= 0.5) highlights.push("Recent");
    else concerns.push("older posting");

    const locRatio = (result?.components?.location?.score || 0) / (componentMax("location") || 1);
    if (locRatio >= 0.75) highlights.push("Very convenient location");
    else if (locRatio >= 0.55) highlights.push("Manageable location");
    else concerns.push("less convenient location");

    if (result?.inspection?.state === "unavailable") {
      concerns.push("posting unavailable");
    } else if (result?.inspection?.state !== "inspected") {
      concerns.push("unverified evidence");
    }

    const finalHighlights = [];

    if (concerns.length > 0) {
      finalHighlights.push("Concerns: " + concerns.join(", "));
    }

    // take top positive highlights up to 4 total
    const slotsRemaining = 4 - finalHighlights.length;
    finalHighlights.push(...highlights.slice(0, slotsRemaining));

    if (finalHighlights.length === 0) {
      finalHighlights.push("Meets basic profile criteria");
    }

    return finalHighlights;
  }

  function rankingSummary(result) {
    const drivers = [];
    for (const key of ["fit", "freshness", "roi", "location"]) {
      const component = result?.components?.[key];
      const max = componentMax(key);
      if (!component || max <= 0) continue;
      drivers.push({
        key,
        ratio: component.score / max,
        name: key === "fit" ? "profile match" : key === "roi" ? "role value" : key === "freshness" ? "timing" : "location convenience"
      });
    }

    if (!drivers.length) return "Why this is here: based on your profile and the evidence available.";

    drivers.sort((a, b) => b.ratio - a.ratio);

    const topRatio = drivers[0].ratio;
    const positiveDrivers = drivers.filter(d => topRatio - d.ratio <= 0.15 && d.ratio >= 0.55);

    const bottomRatio = drivers[drivers.length - 1].ratio;
    const negativeDrivers = drivers.filter(d => d.ratio - bottomRatio <= 0.15 && d.ratio < 0.55 && !positiveDrivers.includes(d));

    const parts = [];

    const formatNames = (names) => {
      if (names.length === 0) return "";
      if (names.length === 1) return names[0];
      return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
    };

    if (positiveDrivers.length > 0) {
      const names = positiveDrivers.map(d => d.name);
      parts.push(`strongest drivers: ${formatNames(names)}`);
    }
    if (negativeDrivers.length > 0) {
      const names = negativeDrivers.map(d => d.name);
      parts.push(`limited by: ${formatNames(names)}`);
    }

    return parts.length > 0 ? `Why this is here: ${parts.join("; ")}.` : "Why this is here: based on your profile and the evidence available.";
  }

  function componentMax(key) {
    const maxima = (typeof YartchivesApplyNext !== "undefined" && YartchivesApplyNext.SCORE_MAXIMA)
      ? YartchivesApplyNext.SCORE_MAXIMA
      : { fit: 40, eligibility: 0, freshness: 10, roi: 15, role: 20, location: 15, link: 0 };
    return Number(maxima[key] || 0);
  }

  function recommendationCard(result, rank) {
    const job = result.job;
    const card = element("article", "apply-next-card");
    if (job?.id) card.dataset.id = job.id;

    const top = element("div", "apply-next-card-top");
    const titleWrap = element("div");
    titleWrap.append(
      element("p", "apply-next-rank", `#${rank} · ${job.company || "Company not listed"}`),
      element("h3", "", job.title || "Untitled opportunity"),
      element("p", "muted", cardLocationText(job))
    );
    const isAuthoritative = result.inspection?.state === "inspected";
    const postedDate = formatPostedDate(job.posted_at, isAuthoritative);
    if (postedDate) titleWrap.append(element("p", "muted apply-next-posted-date", postedDate));
    const inspectionState = result.inspection?.state || "metadata-only";
    const evidenceStatus = element(
      "span",
      `apply-next-component apply-next-inspection-status apply-next-inspection-${inspectionState}`,
      result.inspection?.label || "Metadata fallback"
    );
    let statusExplanation = "";
    if (inspectionState === "inspected") {
      statusExplanation = "Authoritative employer posting evidence is included in this score.";
    } else if (inspectionState === "unavailable") {
      statusExplanation = "This score falls back to feed metadata because authoritative posting evidence is no longer available.";
    } else {
      statusExplanation = "This score falls back to feed metadata because authoritative posting evidence is unavailable.";
    }
    evidenceStatus.title = statusExplanation;
    evidenceStatus.append(element("span", "sr-only", " " + statusExplanation));
    titleWrap.append(evidenceStatus);

    const scoreClass = `apply-next-score ${totalScoreBandClass(result.total)}`;
    const score = element("div", scoreClass);
    score.append(element("strong", "", String(result.total)), element("span", "", "/100"));
    top.append(titleWrap, score);
    card.append(top);

        const highlights = decisionHighlights(result);
    const highlightsUl = element("ul", "apply-next-highlights");
    for (const h of highlights) {
      highlightsUl.append(element("li", "", h));
    }
    card.append(highlightsUl);

    const breakdown = element("div", "apply-next-breakdown");
    for (const [key, component] of Object.entries(result.components || {})) {
      const max = componentMax(key);
      if (max <= 0) continue;
      const metric = element("div", "apply-next-metric");
      const line = element("div", "apply-next-metric-line");
      const label = element("strong", "", componentLabel(key));
      const scoreText = element("span", "", `${component.score}/${max}`);
      line.append(label, scoreText);
      metric.append(line);
      const band = scoreBand(key, component.score, max);
      if (band) metric.append(element("p", "apply-next-metric-band", band));
      const explanation = componentExplanation(key);
      if (explanation) metric.append(element("p", "apply-next-metric-explanation", explanation));
      breakdown.append(metric);
    }


    const details = element("details", "apply-next-why");
    const summary = element("summary", "", "Why this ranks here");
    details.append(summary, breakdown);

    if (result.inspection?.evidence?.length) {
      const evidenceHeading = element("p", "muted", "Authoritative posting evidence");
      const evidenceList = element("ul");
      for (const evidence of result.inspection.evidence) {
        const li = element("li", "", evidence);
        const text = String(evidence).toLowerCase();
        if (text.includes("unsupported hard required skill") || text.includes("major required gaps") || text.includes("known requirement conflict") || text.includes("required gap")) {
          li.classList.add("apply-next-gap-hard");
        } else if (text.includes("learnable/low-threshold stack gap") || text.includes("required skill only cautiously")) {
          li.classList.add("apply-next-gap-learnable");
        } else if (text.includes("unverified requirement") || text.includes("unverified required domain experience")) {
          li.classList.add("apply-next-gap-unknown");
        }
        evidenceList.append(li);
      }
      details.append(evidenceHeading, evidenceList);
    } else if (result.inspection?.state !== "inspected") {
      details.append(element("p", "muted", "No authoritative posting evidence is attached; metadata is used as a fallback."));
    }

    const list = element("ul");
    for (const [key, component] of Object.entries(result.components || {})) {
      const item = element("li");
      const strong = element("strong", "", `${componentLabel(key)}: `);
      item.append(strong, document.createTextNode(component.detail || "No detail available"));
      list.append(item);
    }
    details.append(list);
    card.append(details);

    const actions = element("div", "apply-next-actions");
    if (job.url) {
      const actionLabel = job.link_kind === "employer_job" ? "View posting ↗" : "Apply ↗";
      const apply = element("a", "primary-btn link-btn", actionLabel);
      apply.href = job.url;
      apply.target = "_blank";
      apply.rel = "noopener noreferrer";
      apply.addEventListener("click", () => {
      });
      actions.append(apply);
    }
    const saved = element("button", "secondary-btn", state.saved.has(job.id) ? "Saved" : "Save");
    saved.type = "button";
    saved.addEventListener("click", () => {
      if (state.saved.has(job.id)) state.saved.delete(job.id);
      else state.saved.add(job.id);
      persist();
      saved.textContent = state.saved.has(job.id) ? "Saved" : "Save";
      updateStats();
    });
    const applied = element("button", "secondary-btn", "Mark applied");
    applied.type = "button";
    applied.addEventListener("click", () => {
      state.applied.add(job.id);
      persist();
      updateQueueOptimistically(document.querySelector("#applyNextPanel"), loadProfile(localStorage), job.id);
      applyFilters();
    });
    const hide = element("button", "icon-btn hide-btn", "×");
    hide.type = "button";
    hide.title = "Hide listing";
    hide.setAttribute("aria-label", "Hide listing");
    hide.addEventListener("click", () => {
      state.hidden.add(job.id);
      persist();
      updateQueueOptimistically(document.querySelector("#applyNextPanel"), loadProfile(localStorage), job.id);
      applyFilters();
    });
    actions.append(saved, applied, hide);
    card.append(actions);

    const feedbackSection = element("div", "apply-next-feedback");

    function renderFeedback() {
      feedbackSection.innerHTML = "";
      const currentFeedback = state.feedback[job.id];

      if (!currentFeedback) {
        const p = element("span", "muted", "Was this recommendation useful?");
        const goodBtn = element("button", "secondary-btn apply-next-feedback-btn", "Good suggestion");
        goodBtn.type = "button";
        goodBtn.addEventListener("click", () => {
          state.feedback[job.id] = { rating: "good" };
          persist();
          renderFeedback();
        });

        const badBtn = element("button", "secondary-btn apply-next-feedback-btn", "Bad suggestion");
        badBtn.type = "button";
        badBtn.addEventListener("click", () => {
          state.feedback[job.id] = { rating: "bad" };
          persist();
          renderFeedback();
        });

        const btnGroup = element("div", "apply-next-feedback-group");
        btnGroup.append(goodBtn, badBtn);
        feedbackSection.append(p, btnGroup);
      } else if (currentFeedback.rating === "good") {
        const p = element("span", "muted", "Rated as a good suggestion.");
        const undoBtn = element("button", "text-btn", "Undo");
        undoBtn.type = "button";
        undoBtn.addEventListener("click", () => {
          delete state.feedback[job.id];
          persist();
          renderFeedback();
        });
        feedbackSection.append(p, undoBtn);

        const noteWrap = element("label", "apply-next-feedback-note");
        noteWrap.append(element("span", "muted", "Anything else? (optional)"));
        const note = element("textarea", "apply-next-feedback-note-input");
        note.rows = 2;
        note.maxLength = 500;
        note.placeholder = "What made this a good suggestion?";
        note.value = currentFeedback.note || "";
        note.addEventListener("input", (e) => {
          const value = e.target.value.trim();
          if (value) state.feedback[job.id].note = value;
          else delete state.feedback[job.id].note;
          persist();
        });
        noteWrap.append(note);
        feedbackSection.append(noteWrap);
      } else if (currentFeedback.rating === "bad") {
        const p = element("span", "muted", "Rated as a bad suggestion.");
        const undoBtn = element("button", "text-btn", "Undo");
        undoBtn.type = "button";
        undoBtn.addEventListener("click", () => {
          delete state.feedback[job.id];
          persist();
          renderFeedback();
        });
        feedbackSection.append(p, undoBtn);

        const reasonWrap = element("div", "apply-next-feedback-reason");
        const reasonLabel = element("span", "muted", "Optional reason:");
        const select = element("select", "apply-next-feedback-select");
        select.innerHTML = `
          <option value="">Select reason...</option>
          <option value="role">Role interest</option>
          <option value="location">Location</option>
          <option value="fit">Requirements/Fit</option>
          <option value="company">Company/Industry</option>
          <option value="other">Other</option>
        `;
        if (currentFeedback.reason) select.value = currentFeedback.reason;

        select.addEventListener("change", (e) => {
          if (e.target.value) {
            state.feedback[job.id].reason = e.target.value;
          } else {
            delete state.feedback[job.id].reason;
          }
          persist();
        });

        reasonWrap.append(reasonLabel, select);
        feedbackSection.append(reasonWrap);

        const noteWrap = element("label", "apply-next-feedback-note");
        noteWrap.append(element("span", "muted", "Anything else? (optional)"));
        const note = element("textarea", "apply-next-feedback-note-input");
        note.rows = 2;
        note.maxLength = 500;
        note.placeholder = "Tell us what was wrong with this suggestion.";
        note.value = currentFeedback.note || "";
        note.addEventListener("input", (e) => {
          const value = e.target.value.trim();
          if (value) state.feedback[job.id].note = value;
          else delete state.feedback[job.id].note;
          persist();
        });
        noteWrap.append(note);
        feedbackSection.append(noteWrap);
      }
    }

    renderFeedback();
    card.append(feedbackSection);

    return card;
  }

  function renderEmptyState(type, container) {
    const empty = element("div", "apply-next-empty");
    const p = element("p", "apply-next-note");

    if (type === "loading") {
      p.textContent = "Finding your best matches…";
      p.setAttribute("role", "status");
      p.setAttribute("aria-live", "polite");
      empty.append(p);
    } else if (type === "error") {
      p.textContent = "Apply Next could not load the current feed.";
      const retryBtn = element("button", "primary-btn apply-next-empty-action", "Retry");
      retryBtn.type = "button";
      retryBtn.addEventListener("click", () => renderPanel(container.closest(".apply-next-panel")));
      empty.append(p, retryBtn);
    } else if (type === "exhausted") {
      p.textContent = "You have saved, applied to, or hidden all eligible Apply Next candidates. Close Apply Next to explore the main feed, or wait for new matches to be posted.";
      const closeBtn = element("button", "primary-btn apply-next-empty-action", "Close Apply Next");
      closeBtn.type = "button";
      closeBtn.addEventListener("click", () => document.querySelector("#applyNextBtn")?.click());
      empty.append(p, closeBtn);
    } else if (type === "no-recommendations") {
      p.textContent = "No eligible Apply Next candidates are available yet. Try adjusting your profile, or explore the main feed.";
      const editBtn = element("button", "primary-btn apply-next-empty-action", "Edit profile");
      editBtn.type = "button";
      editBtn.addEventListener("click", () => {
        const panel = container.closest(".apply-next-panel");
        setupPanel(panel);
        const input = document.querySelector("#applyNextProfileInput");
        if (input) input.value = JSON.stringify(loadProfile(localStorage), null, 2);
      });
      empty.append(p, editBtn);
    } else if (type === "fresh-empty") {
      p.textContent = `No strong matches were posted within the last ${FRESH_MAX_AGE_DAYS} days.`;
      const switchBtn = element("button", "primary-btn apply-next-empty-action", "View all recommendations");
      switchBtn.type = "button";
      switchBtn.addEventListener("click", () => {
        const panel = container.closest(".apply-next-panel");
        const btn = panel.querySelector('.apply-next-view-btn[data-queue-view="recommended"]');
        if (btn) btn.click();
      });
      empty.append(p, switchBtn);
    }

    return empty;
  }

  function renderCurrentQueue(panel, profile, poolCount, status = "success") {
    if (!panel || !profile) return;
    const list = panel.querySelector(".apply-next-list");
    const note = panel.querySelector(".apply-next-queue-note");
    const loadMore = panel.querySelector(".apply-next-load-more");
    if (!list || !note) return;

    if (status === "loading" || status === "error") {
      note.textContent = "";
      list.innerHTML = "";
      list.append(renderEmptyState(status, list));
      if (loadMore) loadMore.classList.add("hidden");
      return;
    }

    const now = new Date();
    const allForView = queueResults(lastRankedResults, activeQueueView, now);
    const visibleCount = queueVisibleCounts[activeQueueView] || TOP_N;
    const ranked = visibleQueueResults(lastRankedResults, activeQueueView, now, visibleCount);
    const inspectedCount = ranked.filter(result => result.inspection?.state === "inspected").length;

    panel.querySelectorAll(".apply-next-view-btn").forEach(button => {
      const active = button.dataset.queueView === activeQueueView;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });

    if (activeQueueView === "fresh") {
      note.textContent = `Showing ${ranked.length} of ${allForView.length} strong matches posted within the last ${FRESH_MAX_AGE_DAYS} days. Ranked by overall Apply Next score, not posting time. ${inspectedCount} of these ${ranked.length || 0} recommendations use authoritative posting evidence; the rest use metadata fallback.`;
    } else {
      note.textContent = `Showing ${ranked.length} of ${allForView.length} recommended options from ${poolCount.toLocaleString()} current candidates. ${inspectedCount} of these ${ranked.length || 0} recommendations use authoritative posting evidence; the rest use metadata fallback. Known non-${profile.targetTerm} terms plus applied/hidden jobs are excluded.`;
    }

    list.innerHTML = "";
    ranked.forEach((result, index) => list.append(recommendationCard(result, index + 1)));

    if (!ranked.length) {
      if (activeQueueView === "fresh") {
        list.append(renderEmptyState("fresh-empty", list));
      } else if (lastTotalEligibleCount > 0 && poolCount === 0) {
        list.append(renderEmptyState("exhausted", list));
      } else {
        list.append(renderEmptyState("no-recommendations", list));
      }
    }

    if (loadMore) {
      const remaining = Math.max(0, allForView.length - ranked.length);
      loadMore.classList.toggle("hidden", remaining === 0);
      loadMore.textContent = remaining > 0 ? `Load 10 more` : "";
    }
  }

  function updateQueueOptimistically(panel, profile, appliedJobId) {
    const targetPanel = panel || (typeof document !== "undefined" ? document.querySelector("#applyNextPanel") : null);
    if (!targetPanel) return;

    if (Array.isArray(lastRankedResults) && lastRankedResults.length) {
      lastRankedResults = lastRankedResults.filter(r => r.job && r.job.id !== appliedJobId && !state.applied?.has(r.job.id) && !state.hidden?.has(r.job.id));
    } else if (typeof feed !== "undefined" && Array.isArray(feed?.jobs) && profile && typeof YartchivesApplyNext !== "undefined") {
      const pool = candidatePool(feed.jobs, profile, state);
      lastRankedResults = YartchivesApplyNext.rankJobs(pool, profile, new Date());
    }

    if (typeof feed !== "undefined" && Array.isArray(feed?.jobs) && profile) {
      lastTotalEligibleCount = eligiblePoolCount(feed.jobs, profile);
    }

    const poolCount = (typeof feed !== "undefined" && Array.isArray(feed?.jobs) && profile)
      ? candidatePool(feed.jobs, profile, state).length
      : 0;
    renderCurrentQueue(targetPanel, profile, poolCount);
  }

  function buildQueueSkeleton(profile, panel, explanation) {
    const fragment = document.createDocumentFragment();

    const heading = element("div", "apply-next-heading");
    const copy = element("div");
    copy.append(
      element("p", "eyebrow", "your next application queue"),
      element("h2", "", "Apply Next"),
      element("p", "muted", profileSummary(profile) || "Private strategy loaded")
    );
    const controls = element("div", "apply-next-profile-actions");
    const edit = element("button", "ghost-btn", "Edit profile");
    edit.type = "button";
    edit.addEventListener("click", () => {
      setupPanel(panel);
      const input = document.querySelector("#applyNextProfileInput");
      if (input) input.value = JSON.stringify(profile, null, 2);
    });
    const clear = element("button", "text-btn", "Clear private profile");
    clear.type = "button";
    clear.addEventListener("click", () => {
      localStorage.removeItem(STORAGE_KEY);
      setupPanel(panel);
    });
    controls.append(edit, clear);
    heading.append(copy, controls);
    fragment.append(heading);

    const viewTabs = element("div", "apply-next-view-tabs");
    viewTabs.setAttribute("role", "group");
    viewTabs.setAttribute("aria-label", "Apply Next recommendation view");
    for (const [view, label] of [["recommended", "Recommended"], ["fresh", "Fresh"]]) {
      const button = element("button", "apply-next-view-btn", label);
      button.type = "button";
      button.dataset.queueView = view;
      button.addEventListener("click", () => {
        if (activeQueueView === view) return;
        activeQueueView = view;
        renderCurrentQueue(panel, profile, candidatePool(feed.jobs, profile, state).length);
      });
      viewTabs.append(button);
    }
    fragment.append(viewTabs);

    const note = element("p", "apply-next-note apply-next-queue-note");
    fragment.append(note);
    if (explanation) {
      const explanationEl = element("p", "apply-next-explanation apply-next-note", explanation);
      fragment.append(explanationEl);
    }

    const list = element("div", "apply-next-list");
    fragment.append(list);

    const loadMore = element("button", "primary-btn apply-next-load-more hidden", "Load 10 more");
    loadMore.type = "button";
    loadMore.addEventListener("click", () => {
      queueVisibleCounts[activeQueueView] = (queueVisibleCounts[activeQueueView] || TOP_N) + TOP_N;
      renderCurrentQueue(panel, profile, candidatePool(feed.jobs, profile, state).length);
    });
    fragment.append(loadMore);
    return fragment;
  }

  async function renderQueue(panel, profile) {
    setProfileSetupMode(true);

    panel.innerHTML = "";
    panel.append(buildQueueSkeleton(profile, panel, null));
    renderCurrentQueue(panel, profile, 0, "loading");
    panel.setAttribute("aria-busy", "true");

    const slowLoadingTimer = setTimeout(() => {
      const loadingMessage = panel.querySelector(".apply-next-empty .apply-next-note");
      if (loadingMessage && panel.getAttribute("aria-busy") === "true") {
        loadingMessage.textContent = "Still finding your best matches…";
      }
    }, 1500);

    // Let the browser paint the shell, disabled button, and loading copy before
    // synchronous candidate filtering/ranking work starts.
    await YartchivesUtils.waitForBrowserPaint();

    try {
      if (typeof feed === "undefined" || !Array.isArray(feed.jobs)) throw new Error("Feed not available");

      const pool = candidatePool(feed.jobs, profile, state);
      lastTotalEligibleCount = eligiblePoolCount(feed.jobs, profile);

      const artifact = await loadInspectionArtifact();
      attachInspections(pool, artifact);
      await addBaseDistances(pool, profile);
      const ranked = YartchivesApplyNext.rankJobs(pool, profile, new Date());

      const explanation = explainProfileChange(lastProfile, profile, lastRankedResults?.[0]?.job?.id, ranked?.[0]?.job?.id);

      lastRankedResults = ranked;
      lastProfile = profile;

      panel.innerHTML = "";
      panel.append(buildQueueSkeleton(profile, panel, explanation));
      renderCurrentQueue(panel, profile, pool.length);
    } catch (error) {
      console.error(error);
      panel.innerHTML = "";
      panel.append(buildQueueSkeleton(profile, panel, null));
      renderCurrentQueue(panel, profile, 0, "error");
    } finally {
      clearTimeout(slowLoadingTimer);
      panel.setAttribute("aria-busy", "false");
    }
  }

  async function renderPanel(panel) {
    const profile = loadProfile(localStorage);
    if (!profile) setupPanel(panel);
    else await renderQueue(panel, profile);
  }

  function init() {
    if (typeof YartchivesApplyNext === "undefined") return;
    loadInspectionArtifact();
    const headerActions = document.querySelector(".header-actions");
    const main = document.querySelector("main");
    if (!headerActions || !main || document.querySelector("#applyNextBtn")) return;

    const button = element("button", "primary-btn apply-next-open", "Apply Next");
    button.id = "applyNextBtn";
    button.type = "button";
    button.setAttribute("aria-controls", "applyNextPanel");
    headerActions.prepend(button);

    const panel = element("section", "panel apply-next-panel hidden");
    panel.id = "applyNextPanel";
    panel.setAttribute("aria-label", "Apply Next");
    const stats = main.querySelector(".stats");
    main.insertBefore(panel, stats ? stats.nextSibling : main.firstChild);

    button.addEventListener("click", async () => {
      const opening = panel.classList.contains("hidden");
      panel.classList.toggle("hidden", !opening);
      button.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) {
        activeQueueView = "recommended";
        queueVisibleCounts = { recommended: TOP_N, fresh: TOP_N };
        await YartchivesUtils.runWithPendingUi({
          control: button,
          pendingLabel: "Finding matches…",
          prepare: () => {
            setProfileSetupMode(true);
            panel.scrollIntoView({ behavior: "smooth", block: "start" });
          },
          work: () => renderPanel(panel),
        });
      } else {
        setProfileSetupMode(false);
      }
    });

    if (typeof renderJobs === "function") {
      const priorRenderJobs = renderJobs;
      renderJobs = function () {
        priorRenderJobs();
        if (!panel.classList.contains("hidden") && loadProfile(localStorage)) renderPanel(panel);
      };
    }
  }

  return {
    STORAGE_KEY,
    INSPECTION_URL,
    TOP_N,
    FRESH_MAX_AGE_DAYS,
    FRESH_MIN_SCORE,
    postedAgeDays,
    freshRankedResults,
    queueResults,
    visibleQueueResults,
    validateProfile,
    loadProfile,
    saveProfile,
    knownWrongTerm,
    candidatePool,
    profileSummary,
    formatPostedDate,
    locationValueText,
    locationDisplayValues,
    cardLocationText,
    orderLocationValues,
    emptyInspectionArtifact,
    loadInspectionArtifact,
    attachInspections,
    addBaseDistances,
    componentLabel,
    componentExplanation,
    scoreBand,
    totalScoreBandClass,
    decisionHighlights,
    rankingSummary,
    componentMax,
    renderQueue,
    updateQueueOptimistically,
    explainProfileChange,
    setProfileSetupMode,
    init,
  };
});