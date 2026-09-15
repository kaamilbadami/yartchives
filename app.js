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

const STORAGE_KEY = "yartchives-state-v1";
const PAGE_SIZE = 80;
let feed = { jobs: [], sources: {}, generated_at: null };
let filtered = [];
let visibleLimit = PAGE_SIZE;

const state = {
  profile: "all",
  search: "",
  location: "",
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
  feedMeta: document.querySelector("#feedMeta"),
  sourceHealth: document.querySelector("#sourceHealth"),
  errorBox: document.querySelector("#errorBox"),
  shareBtn: document.querySelector("#shareBtn"),
  clearFiltersBtn: document.querySelector("#clearFiltersBtn"),
};

function loadSavedState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    for (const key of ["profile", "search", "location", "freshness", "status"]) {
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
  if (params.has("fresh")) state.freshness = params.get("fresh") || "7";
}

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    profile: state.profile,
    search: state.search,
    location: state.location,
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
  const raw = job.posted_at || job.first_seen;
  if (!raw) return null;
  const ms = Date.now() - new Date(raw).getTime();
  return Math.max(0, ms / 86400000);
}

function matchesLocation(job) {
  const query = state.location.trim().toLowerCase();
  if (!query) return true;
  const tokens = query.split(/[,;/]+/).map(x => x.trim()).filter(Boolean);
  const stateTokens = (job.states || []).map(x => x.toLowerCase());
  const loc = (job.location || "").toLowerCase();
  return tokens.some(token => stateTokens.includes(token) || loc.includes(token));
}

function applyFilters() {
  const q = state.search.trim().toLowerCase();
  const maxDays = state.freshness === "all" ? Infinity : Number(state.freshness);

  filtered = feed.jobs.filter(job => {
    if (state.hidden.has(job.id)) return false;
    if (state.profile !== "all" && !(job.profiles || []).includes(state.profile)) return false;
    if (q && !searchable(job).includes(q)) return false;
    if (!matchesLocation(job)) return false;
    const ageDays = jobAgeDays(job);
    if (ageDays !== null && ageDays > maxDays) return false;
    if (state.status === "saved" && !state.saved.has(job.id)) return false;
    if (state.status === "applied" && !state.applied.has(job.id)) return false;
    return true;
  });

  renderJobs();
  updateStats();
}

function relativeAge(job) {
  const raw = job.posted_at || job.first_seen;
  if (!raw) return "date unknown";
  const delta = Math.max(0, Date.now() - new Date(raw).getTime());
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
    empty.innerHTML = "<strong>No matches.</strong><br>Try a broader profile, location, or freshness window.";
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
    age.textContent = relativeAge(job);
    age.title = job.posted_at ? `Posted/added: ${new Date(job.posted_at).toLocaleString()}` : "Posting date unavailable";

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
      applyBtn.addEventListener("click", () => {
        state.applied.add(job.id);
        persist();
      });
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
  els.newCount.textContent = feed.jobs.filter(j => { const d = jobAgeDays(j); return d !== null && d <= 7; }).length.toLocaleString();
  els.savedCount.textContent = state.saved.size.toLocaleString();
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
    applyFilters();
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
