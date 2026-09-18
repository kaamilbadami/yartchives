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
const GEO_DATA_URL = "https://raw.githubusercontent.com/ReadyAPIs-com/curated-us-zips/f9eb7daabdade9b2a9f3cbc80327a5c152fc82d3/data/us-zips.csv";

let feed = { jobs: [], sources: {}, generated_at: null };
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
  freshness: "7",
  status: "all",
  saved: new Set(),
  applied: new Set(),
  hidden: new Set(),
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
  resultsTitle: document.querySelector("#resultsTitle"),
  resultsNote: document.querySelector("#resultsNote"),
  feedMeta: document.querySelector("#feedMeta"),
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
  } catch (_) {}

  const params = new URLSearchParams(location.search);
  if (params.has("profile") && PROFILE_LABELS[params.get("profile")]) state.profile = params.get("profile");
  if (params.has("q")) state.search = params.get("q") || "";
  if (params.has("loc")) state.location = params.get("loc") || "";
  if (params.has("miles")) state.radius = params.get("miles") || "50";
  if (params.has("fresh")) state.freshness = params.get("fresh") || "7";
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
    const response = await fetch(GEO_DATA_URL, { cache: "force-cache", mode: "cors" });
    if (!response.ok) throw new Error(`ZIP data request failed (${response.status})`);
    const text = await response.text();
    const lines = text.split(/\r?\n/).filter(Boolean);
    const headers = parseCsvLine(lines[0]);
    const col = Object.fromEntries(headers.map((name, i) => [name, i]));
    for (const needed of ["zip_code", "city", "state", "latitude", "longitude"]) {
      if (col[needed] === undefined) throw new Error(`ZIP data is missing ${needed}`);
    }

    const zips = new Map();
    const cityAcc = new Map();
    for (let i = 1; i < lines.length; i++) {
      const row = parseCsvLine(lines[i]);
      const zip = (row[col.zip_code] || "").padStart(5, "0");
      const city = row[col.city] || "";
      const st = (row[col.state] || "").toUpperCase();
      const lat = Number(row[col.latitude]);
      const lon = Number(row[col.longitude]);
      if (!zip || !city || !st || !Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const point = { lat, lon, state: st, city };
      zips.set(zip, point);
      const key = `${st}|${normalizePlace(city)}`;
      const acc = cityAcc.get(key) || { lat: 0, lon: 0, count: 0, name: normalizePlace(city), state: st };
      acc.lat += lat;
      acc.lon += lon;
      acc.count += 1;
      cityAcc.set(key, acc);
    }

    const cities = new Map();
    const citiesByState = new Map();
    for (const [key, acc] of cityAcc.entries()) {
      const point = { lat: acc.lat / acc.count, lon: acc.lon / acc.count, state: acc.state, city: acc.name };
      cities.set(key, point);
      if (!citiesByState.has(acc.state)) citiesByState.set(acc.state, []);
      citiesByState.get(acc.state).push([acc.name, point]);
    }
    for (const list of citiesByState.values()) list.sort((a, b) => b[0].length - a[0].length);

    geoIndex = { zips, cities, citiesByState };
    geoError = null;
    return geoIndex;
  })().catch(error => {
    geoError = error;
    geoLoadingPromise = null;
    throw error;
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
    if (state.hidden.has(job.id)) return false;
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
    empty.innerHTML = "<strong>No matches.</strong><br>Try a broader profile, location, radius, or freshness window.";
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
      } else {
        applyBtn.addEventListener("click", () => {
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
  const entries = Object.entries(feed.sources || {}).sort((a, b) => (a[1].name || a[0]).localeCompare(b[1].name || b[0]));
  for (const [key, src] of entries) {
    const row = document.createElement("div");
    row.className = "source-row";
    const name = document.createElement("span");
    name.textContent = src.name || key;
    const status = document.createElement("span");
    if (src.configured === false) {
      status.className = "skip";
      status.textContent = "not configured";
    } else if (src.ok) {
      status.className = "ok";
      status.textContent = `${Number(src.count || 0).toLocaleString()} ✓`;
    } else {
      status.className = "fail";
      status.textContent = "failed";
      status.title = src.error || "Source failed during last refresh";
    }
    row.append(name, status);
    els.sourceHealth.appendChild(row);
  }
}

function updateFeedMeta() {
  if (!feed.generated_at) {
    els.feedMeta.textContent = "Feed has not been built yet.";
    return;
  }
  const when = new Date(feed.generated_at);
  els.feedMeta.textContent = `Updated ${when.toLocaleString()} · ${Object.values(feed.sources || {}).filter(s => s.ok && s.configured !== false).length} active sources`;
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
    state.freshness = "7";
    state.status = "all";
    visibleLimit = PAGE_SIZE;
    persist();
    syncControls();
    renderProfiles();
    applyFilters();
  });
  els.shareBtn.addEventListener("click", async () => {
    const url = new URL(location.href);
    url.search = "";
    if (state.profile !== "all") url.searchParams.set("profile", state.profile);
    if (state.search) url.searchParams.set("q", state.search);
    if (state.location) url.searchParams.set("loc", state.location);
    if (currentZip() && state.radius !== "50") url.searchParams.set("miles", state.radius);
    if (state.freshness !== "7") url.searchParams.set("fresh", state.freshness);
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

async function boot() {
  loadSavedState();
  syncControls();
  renderProfiles();
  setUpEvents();
  try {
    const response = await fetch(`data/listings.json?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Feed request failed (${response.status})`);
    feed = await response.json();
    if (!Array.isArray(feed.jobs)) throw new Error("Feed JSON is malformed");
    renderHealth();
    updateFeedMeta();
    applyFilters();
  } catch (error) {
    els.errorBox.classList.remove("hidden");
    els.errorBox.textContent = `Yartchives couldn't load the listings feed: ${error.message}`;
    els.feedMeta.textContent = "Feed unavailable.";
  }
}

boot();
