const PROFILE_LABELS = {
  all: "All",
  "tech-business": "Tech + Business",
  cs: "Computer Science",
  "finance-econ": "Finance / Econ",
  mechanical: "Mechanical",
  aero: "Aero / Astro",
  electrical: "Electrical",
  policy: "Policy / Government",
  health: "Premed / Health",
};

const PROFILE_TITLES = {
  all: "All opportunities",
  "tech-business": "Tech + Business",
  cs: "Computer Science",
  "finance-econ": "Finance / Economics",
  mechanical: "Mechanical Engineering",
  aero: "Aerospace / Astronautical",
  electrical: "Electrical Engineering",
  policy: "Policy / Government",
  health: "Premed / Health",
};

const STATE_NAMES = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", DC: "District of Columbia",
  FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois",
  IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana",
  ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan", MN: "Minnesota",
  MS: "Mississippi", MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada",
  NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon",
  PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota",
  TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia",
  WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming",
};
const STATE_CODE_BY_NAME = Object.fromEntries(Object.entries(STATE_NAMES).map(([code, name]) => [name.toLowerCase(), code.toLowerCase()]));
const STORAGE_KEY = "yartchives-state-v1";
const PAGE_SIZE = 40;
const PRIORITY_STATE = "CT";
const GEO_DATA_URL = "data/geo-index.json";
const BUILD_SHA = document.querySelector('meta[name="yartchives-build"]')?.content || "";
const FEED_DATA_URL = BUILD_SHA && !BUILD_SHA.startsWith("__")
  ? `data/listings.json?v=${encodeURIComponent(BUILD_SHA)}`
  : "data/listings.json";

let feed = { jobs: [], sources: {}, generated_at: null };
let feedReady = false;
let filtered = [];
let visibleLimit = PAGE_SIZE;
let filterRequestId = 0;
let geoIndex = null;
let geoLoadingPromise = null;
let geoError = null;

const state = {
  profile: "all",
  search: "",
  location: "",
  radius: "50",
  freshness: "all",
  status: "all",
  saved: new Set(),
  applied: new Set(),
  hidden: new Set(),
  feedback: {},
};

const els = {
  profileChips: document.querySelector("#profileChips"),
  searchInput: document.querySelector("#searchInput"),
  locationInput: document.querySelector("#locationInput"),
  radiusInput: document.querySelector("#radiusInput"),
  freshnessSelect: document.querySelector("#freshnessSelect"),
  statusSelect: document.querySelector("#statusSelect"),
  jobs: document.querySelector("#jobs"),
  template: document.querySelector("#jobCardTemplate"),
  loadMoreBtn: document.querySelector("#loadMoreBtn"),
  shownCount: document.querySelector("#shownCount"),
  totalCount: document.querySelector("#totalCount"),
  newCount: document.querySelector("#newCount"),
  savedCount: document.querySelector("#savedCount"),
  hiddenCount: document.querySelector("#hiddenCount"),
  resultsTitle: document.querySelector("#resultsTitle"),
  resultsNote: document.querySelector("#resultsNote"),
  feedMeta: document.querySelector("#feedMeta"),
  siteMeta: document.querySelector("#siteMeta"),
  sourceHealth: document.querySelector("#sourceHealth"),
  errorBox: document.querySelector("#errorBox"),
  shareBtn: document.querySelector("#shareBtn"),
  clearFiltersBtn: document.querySelector("#clearFiltersBtn"),
};

function normalizePlace(value) {
  return (value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function currentZip() {
  const value = state.location.trim();
  return /^\d{5}$/.test(value) ? value : null;
}

function radiusMiles() {
  const parsed = Number(state.radius);
  return Number.isFinite(parsed) ? Math.min(500, Math.max(5, parsed)) : 50;
}

function loadSavedState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    for (const key of ["profile", "search", "location", "radius", "freshness", "status"]) {
      if (saved[key] !== undefined) state[key] = saved[key];
    }
    state.saved = new Set(saved.saved || []);
    state.applied = new Set(saved.applied || []);
    state.hidden = new Set(saved.hidden || []);
    state.feedback = saved.feedback || {};
    if (!["all", "saved", "applied", "hidden"].includes(state.status)) state.status = "all";
  } catch (_) {}

  const params = new URLSearchParams(location.search);
  if (params.has("profile") && PROFILE_LABELS[params.get("profile")]) state.profile = params.get("profile");
  if (params.has("q")) state.search = params.get("q") || "";
  if (params.has("loc")) state.location = params.get("loc") || "";
  if (params.has("miles")) state.radius = params.get("miles") || "50";
  if (params.has("fresh")) state.freshness = params.get("fresh") || "all";
}

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    profile: state.profile,
    search: state.search,
    location: state.location,
    radius: state.radius,
    freshness: state.freshness,
    status: state.status,
    saved: [...state.saved],
    applied: [...state.applied],
    hidden: [...state.hidden],
    feedback: state.feedback,
  }));
}


function syncControls() {
  els.searchInput.value = state.search;
  els.locationInput.value = state.location;
  els.radiusInput.value = state.radius;
  els.radiusInput.disabled = !currentZip();
  els.radiusInput.title = currentZip() ? "Radius from this ZIP code" : "Enter a 5-digit ZIP code to use radius filtering";
  els.freshnessSelect.value = state.freshness;
  els.statusSelect.value = state.status;
  document.querySelectorAll(".quick-locations button").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.location.toLowerCase() === state.location.trim().toLowerCase());
  });
}

function renderProfiles() {
  els.profileChips.innerHTML = "";
  for (const [key, label] of Object.entries(PROFILE_LABELS)) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.classList.toggle("active", state.profile === key);
    btn.addEventListener("click", () => {
      state.profile = key;
      visibleLimit = PAGE_SIZE;
      persist();
      renderProfiles();
      applyFilters();
    });
    els.profileChips.appendChild(btn);
  }
}

function searchable(job) {
  return [job.company, job.title, job.location, ...(job.profiles || []), ...(job.source_names || [])]
    .filter(Boolean).join(" ").toLowerCase();
}

function jobAgeDays(job) {
  if (!job.posted_at) return null;
  const ms = Date.now() - new Date(job.posted_at).getTime();
  return Math.max(0, ms / 86400000);
}

function matchesTextLocation(job) {
  const query = state.location.trim().toLowerCase();
  if (!query) return true;
  const tokens = query.split(/[,;/]+/).map(x => x.trim()).filter(Boolean);
  const stateTokens = (job.states || []).map(x => x.toLowerCase());
  const loc = (job.location || "").toLowerCase();

  return tokens.some(token => {
    if (token === "remote") return stateTokens.includes("remote") || loc.includes("remote");
    if (/^[a-z]{2}$/.test(token)) return stateTokens.includes(token);
    if (STATE_CODE_BY_NAME[token]) return stateTokens.includes(STATE_CODE_BY_NAME[token]);
    return loc.includes(token);
  });
}

function parseCsvLine(line) {
  const out = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (ch === "," && !quoted) {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

async function loadGeoIndex() {
  if (geoIndex) return geoIndex;
  if (geoLoadingPromise) return geoLoadingPromise;

  geoLoadingPromise = (async () => {
    let response;
    try {
      response = await fetch(GEO_DATA_URL, { cache: "no-cache" });
    } catch (error) {
      const classified = new Error("ZIP data request failed");
      classified.code = "geo_network";
      classified.cause = error;
      throw classified;
    }
    if (!response.ok) {
      const classified = new Error(`ZIP data request failed (${response.status})`);
      classified.code = `geo_http_${Number(response.status) || "error"}`;
      throw classified;
    }

    let payload;
    try {
      payload = await response.json();
    } catch (error) {
      const classified = new Error("ZIP data is malformed");
      classified.code = "geo_malformed";
      classified.cause = error;
      throw classified;
    }
    if (!payload || !Array.isArray(payload.zips) || !Array.isArray(payload.cities)) {
      const classified = new Error("ZIP data is malformed");
      classified.code = "geo_malformed";
      throw classified;
    }

    const zips = new Map();
    try {
      for (const row of payload.zips) {
        if (!Array.isArray(row) || row.length < 5) continue;
        const [zip, lat, lon, st, city] = row;
        if (!/^\d{5}$/.test(String(zip)) || !Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        zips.set(String(zip), { lat, lon, state: st, city, zip: String(zip), precision: "zip" });
      }
    } catch (error) {
      const classified = new Error("ZIP index construction failed");
      classified.code = "geo_index_zips";
      classified.cause = error;
      throw classified;
    }

    const cities = new Map();
    const citiesByState = new Map();
    try {
      for (const row of payload.cities) {
        if (!Array.isArray(row) || row.length < 4) continue;
        const [st, city, lat, lon] = row;
        if (!st || !city || !Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        const point = { lat, lon, state: st, city, precision: "city" };
        cities.set(`${st}|${city}`, point);
        if (!citiesByState.has(st)) citiesByState.set(st, []);
        citiesByState.get(st).push([city, point]);
      }
    } catch (error) {
      const classified = new Error("City index construction failed");
      classified.code = "geo_index_cities";
      classified.cause = error;
      throw classified;
    }

    try {
      for (const list of citiesByState.values()) list.sort((a, b) => b[0].length - a[0].length);
    } catch (error) {
      const classified = new Error("City index ordering failed");
      classified.code = "geo_index_sort";
      classified.cause = error;
      throw classified;
    }

    geoIndex = { zips, cities, citiesByState };
    geoError = null;
    return geoIndex;
  })().catch(error => {
    let classified = error;
    if (!classified?.code) {
      classified = new Error("ZIP index load failed internally");
      classified.code = "geo_internal";
      classified.cause = error;
    }
    geoError = classified;
    geoLoadingPromise = null;
    throw classified;
  });

  return geoLoadingPromise;
}

function addCandidate(candidates, value) {
  const normalized = normalizePlace(value)
    .replace(/^\d+\s+locations?\s+/, "")
    .replace(/\b(?:united states|usa|us)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (normalized) candidates.add(normalized);
}

function coordinatesForJob(job, geo) {
  if (job._geoResolved) return job._geo || null;
  job._geoResolved = true;

  const states = (job.states || []).filter(x => /^[A-Z]{2}$/.test(x) && x !== "US");
  if (!states.length) {
    job._geo = null;
    return null;
  }

  const raw = job.location || "";
  const normalizedLocation = ` ${normalizePlace(raw)} `;
  const candidates = new Set();
  const commaParts = raw.split(",");
  if (commaParts.length > 1) addCandidate(candidates, commaParts[0]);
  for (const segment of raw.split(/[\/;|]+/)) addCandidate(candidates, segment.split(",")[0]);

  const found = [];
  for (const st of states) {
    const full = STATE_NAMES[st] || "";
    const beforeState = full
      ? raw.match(new RegExp(`^(.+?)(?:,|[-\\s]+)(?:${st}|${full.replace(/ /g, "\\s+")})(?:\\b|-)`, "i"))
      : raw.match(new RegExp(`^(.+?)(?:,|[-\\s]+)${st}(?:\\b|-)`, "i"));
    if (beforeState) addCandidate(candidates, beforeState[1]);

    const afterState = raw.match(new RegExp(`(?:^|\\b)(?:US|USA)?[-\\s]*${st}[-\\s]+(.+?)(?:[-~,/]|$)`, "i"));
    if (afterState) addCandidate(candidates, afterState[1].replace(/-\d.*$/, ""));

    for (const candidate of candidates) {
      const direct = geo.cities.get(`${st}|${candidate}`);
      if (direct) found.push(direct);
    }

    if (!found.length) {
      const cities = geo.citiesByState.get(st) || [];
      for (const [cityName, point] of cities) {
        if (cityName.length < 4) continue;
        if (normalizedLocation.includes(` ${cityName} `)) {
          found.push(point);
          break;
        }
      }
    }
  }

  job._geo = found.length ? found : null;
  return job._geo;
}

function milesBetween(a, b) {
  const toRad = deg => deg * Math.PI / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 3958.7613 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function distanceForJob(job, origin, geo) {
  const points = coordinatesForJob(job, geo);
  if (!points?.length) return null;
  return Math.min(...points.map(point => milesBetween(origin, point)));
}

function sortFiltered(jobs, zipMode) {
  jobs.sort((a, b) => {
    if (!state.location.trim()) {
      const aPriority = (a.states || []).includes(PRIORITY_STATE) ? 1 : 0;
      const bPriority = (b.states || []).includes(PRIORITY_STATE) ? 1 : 0;
      if (aPriority !== bPriority) return bPriority - aPriority;
    }
    if (zipMode) {
      const ad = Number.isFinite(a._distanceMiles) ? a._distanceMiles : Infinity;
      const bd = Number.isFinite(b._distanceMiles) ? b._distanceMiles : Infinity;
      if (ad !== bd) return ad - bd;
    }
    const at = a.posted_at ? new Date(a.posted_at).getTime() : 0;
    const bt = b.posted_at ? new Date(b.posted_at).getTime() : 0;
    if (at !== bt) return bt - at;
    return (a.company || "").localeCompare(b.company || "");
  });
}

async function applyFilters() {
  const requestId = ++filterRequestId;
  const q = state.search.trim().toLowerCase();
  const hasFreshnessLimit = state.freshness !== "all";
  const maxDays = hasFreshnessLimit ? Number(state.freshness) : Infinity;
  const zip = currentZip();
  let origin = null;
  let geo = null;

  if (zip) {
    els.resultsNote.textContent = `Loading ${radiusMiles()}-mile ZIP radius…`;
    try {
      geo = await loadGeoIndex();
      origin = geo.zips.get(zip) || null;
    } catch (_) {
      if (requestId !== filterRequestId) return;
      filtered = [];
      renderJobs();
      updateStats();
      els.resultsNote.textContent = "ZIP radius data could not be loaded. Try a state/city filter instead.";
      return;
    }
    if (requestId !== filterRequestId) return;
  }

  filtered = feed.jobs.filter(job => {
    if (state.status === "hidden") {
      if (!state.hidden.has(job.id)) return false;
    } else {
      if (state.hidden.has(job.id)) return false;
    }
    if (state.profile !== "all" && !(job.profiles || []).includes(state.profile)) return false;
    if (q && !searchable(job).includes(q)) return false;
    const ageDays = jobAgeDays(job);
    if (hasFreshnessLimit && ageDays === null) return false;
    if (ageDays !== null && ageDays > maxDays) return false;
    if (state.status === "saved" && !state.saved.has(job.id)) return false;
    if (state.status === "applied" && !state.applied.has(job.id)) return false;

    if (zip) {
      if (!origin) return false;
      const distance = distanceForJob(job, origin, geo);
      job._distanceMiles = distance;
      return distance !== null && distance <= radiusMiles();
    }

    job._distanceMiles = null;
    return matchesTextLocation(job);
  });

  sortFiltered(filtered, Boolean(zip));
  renderJobs();
  updateStats();
  updateResultsNote(origin);
}

function relativeAge(job) {
  if (!job.posted_at) return "date unknown";
  const delta = Math.max(0, Date.now() - new Date(job.posted_at).getTime());
  const hours = Math.floor(delta / 3600000);
  if (hours < 1) return "<1h";
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  return `${Math.floor(days / 30)}mo`;
}

function humanProfile(profile) {
  return PROFILE_LABELS[profile] || profile.replaceAll("-", " ");
}

function renderJobs() {
  els.jobs.innerHTML = "";
  const slice = filtered.slice(0, visibleLimit);

  if (!slice.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    if (state.status === "saved") {
      if (state.saved.size === 0) {
        empty.innerHTML = "<strong>No saved internships yet.</strong><br>Click the Save button on any internship card to save it for later.";
      } else {
        empty.innerHTML = "<strong>No saved internships match your current filters.</strong><br>Try clearing or broadening your search, location, career area, or freshness filters.<br>";
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "secondary-btn empty-reset-btn";
        resetBtn.style.marginTop = "12px";
        resetBtn.textContent = "Reset filters";
        resetBtn.addEventListener("click", () => els.clearFiltersBtn?.click());
        empty.appendChild(resetBtn);
      }
    } else if (state.status === "applied") {
      if (state.applied.size === 0) {
        empty.innerHTML = "<strong>No applied internships yet.</strong><br>Click Applied on any internship card when you've submitted an application.";
      } else {
        empty.innerHTML = "<strong>No applied internships match your current filters.</strong><br>Try clearing or broadening your search, location, career area, or freshness filters.<br>";
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "secondary-btn empty-reset-btn";
        resetBtn.style.marginTop = "12px";
        resetBtn.textContent = "Reset filters";
        resetBtn.addEventListener("click", () => els.clearFiltersBtn?.click());
        empty.appendChild(resetBtn);
      }
    } else if (state.status === "hidden") {
      if (state.hidden.size === 0) {
        empty.innerHTML = "<strong>No hidden internships.</strong><br>Click the Hide button on any internship card to hide it on this browser.";
      } else {
        empty.innerHTML = "<strong>No hidden internships match your current filters.</strong><br>Try clearing or broadening your search, location, career area, or freshness filters.<br>";
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "secondary-btn empty-reset-btn";
        resetBtn.style.marginTop = "12px";
        resetBtn.textContent = "Reset filters";
        resetBtn.addEventListener("click", () => els.clearFiltersBtn?.click());
        empty.appendChild(resetBtn);
      }
    } else {
      empty.innerHTML = "<strong>No matches.</strong><br>Try a broader profile, location, radius, or freshness window.";
    }
    els.jobs.appendChild(empty);
  }

  const frag = document.createDocumentFragment();
  for (const job of slice) {
    const card = els.template.content.firstElementChild.cloneNode(true);
    card.dataset.id = job.id;
    card.querySelector(".company").textContent = job.company || "Company not listed";
    card.querySelector(".title").textContent = job.title;
    card.querySelector(".location").textContent = job.location || "Location not listed";
    const age = card.querySelector(".age");
    const distance = currentZip() && Number.isFinite(job._distanceMiles) ? ` · ${Math.round(job._distanceMiles)} mi` : "";
    age.textContent = `${relativeAge(job)}${distance}`;
    age.classList.toggle("unknown", !job.posted_at);
    age.title = job.posted_at ? `Posted: ${new Date(job.posted_at).toLocaleString()}` : "Posting date unavailable from this source";

    const tags = card.querySelector(".tags");
    for (const profile of (job.profiles || []).filter(x => x !== "general").slice(0, 4)) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = humanProfile(profile);
      tags.appendChild(tag);
    }
    if (job.term) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = job.term;
      tags.appendChild(tag);
    }

    const sources = card.querySelector(".sources");
    for (const source of (job.source_names || []).slice(0, 4)) {
      const pill = document.createElement("span");
      pill.className = "source-pill";
      pill.textContent = source;
      sources.appendChild(pill);
    }

    const saveBtn = card.querySelector(".save-btn");
    saveBtn.classList.toggle("active", state.saved.has(job.id));
    saveBtn.textContent = state.saved.has(job.id) ? "Saved" : "Save";
    saveBtn.addEventListener("click", () => {
      toggleSet(state.saved, job.id);
      if (state.saved.has(job.id)) typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("saved");
      persist();
      applyFilters();
    });

    const appliedBtn = card.querySelector(".applied-btn");
    appliedBtn.classList.toggle("active", state.applied.has(job.id));
    appliedBtn.textContent = state.applied.has(job.id) ? "Applied ✓" : "Applied";
    appliedBtn.addEventListener("click", () => {
      toggleSet(state.applied, job.id);
      persist();
      applyFilters();
    });

    const applyBtn = card.querySelector(".apply-btn");
    if (job.url) {
      applyBtn.href = job.url;
      if (job.link_kind === "employer_job") {
        applyBtn.textContent = "View posting ↗";
        applyBtn.addEventListener("click", () => {
          typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("apply_clicked");
        });
      } else {
        applyBtn.addEventListener("click", () => {
          typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("apply_clicked");
          state.applied.add(job.id);
          persist();
        });
      }
    } else {
      applyBtn.textContent = "Source";
      applyBtn.href = (job.source_urls || ["https://github.com/kaamilbadami/yartchives"])[0];
    }

    card.querySelector(".hide-btn").addEventListener("click", () => {
      state.hidden.add(job.id);
      typeof YartchivesAnalytics !== "undefined" && YartchivesAnalytics.track("hidden");
      persist();
      applyFilters();
    });

    frag.appendChild(card);
  }
  els.jobs.appendChild(frag);
  els.loadMoreBtn.classList.toggle("hidden", visibleLimit >= filtered.length);
  els.resultsTitle.textContent = PROFILE_TITLES[state.profile] || "Opportunities";
}

function toggleSet(set, id) {
  if (set.has(id)) set.delete(id); else set.add(id);
}

function updateStats() {
  els.shownCount.textContent = filtered.length.toLocaleString();
  els.totalCount.textContent = feed.jobs.length.toLocaleString();
  els.newCount.textContent = feed.jobs.filter(j => {
    const d = jobAgeDays(j);
    return d !== null && d <= 7;
  }).length.toLocaleString();
  els.savedCount.textContent = state.saved.size.toLocaleString();
}

function updateResultsNote(origin = null) {
  if (!els.resultsNote) return;
  const zip = currentZip();
  if (zip) {
    if (!origin) {
      els.resultsNote.textContent = geoError ? "ZIP radius data unavailable." : `ZIP ${zip} was not found in the radius dataset.`;
    } else {
      els.resultsNote.textContent = `Within ${radiusMiles()} miles of ${zip} (${origin.city}, ${origin.state}). Distances use approximate city/ZIP centroids.`;
    }
    return;
  }
  if (!state.location.trim()) {
    els.resultsNote.textContent = "Connecticut listings are ranked first when no location filter is selected.";
  } else if (state.freshness === "all") {
    els.resultsNote.textContent = "Any age includes listings whose source does not expose a reliable posting date.";
  } else {
    els.resultsNote.textContent = "Freshness uses the source/employer posting date. Date-unknown listings are hidden in this view.";
  }
}

function renderHealth() {
  els.sourceHealth.innerHTML = "";
  const entries = YartchivesUtils.groupSourceHealth(feed.sources || {});
  for (const src of entries) {
    const row = document.createElement("div");
    row.className = "source-row";
    const name = document.createElement("span");
    name.textContent = src.name;
    const status = document.createElement("span");
    if (!src.configuredCount) {
      status.className = "skip";
      status.textContent = "not configured";
    } else if (!src.failureCount) {
      status.className = "ok";
      status.textContent = `${Number(src.count || 0).toLocaleString()} ✓`;
    } else {
      status.className = "fail";
      const healthy = src.successCount ? `${Number(src.count || 0).toLocaleString()} ✓ · ` : "";
      const detail = src.errors.length ? ` · ${src.errors.join(" · ")}` : "";
      status.textContent = `${healthy}${src.failureCount} failed${detail}`;
    }
    row.append(name, status);
    els.sourceHealth.appendChild(row);
  }
}

function formatEasternTimestamp(value) {
  return new Date(value).toLocaleString(undefined, {
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
}

function updateFeedMeta() {
  if (!feed.generated_at) {
    els.feedMeta.textContent = "Feed has not been built yet.";
    return;
  }
  const when = new Date(feed.generated_at);
  const active = YartchivesUtils.groupSourceHealth(feed.sources || {}).filter(source => source.successCount > 0).length;
  els.feedMeta.textContent = `Updated ${formatEasternTimestamp(when)} · ${active} active sources`;
}

function formatSiteAge(value, nowValue = Date.now()) {
  const deployed = new Date(value);
  const now = Number(nowValue);
  if (!Number.isFinite(deployed.getTime()) || !Number.isFinite(now)) return null;
  const minutes = Math.max(0, Math.floor((now - deployed.getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

const DEPLOY_STATUS_URL = "https://api.github.com/repos/kaamilbadami/yartchives/actions/workflows/deploy-pages.yml/runs?per_page=1";
const DEPLOY_NOTIFICATION_POLL_MS = 30 * 1000;
const DEPLOY_NOTIFICATION_SEEN_KEY = "yartchives-last-seen-deploy-v1";

function localDeploymentInfo() {
  const deployedAt = document.querySelector('meta[name="yartchives-deployed-at"]')?.content || "";
  const buildSha = document.querySelector('meta[name="yartchives-build"]')?.content || "";
  return { deployedAt, buildSha, age: formatSiteAge(deployedAt) };
}

function productionStatusTargets() {
  if (typeof document === "undefined") return els.siteMeta ? [els.siteMeta] : [];
  const targets = [...document.querySelectorAll("[data-production-status]")];
  if (els.siteMeta && !targets.includes(els.siteMeta)) targets.unshift(els.siteMeta);
  return targets;
}

function appendDeployAlertControl(target) {
  if (!target || typeof Notification === "undefined" || Notification.permission !== "default") return;
  const separator = document.createTextNode(" · ");
  const enable = document.createElement("button");
  enable.type = "button";
  enable.className = "text-btn";
  enable.textContent = "Enable deploy alerts";
  enable.addEventListener("click", async () => {
    const permission = await Notification.requestPermission();
    if (permission === "granted") {
      try { localStorage.setItem(DEPLOY_NOTIFICATION_SEEN_KEY, BUILD_SHA); } catch (_) {}
      void checkDeploymentNotification();
    }
    renderProductionStatus();
  });
  target.append(separator, enable);
}

function renderProductionStatus(run = null) {
  const targets = productionStatusTargets();
  if (!targets.length) return;
  const { deployedAt, buildSha, age } = localDeploymentInfo();
  if (!age || !buildSha || buildSha.startsWith("__")) {
    for (const target of targets) target.textContent = "Production status unavailable.";
    return;
  }

  const shortSha = buildSha.slice(0, 7);
  const status = String(run?.status || "");
  const conclusion = String(run?.conclusion || "");
  const runSha = String(run?.head_sha || "");
  const newerRun = Boolean(runSha && runSha !== buildSha);

  let text;
  if (status === "queued" || status === "in_progress" || status === "waiting" || status === "pending") {
    text = newerRun
      ? `Deploying update… · current production ${shortSha}`
      : `Deploying… · current production ${shortSha}`;
  } else if (status === "completed" && conclusion && conclusion !== "success" && newerRun) {
    text = `Deployment blocked · production still ${shortSha}`;
  } else {
    text = `Ready to test · production ${shortSha} · deployed ${age}`;
  }
  const title = `Deployed ${formatEasternTimestamp(deployedAt)} · build ${buildSha}${run?.html_url ? ` · latest deploy: ${run.html_url}` : ""}`;
  for (const target of targets) {
    target.textContent = text;
    target.title = title;
    appendDeployAlertControl(target);
  }
}

function updateSiteMeta() {
  renderProductionStatus();
}

let productionStatusPromise = null;

async function refreshProductionStatus(fetchImpl = typeof fetch === "function" ? fetch : null) {
  if (!fetchImpl || !els.siteMeta) return null;
  if (productionStatusPromise) return productionStatusPromise;
  productionStatusPromise = (async () => {
    const response = await fetchImpl(DEPLOY_STATUS_URL, {
      cache: "no-cache",
      headers: { Accept: "application/vnd.github+json" },
    });
    if (!response.ok) return null;
    const payload = await response.json();
    const run = Array.isArray(payload?.workflow_runs) ? payload.workflow_runs[0] : null;
    renderProductionStatus(run);
    return run;
  })()
    .catch(() => null)
    .finally(() => {
      productionStatusPromise = null;
    });
  return productionStatusPromise;
}

let deploymentCheckPromise = null;

function liveBuildShaFromHtml(html) {
  const match = String(html || "").match(
    /<meta\s+name=["']yartchives-build["']\s+content=["']([^"']+)["']/i
  );
  return match?.[1] || "";
}

function showUpdateReady(locationObj = typeof location !== "undefined" ? location : null) {
  if (!locationObj) return;
  for (const target of productionStatusTargets()) {
    target.textContent = "";
    const label = document.createElement("span");
    label.textContent = "Update ready · ";
    const reload = document.createElement("button");
    reload.type = "button";
    reload.className = "text-btn";
    reload.textContent = "Reload";
    reload.addEventListener("click", () => locationObj.reload());
    target.append(label, reload);
  }
}

async function checkForNewDeployment({
  fetchImpl = typeof fetch === "function" ? fetch : null,
  locationObj = typeof location !== "undefined" ? location : null,
  now = Date.now,
} = {}) {
  if (!fetchImpl || !locationObj || !BUILD_SHA || BUILD_SHA.startsWith("__")) return false;
  if (deploymentCheckPromise) return deploymentCheckPromise;

  deploymentCheckPromise = (async () => {
    const nonce = Number(typeof now === "function" ? now() : Date.now());
    const response = await fetchImpl(`./?build-check=${encodeURIComponent(BUILD_SHA)}-${nonce}`, {
      cache: "no-cache",
    });
    if (!response.ok) return false;
    const liveSha = liveBuildShaFromHtml(await response.text());
    if (!liveSha || liveSha === BUILD_SHA) return false;
    showUpdateReady(locationObj);
    return true;
  })()
    .catch(() => false)
    .finally(() => {
      deploymentCheckPromise = null;
    });

  return deploymentCheckPromise;
}

let deploymentNotificationPromise = null;

async function checkDeploymentNotification({
  fetchImpl = typeof fetch === "function" ? fetch : null,
  notificationImpl = typeof Notification !== "undefined" ? Notification : null,
  storage = typeof localStorage !== "undefined" ? localStorage : null,
  locationObj = typeof location !== "undefined" ? location : null,
  now = Date.now,
} = {}) {
  if (!fetchImpl || !notificationImpl || notificationImpl.permission !== "granted") return null;
  if (deploymentNotificationPromise) return deploymentNotificationPromise;

  deploymentNotificationPromise = (async () => {
    const nonce = Number(typeof now === "function" ? now() : Date.now());
    const response = await fetchImpl(`./deployment-status.json?watch=${nonce}`, { cache: "no-cache" });
    if (!response.ok) return null;
    const payload = await response.json();
    const liveSha = String(payload?.build_sha || "");
    if (!liveSha) return null;
    let seenSha = BUILD_SHA;
    try { seenSha = storage?.getItem(DEPLOY_NOTIFICATION_SEEN_KEY) || BUILD_SHA; } catch (_) {}
    if (liveSha === seenSha) return payload;
    try { storage?.setItem(DEPLOY_NOTIFICATION_SEEN_KEY, liveSha); } catch (_) {}
    if (liveSha !== BUILD_SHA) showUpdateReady(locationObj);
    if (payload?.interactive === true) {
      const options = {
        body: "Your interactive change is deployed and ready to test.",
        tag: `yartchives-deploy-${liveSha}`,
        requireInteraction: true,
        data: { url: "./" },
      };
      let shown = false;
      try {
        if (typeof navigator !== "undefined" && navigator.serviceWorker) {
          const registration = await navigator.serviceWorker.ready;
          await registration.showNotification("Yartchives update is live", options);
          shown = true;
        }
      } catch (_) {}
      if (!shown) new notificationImpl("Yartchives update is live", options);
    }
    return payload;
  })().catch(() => null).finally(() => { deploymentNotificationPromise = null; });
  return deploymentNotificationPromise;
}

async function registerDeployNotificationWorker() {
  if (typeof navigator === "undefined" || !navigator.serviceWorker) return null;
  try {
    return await navigator.serviceWorker.register("./service-worker.js", { scope: "./" });
  } catch (_) {
    return null;
  }
}

function setUpDeploymentFreshnessChecks() {
  if (typeof window !== "undefined") {
    window.addEventListener("focus", () => {
      void checkForNewDeployment();
      void refreshProductionStatus();
      void checkDeploymentNotification();
    });
    window.setInterval(() => {
      void checkForNewDeployment();
      void refreshProductionStatus();
    }, 5 * 60 * 1000);
    window.setInterval(() => {
      void checkDeploymentNotification();
    }, DEPLOY_NOTIFICATION_POLL_MS);
  }
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        void checkForNewDeployment();
        void refreshProductionStatus();
      }
    });
  }
}

function setUpEvents() {
  let timer;
  els.searchInput.addEventListener("input", e => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.search = e.target.value;
      visibleLimit = PAGE_SIZE;
      persist();
      applyFilters();
    }, 120);
  });
  els.locationInput.addEventListener("input", e => {
    state.location = e.target.value;
    visibleLimit = PAGE_SIZE;
    persist();
    syncControls();
    clearTimeout(timer);
    timer = setTimeout(() => applyFilters(), 180);
  });
  els.radiusInput.addEventListener("input", e => {
    state.radius = e.target.value;
    visibleLimit = PAGE_SIZE;
    persist();
    clearTimeout(timer);
    timer = setTimeout(() => applyFilters(), 120);
  });
  els.freshnessSelect.addEventListener("change", e => {
    state.freshness = e.target.value;
    visibleLimit = PAGE_SIZE;
    persist();
    applyFilters();
  });
  els.statusSelect.addEventListener("change", e => {
    state.status = e.target.value;
    visibleLimit = PAGE_SIZE;
    persist();
    applyFilters();
  });
  document.querySelectorAll(".quick-locations button").forEach(btn => {
    btn.addEventListener("click", () => {
      state.location = btn.dataset.location || "";
      visibleLimit = PAGE_SIZE;
      persist();
      syncControls();
      applyFilters();
    });
  });
  els.loadMoreBtn.addEventListener("click", () => {
    visibleLimit += PAGE_SIZE;
    renderJobs();
  });
  els.clearFiltersBtn.addEventListener("click", () => {
    state.profile = "all";
    state.search = "";
    state.location = "";
    state.radius = "50";
    state.freshness = "all";
    state.status = "all";
    visibleLimit = PAGE_SIZE;
    persist();
    syncControls();
    renderProfiles();
    applyFilters();
  });
  if (els.shareBtn) {
    els.shareBtn.addEventListener("click", async () => {
      const url = new URL(location.href);
      url.search = "";
      if (state.profile !== "all") url.searchParams.set("profile", state.profile);
      if (state.search) url.searchParams.set("q", state.search);
      if (state.location) url.searchParams.set("loc", state.location);
      if (currentZip() && state.radius !== "50") url.searchParams.set("miles", state.radius);
      if (state.freshness !== "all") url.searchParams.set("fresh", state.freshness);
      try {
        await navigator.clipboard.writeText(url.toString());
        const old = els.shareBtn.textContent;
        els.shareBtn.textContent = "Copied";
        setTimeout(() => els.shareBtn.textContent = old, 1200);
      } catch (_) {
        prompt("Copy this link:", url.toString());
      }
    });
  }
}

function isFeedReady() {
  return feedReady;
}

async function boot() {
  void registerDeployNotificationWorker();
  updateSiteMeta();
  void refreshProductionStatus();
  void checkDeploymentNotification();
  setUpDeploymentFreshnessChecks();
  loadSavedState();
  syncControls();
  renderProfiles();
  setUpEvents();
  try {
    const response = await fetch(FEED_DATA_URL, { cache: "no-cache" });
    if (!response.ok) throw new Error(`Feed request failed (${response.status})`);
    feed = await response.json();
    if (!Array.isArray(feed.jobs)) throw new Error("Feed JSON is malformed");
    feedReady = true;
    renderHealth();
    updateFeedMeta();
    applyFilters();
  } catch (error) {
    feedReady = false;
    els.errorBox.classList.remove("hidden");
    els.errorBox.textContent = `Yartchives couldn't load the listings feed: ${error.message}`;
    els.feedMeta.textContent = "Feed unavailable.";
  }
}

boot();
