(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.YartchivesUtils = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
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
  const STATE_CODE_BY_NAME = Object.fromEntries(
    Object.entries(STATE_NAMES).map(([code, name]) => [name.toLowerCase(), code.toLowerCase()])
  );

  const MAX_PAINT_WAIT_MS = 50;

  function waitForBrowserPaint(options = {}) {
    return new Promise(resolve => {
      const raf = options.requestAnimationFrame
        || (typeof requestAnimationFrame === "function" ? requestAnimationFrame : null);
      const timer = options.setTimeout
        || (typeof setTimeout === "function" ? setTimeout : null);
      const maxWaitMs = Number.isFinite(Number(options.maxWaitMs))
        ? Math.max(0, Number(options.maxWaitMs))
        : MAX_PAINT_WAIT_MS;
      let settled = false;

      const finish = () => {
        if (settled) return;
        settled = true;
        resolve();
      };

      if (raf) raf(finish);
      if (timer) timer(finish, raf ? maxWaitMs : 0);
      if (!raf && !timer) finish();
    });
  }

  async function runWithPendingUi(options = {}) {
    const {
      control = null,
      busyTarget = null,
      pendingLabel,
      prepare,
      work,
      paint = waitForBrowserPaint,
    } = options;

    if (typeof work !== "function") {
      throw new TypeError("runWithPendingUi requires a work function");
    }

    const priorDisabled = control ? Boolean(control.disabled) : false;
    const priorLabel = control && "textContent" in control ? control.textContent : null;
    const priorBusy = busyTarget?.getAttribute ? busyTarget.getAttribute("aria-busy") : null;

    try {
      if (control) {
        control.disabled = true;
        if (pendingLabel !== undefined && "textContent" in control) control.textContent = pendingLabel;
      }
      if (busyTarget?.setAttribute) busyTarget.setAttribute("aria-busy", "true");
      if (typeof prepare === "function") prepare();

      await paint();
      return await work();
    } finally {
      if (control) {
        control.disabled = priorDisabled;
        if (priorLabel !== null && "textContent" in control) control.textContent = priorLabel;
      }
      if (busyTarget?.setAttribute) {
        if (priorBusy === null) busyTarget.removeAttribute?.("aria-busy");
        else busyTarget.setAttribute("aria-busy", priorBusy);
      }
    }
  }

  function normalizePlace(value) {
    return (value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function matchesTextLocation(job, queryValue) {
    const query = (queryValue || "").trim().toLowerCase();
    if (!query) return true;
    const tokens = query.split(/[,;/]+/).map(x => x.trim()).filter(Boolean);
    const stateTokens = (job.states || []).map(x => String(x).toLowerCase());
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

  function buildGeoIndex(csvText) {
    const lines = String(csvText || "").split(/\r?\n/).filter(Boolean);
    if (!lines.length) throw new Error("ZIP data is empty");
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
      const pop = col.population === undefined ? 0 : Number(row[col.population]);
      if (!/^\d{5}$/.test(zip) || !city || !st || !Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const point = { lat, lon, state: st, city, zip, precision: "zip" };
      zips.set(zip, point);

      const key = `${st}|${normalizePlace(city)}`;
      const weight = Number.isFinite(pop) && pop > 0 ? pop : 1;
      const acc = cityAcc.get(key) || { lat: 0, lon: 0, weight: 0, name: normalizePlace(city), state: st };
      acc.lat += lat * weight;
      acc.lon += lon * weight;
      acc.weight += weight;
      cityAcc.set(key, acc);
    }

    const cities = new Map();
    const citiesByState = new Map();
    for (const [key, acc] of cityAcc.entries()) {
      const point = {
        lat: acc.lat / acc.weight,
        lon: acc.lon / acc.weight,
        state: acc.state,
        city: acc.name,
        precision: "city",
      };
      cities.set(key, point);
      if (!citiesByState.has(acc.state)) citiesByState.set(acc.state, []);
      citiesByState.get(acc.state).push([acc.name, point]);
    }
    for (const list of citiesByState.values()) list.sort((a, b) => b[0].length - a[0].length);
    return { zips, cities, citiesByState };
  }

  function addCandidate(candidates, value) {
    const normalized = normalizePlace(value)
      .replace(/^\d+\s+locations?\s+/, "")
      .replace(/\b(?:united states|usa|us)\b/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (normalized) candidates.add(normalized);
  }

  function authoritativeLocationValues(job) {
    const inspection = job?._inspection || job?.inspection;
    const locations = inspection?.status === "inspected" ? inspection?.posting?.locations : null;
    if (locations?.status !== "authoritative" || !Array.isArray(locations.values)) return [];
    return locations.values.map(value => String(value || "").trim()).filter(Boolean);
  }

  function locationTextForJob(job) {
    const authoritative = authoritativeLocationValues(job);
    return authoritative.length ? authoritative.join(" ; ") : (job?.location || "");
  }

  function statesForLocation(raw, fallback = []) {
    const found = new Set();
    const text = String(raw || "");
    for (const [code, name] of Object.entries(STATE_NAMES)) {
      if (new RegExp(`(?:^|[\\s,(/-])${code}(?:$|[\\s,)/-])`, "i").test(text)) found.add(code);
      if (new RegExp(`\\b${name.replace(/ /g, "\\s+")}\\b`, "i").test(text)) found.add(code);
    }
    if (found.size) return [...found];
    return (fallback || []).filter(x => /^[A-Z]{2}$/.test(x) && x !== "US");
  }

  function coordinatesForJob(job, geo) {
    const raw = locationTextForJob(job);
    const zipMatches = raw.match(/\b\d{5}(?:-\d{4})?\b/g) || [];
    const zipPoints = zipMatches
      .map(value => geo.zips.get(value.slice(0, 5)))
      .filter(Boolean);
    if (zipPoints.length) return zipPoints;

    const states = statesForLocation(raw, job.states || []);
    if (!states.length) return null;

    const normalizedLocation = ` ${normalizePlace(raw)} `;
    const candidates = new Set();
    const commaParts = raw.split(",");
    if (commaParts.length > 1) addCandidate(candidates, commaParts[0]);
    for (const segment of raw.split(/[\/;|·]+/)) addCandidate(candidates, segment.split(",")[0]);

    const found = [];
    for (const st of states) {
      const full = STATE_NAMES[st] || "";
      const beforeState = full
        ? raw.match(new RegExp(`^(.+?)(?:,|[-\\s]+)(?:${st}|${full.replace(/ /g, "\\s+")})(?:\\b|-)`, "i"))
        : raw.match(new RegExp(`^(.+?)(?:,|[-\\s]+)${st}(?:\\b|-)`, "i"));
      if (beforeState) addCandidate(candidates, beforeState[1]);

      const afterState = raw.match(new RegExp(`(?:^|\\b)(?:US|USA)?[-\\s]*${st}[-\\s]+(.+?)(?:[-~,/]|$)`, "i"));
      if (afterState) addCandidate(candidates, afterState[1].replace(/-\d.*$/, ""));

      let stateFound = false;
      for (const candidate of candidates) {
        const direct = geo.cities.get(`${st}|${candidate}`);
        if (direct) {
          found.push(direct);
          stateFound = true;
        }
      }

      if (!stateFound) {
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
    return found.length ? found : null;
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

  const GEO_POINT_CACHE = new WeakMap();

  function geoResolutionSignature(job) {
    const states = Array.isArray(job?.states)
      ? job.states.map(value => String(value || "")).sort().join(",")
      : "";
    return `${locationTextForJob(job)}|${states}`;
  }

  function resolvedCoordinatesForJob(job, geo) {
    if (!job || typeof job !== "object" || !geo) return coordinatesForJob(job, geo);
    const signature = geoResolutionSignature(job);
    const cached = GEO_POINT_CACHE.get(job);
    if (cached && cached.geo === geo && cached.signature === signature) {
      return cached.points;
    }
    const points = coordinatesForJob(job, geo);
    GEO_POINT_CACHE.set(job, { geo, signature, points });
    return points;
  }

  function distanceForJob(job, origin, geo) {
    const points = resolvedCoordinatesForJob(job, geo);
    if (!points?.length) return null;
    let best = null;
    for (const point of points) {
      const miles = milesBetween(origin, point);
      if (!best || miles < best.miles) best = { miles, precision: point.precision || "city", point };
    }
    return best;
  }

  function sourceHealthDisplayName(value) {
    return String(value || "").replace(/^\s*🔥\s*/u, "").trim();
  }

  function groupSourceHealth(sources) {
    const groups = new Map();
    for (const [key, raw] of Object.entries(sources || {})) {
      const src = raw || {};
      const name = sourceHealthDisplayName(src.name || key) || key;
      const groupKey = name.toLocaleLowerCase();
      const current = groups.get(groupKey) || {
        name,
        count: 0,
        configuredCount: 0,
        successCount: 0,
        failureCount: 0,
        errors: [],
      };
      current.count += Number(src.count || 0);
      if (src.configured !== false) current.configuredCount += 1;
      if (src.ok) current.successCount += 1;
      else if (src.configured !== false) current.failureCount += 1;
      if (src.error && !current.errors.includes(String(src.error))) current.errors.push(String(src.error));
      groups.set(groupKey, current);
    }
    return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name));
  }

  function classifyEducationFromTitle(titleValue) {
    const raw = String(titleValue || "");
    const lower = raw.toLowerCase();
    const hasUndergrad = /\b(undergrad(?:uate)?|bachelor(?:'s|s)?|associate(?:'s|s)? degree|freshman|sophomore|junior)\b/.test(lower)
      || /(?:^|[\s,(\/])B\.?S\.?(?=$|[\s,)/])/i.test(raw)
      || /(?:^|[\s,(\/])B\.?A\.?(?=$|[\s,)/])/i.test(raw);
    const hasGraduate = /\b(ph\.?d\.?|doctoral|doctorate|master(?:'s|s)?(?: degree)?|graduate student|graduate internship|mba|juris doctor)\b/i.test(raw)
      || /(?:^|[\s,(\/])M\.?S\.?(?=$|[\s,)/])/i.test(raw)
      || /(?:^|[\s,(\/])M\.?A\.?(?=$|[\s,)/])/i.test(raw)
      || /(?:^|[\s,(\/])J\.?D\.?(?=$|[\s,)/])/i.test(raw);
    if (hasUndergrad) return "undergrad";
    if (hasGraduate) return "graduate-only";
    return "unspecified";
  }

  function classifyOpportunityTypeFromTitle(titleValue) {
    const text = String(titleValue || "").toLowerCase();
    if (/\b(co[- ]?op|cooperative education)\b/.test(text)) return "co-op";
    if (/\b(intern|internship|student trainee|pathways)\b/.test(text)) return "internship";
    if (/\b(fellow|fellowship)\b/.test(text)) return "fellowship";
    if (/\b(research assistant|research program|research experience)\b/.test(text)) return "research";
    if (/\bstudent\b/.test(text)) return "student";
    return "other";
  }

  function educationLevel(job) {
    return job.education_level || classifyEducationFromTitle(job.title);
  }

  function opportunityType(job) {
    return job.opportunity_type || classifyOpportunityTypeFromTitle(job.title);
  }

  function matchesEducation(job, filter) {
    const level = educationLevel(job);
    if (filter === "all") return true;
    if (filter === "graduate-only") return level === "graduate-only";
    if (filter === "explicit-undergrad") return level === "undergrad";
    return level !== "graduate-only";
  }

  function matchesOpportunityType(job, filter) {
    const type = opportunityType(job);
    if (filter === "all") return true;
    if (filter === "internships") return ["internship", "co-op", "student"].includes(type);
    return type === filter;
  }

  return {
    STATE_NAMES,
    MAX_PAINT_WAIT_MS,
    waitForBrowserPaint,
    runWithPendingUi,
    normalizePlace,
    matchesTextLocation,
    parseCsvLine,
    buildGeoIndex,
    authoritativeLocationValues,
    locationTextForJob,
    statesForLocation,
    coordinatesForJob,
    resolvedCoordinatesForJob,
    geoResolutionSignature,
    milesBetween,
    distanceForJob,
    sourceHealthDisplayName,
    groupSourceHealth,
    classifyEducationFromTitle,
    classifyOpportunityTypeFromTitle,
    educationLevel,
    opportunityType,
    matchesEducation,
    matchesOpportunityType,
  };
});
