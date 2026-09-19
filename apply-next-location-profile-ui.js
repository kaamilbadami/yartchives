(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesApplyNextLocationProfileUI = api;
    if (typeof document !== "undefined") api.init();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const LOCATION_PREFERENCES_VERSION = 2;
  const LOCATION_MODE_OPTIONS = [
    ["normal", "Default scoring (recommended)"],
    ["custom", "Custom scoring (advanced)"],
  ];
  const RELOCATION_REGIONS = Object.freeze([
    { id: "new_england", label: "New England", states: "CT · ME · MA · NH · RI · VT" },
    { id: "mid_atlantic", label: "Mid-Atlantic", states: "DE · DC · MD · NJ · NY · PA · VA · WV" },
    { id: "southeast", label: "Southeast", states: "AL · AR · FL · GA · KY · LA · MS · NC · SC · TN" },
    { id: "midwest", label: "Midwest", states: "IL · IN · IA · KS · MI · MN · MO · NE · ND · OH · SD · WI" },
    { id: "south_central", label: "South Central", states: "OK · TX" },
    { id: "mountain_west", label: "Mountain West", states: "AZ · CO · ID · MT · NV · NM · UT · WY" },
    { id: "west_coast", label: "West Coast / Pacific", states: "AK · CA · HI · OR · WA" },
  ]);

  function clampScore(value, fallback) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(0, Math.min(20, Math.round(parsed)));
  }

  function clampMiles(value, fallback = 50) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(5, Math.min(150, Math.round(parsed))) : fallback;
  }

  function normalizeZip(value) {
    const text = String(value || "").trim();
    return /^\d{5}$/.test(text) ? text : null;
  }

  function normalizedLocationMode(profile) {
    const explicit = String(profile?.locationMode || "").trim().toLowerCase();
    if (explicit === "normal" || explicit === "default") return "normal";
    if (explicit === "custom") return "custom";
    return Array.isArray(profile?.locationAnchors) && profile.locationAnchors.length ? "custom" : "normal";
  }

  function legacyAnchorScore(profile, value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return null;
    if (Number(profile?.locationPreferencesVersion || 0) >= LOCATION_PREFERENCES_VERSION) return clampScore(parsed, 20);
    return Math.round((Math.max(0, Math.min(15, parsed)) / 15) * 20);
  }

  function anchorsFromProfile(profile) {
    const commonMiles = clampMiles(profile?.nearbyMiles, 50);
    const explicit = Array.isArray(profile?.locationAnchors) ? profile.locationAnchors : [];
    if (explicit.length) {
      return explicit.map((anchor, index) => {
        const zip = normalizeZip(anchor?.zip || anchor?.baseZip);
        if (!zip) return null;
        return {
          zip,
          label: String(anchor?.label || "").trim() || (index === 0 ? "Primary base" : `Base ${index + 1}`),
          commuteMiles: clampMiles(anchor?.commuteMiles ?? anchor?.nearbyMiles, commonMiles),
          locationScore: legacyAnchorScore(profile, anchor?.locationScore ?? anchor?.score) ?? (index === 0 ? 20 : 16),
        };
      }).filter(Boolean);
    }
    return (profile?.baseZips || []).map((value, index) => {
      const zip = normalizeZip(value);
      if (!zip) return null;
      return {
        zip,
        label: String(profile?.baseLabels?.[index] || "").trim() || (index === 0 ? "Primary base" : `Base ${index + 1}`),
        commuteMiles: commonMiles,
        locationScore: index === 0 ? 20 : 16,
      };
    }).filter(Boolean);
  }

  function defaultRemoteScore(profile) {
    if (Number.isFinite(Number(profile?.remoteScore))) return clampScore(profile.remoteScore, 20);
    const legacy = String(profile?.remotePreference || "").toLowerCase();
    if (legacy === "not_preferred") return 6;
    if (legacy === "acceptable") return 16;
    return 20;
  }

  function defaultRelocationScore(profile) {
    if (Number.isFinite(Number(profile?.relocationScore))) return clampScore(profile.relocationScore, 8);
    const legacy = String(profile?.relocationPreference || "").toLowerCase();
    if (legacy === "preferred") return 11;
    if (legacy === "not_open" || profile?.relocationAllowed === false) return 0;
    return 8;
  }

  function applyLocationPreferences(profile, values = {}) {
    const mode = values.locationMode === "custom" ? "custom" : "normal";
    const base = profile && typeof profile === "object" ? profile : {};

    if (mode === "normal") {
      const homeZip = normalizeZip(values.homeZip || base?.baseZips?.[0]);
      const commuteMiles = clampMiles(values.homeCommuteMiles ?? base.nearbyMiles, 50);
      return {
        ...base,
        locationPreferencesVersion: LOCATION_PREFERENCES_VERSION,
        locationMode: "normal",
        baseZips: homeZip ? [homeZip] : [],
        baseLabels: homeZip ? ["Home"] : [],
        nearbyMiles: commuteMiles,
        preferredStates: [],
        locationAnchors: [],
        remoteScore: 20,
        relocationScore: 8,
        relocationRegionScores: {},
        excludeRelocation: false,
        remoteRelevant: true,
        relocationAllowed: true,
      };
    }

    const rawAnchors = Array.isArray(values.anchors) ? values.anchors : anchorsFromProfile(base);
    const anchors = rawAnchors.map((anchor, index) => {
      const zip = normalizeZip(anchor?.zip);
      if (!zip) throw new Error(`Base ${index + 1} needs a valid 5-digit ZIP.`);
      return {
        zip,
        label: String(anchor?.label || "").trim() || (index === 0 ? "Primary base" : `Base ${index + 1}`),
        commuteMiles: clampMiles(anchor?.commuteMiles, 50),
        locationScore: clampScore(anchor?.locationScore, index === 0 ? 20 : 16),
      };
    });
    if (!anchors.length) throw new Error("Custom location needs at least one commute base.");

    const relocationRegionScores = {};
    const rawRegions = values.regionScores && typeof values.regionScores === "object" ? values.regionScores : {};
    for (const region of RELOCATION_REGIONS) {
      if (rawRegions[region.id] === "" || rawRegions[region.id] === null || rawRegions[region.id] === undefined) continue;
      relocationRegionScores[region.id] = clampScore(rawRegions[region.id], 8);
    }

    const remoteScore = clampScore(values.remoteScore, defaultRemoteScore(base));
    const relocationScore = clampScore(values.relocationScore, defaultRelocationScore(base));
    const excludeRelocation = Boolean(values.excludeRelocation);
    return {
      ...base,
      locationPreferencesVersion: LOCATION_PREFERENCES_VERSION,
      locationMode: "custom",
      baseZips: anchors.map(anchor => anchor.zip),
      baseLabels: anchors.map(anchor => anchor.label),
      nearbyMiles: anchors[0].commuteMiles,
      preferredStates: [],
      locationAnchors: anchors,
      remoteScore,
      relocationScore,
      relocationRegionScores,
      excludeRelocation,
      remoteRelevant: remoteScore > 0,
      relocationAllowed: !excludeRelocation,
    };
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function numberInput(name, value, min, max) {
    const input = document.createElement("input");
    input.type = "number";
    input.name = name;
    input.value = value;
    input.min = String(min);
    input.max = String(max);
    input.step = "1";
    input.autocomplete = "off";
    return input;
  }

  function makeField(labelText, control, hint) {
    const label = element("label", "apply-next-profile-field");
    label.append(element("span", "", labelText), control);
    if (hint) label.append(element("small", "apply-next-location-field-hint", hint));
    return label;
  }

  function loadSavedProfile() {
    try {
      const ui = window.YartchivesApplyNextUI;
      return ui?.loadProfile?.(localStorage) || null;
    } catch (_) {
      return null;
    }
  }

  function hideLegacyField(input) {
    const field = input?.closest(".apply-next-profile-field");
    if (field) field.hidden = true;
  }

  function makeModeSelect(selected) {
    const select = document.createElement("select");
    select.name = "locationScoringMode";
    select.setAttribute("aria-label", "Location scoring");
    for (const [value, label] of LOCATION_MODE_OPTIONS) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = value === selected;
      select.append(option);
    }
    return select;
  }

  function makeAnchorRow(anchor, index) {
    const row = element("div", "apply-next-location-anchor-row");
    row.dataset.anchorIndex = String(index);

    const zip = document.createElement("input");
    zip.type = "text";
    zip.inputMode = "numeric";
    zip.maxLength = 5;
    zip.placeholder = "ZIP";
    zip.value = anchor?.zip || "";
    zip.dataset.anchorField = "zip";

    const miles = numberInput("", anchor?.commuteMiles ?? 50, 5, 150);
    miles.dataset.anchorField = "commuteMiles";

    const score = numberInput("", anchor?.locationScore ?? (index === 0 ? 20 : 16), 0, 20);
    score.dataset.anchorField = "locationScore";

    const remove = element("button", "text-btn apply-next-location-remove", "Remove");
    remove.type = "button";
    remove.dataset.removeAnchor = "true";

    row.append(
      makeField(index === 0 ? "Primary ZIP" : `Base ${index + 1} ZIP`, zip),
      makeField("Daily commute radius (miles)", miles, "Only count places you would regularly travel to without moving. If you would move for a job, use relocation instead of increasing this radius."),
      makeField("Score /20", score),
      remove
    );
    return row;
  }

  function readAnchorRows(container) {
    return [...container.querySelectorAll(".apply-next-location-anchor-row")].map((row, index) => ({
      zip: row.querySelector('[data-anchor-field="zip"]')?.value,
      label: index === 0 ? "Primary base" : `Base ${index + 1}`,
      commuteMiles: row.querySelector('[data-anchor-field="commuteMiles"]')?.value,
      locationScore: row.querySelector('[data-anchor-field="locationScore"]')?.value,
    }));
  }

  function enhanceForm(form) {
    if (!form || form.dataset.locationPreferencesEnhanced === "true") return;
    const locationSection = [...form.querySelectorAll(".apply-next-profile-section")]
      .find(section => /location preferences/i.test(section.querySelector("h3")?.textContent || ""));
    if (!locationSection) return;

    const profile = loadSavedProfile() || {};
    const initialMode = normalizedLocationMode(profile);
    const oldBase = form.querySelector('[name="baseZips"]');
    const oldStates = form.querySelector('[name="preferredStates"]');
    const oldMiles = form.querySelector('[name="nearbyMiles"]');
    hideLegacyField(oldStates);
    const oldChecks = locationSection.querySelector(".apply-next-profile-checks");
    if (oldChecks) oldChecks.hidden = true;

    if (oldBase) {
      const label = oldBase.closest(".apply-next-profile-field")?.querySelector("span");
      if (label) label.textContent = "Home ZIP";
      oldBase.placeholder = "e.g. 06897";
      oldBase.value = profile?.baseZips?.[0] || oldBase.value || "";
    }
    if (oldMiles) {
      const label = oldMiles.closest(".apply-next-profile-field")?.querySelector("span");
      if (label) label.textContent = "Daily commute radius (miles)";
      oldMiles.max = "150";
      const field = oldMiles.closest(".apply-next-profile-field");
      if (field && !field.querySelector(".apply-next-location-field-hint")) {
        field.append(element("small", "apply-next-location-field-hint", "Only count places you would regularly travel to without moving. If you would move for a job, select “Open to relocating for a worthwhile role” below—don’t increase the commute radius."));
      }
    }

    const intro = element("div", "apply-next-location-intro");
    intro.append(
      element("p", "apply-next-profile-subhead", "Location preferences"),
      element("p", "muted", "Your commute radius is only for jobs you can reach without moving. Jobs farther away are handled as relocation.")
    );
    const modeSelect = makeModeSelect(initialMode);
    intro.append(makeField("Location scoring", modeSelect));

    const defaultPanel = element("div", "apply-next-location-panel");
    defaultPanel.dataset.locationPanel = "normal";
    defaultPanel.append(
      element("div", "apply-next-location-summary-chip", "Default scoring"),
      element("p", "muted", "Remote = 20. Jobs inside your commute range taper from 20 to 16 as the commute gets longer. Jobs that clearly require moving = 8. Unverified location = 10.")
    );

    const customPanel = element("div", "apply-next-location-panel");
    customPanel.dataset.locationPanel = "custom";
    const customHeading = element("div", "apply-next-location-panel-heading");
    customHeading.append(
      element("div", "apply-next-location-summary-chip", "Custom scoring"),
      element("p", "muted", "Your numbers are used directly. If a job fits more than one commute base, the highest matching base score wins.")
    );
    customPanel.append(customHeading);

    const anchorWrap = element("div", "apply-next-location-anchor-list");
    const initialAnchors = anchorsFromProfile(profile);
    (initialAnchors.length ? initialAnchors : [{ zip: profile?.baseZips?.[0] || "", commuteMiles: profile?.nearbyMiles || 50, locationScore: 20 }])
      .forEach((anchor, index) => anchorWrap.append(makeAnchorRow(anchor, index)));
    const addBase = element("button", "secondary-btn apply-next-location-add", "+ Add another commute base");
    addBase.type = "button";
    customPanel.append(element("p", "apply-next-profile-subhead", "Commute bases"), anchorWrap, addBase);

    const scoreGrid = element("div", "apply-next-profile-grid apply-next-location-score-grid");
    const remoteScore = numberInput("remoteScore", defaultRemoteScore(profile), 0, 20);
    const relocationScore = numberInput("relocationScore", defaultRelocationScore(profile), 0, 20);
    scoreGrid.append(
      makeField("Remote score /20", remoteScore, "Set this to exactly how valuable remote work is to you."),
      makeField("Default relocation score /20", relocationScore, "Used when a role is outside all commute bases and you have no regional override.")
    );
    customPanel.append(scoreGrid);

    const hardLimit = element("label", "apply-next-location-hard-limit");
    const excludeRelocation = document.createElement("input");
    excludeRelocation.type = "checkbox";
    excludeRelocation.name = "excludeRelocation";
    excludeRelocation.checked = profile?.excludeRelocation === true;
    hardLimit.append(excludeRelocation, element("span", "", "Hide roles that require moving outside my commute bases"));
    customPanel.append(hardLimit);

    const details = document.createElement("details");
    details.className = "apply-next-location-regions";
    const summary = document.createElement("summary");
    summary.textContent = "Fine-tune relocation by area (optional)";
    details.append(summary);
    details.append(element("p", "muted", "Leave an area blank to use your default relocation score. The included states are shown so you never have to remember region definitions."));
    const regionGrid = element("div", "apply-next-location-region-grid");
    const existingRegions = profile?.relocationRegionScores || {};
    for (const region of RELOCATION_REGIONS) {
      const card = element("label", "apply-next-location-region-card");
      const title = element("span", "apply-next-location-region-title", region.label);
      const states = element("small", "apply-next-location-region-states", region.states);
      const input = numberInput(`regionScore_${region.id}`, existingRegions[region.id] ?? "", 0, 20);
      input.placeholder = "Default";
      input.dataset.regionId = region.id;
      card.append(title, states, input);
      regionGrid.append(card);
    }
    details.append(regionGrid);
    customPanel.append(details);

    locationSection.insertBefore(intro, locationSection.firstChild?.nextSibling || null);
    locationSection.append(defaultPanel, customPanel);

    let mode = initialMode;
    function syncMode(nextMode) {
      mode = nextMode === "custom" ? "custom" : "normal";
      form.dataset.locationMode = mode;
      defaultPanel.hidden = mode !== "normal";
      customPanel.hidden = mode !== "custom";
      if (oldBase?.closest(".apply-next-profile-field")) oldBase.closest(".apply-next-profile-field").hidden = mode !== "normal";
      if (oldMiles?.closest(".apply-next-profile-field")) oldMiles.closest(".apply-next-profile-field").hidden = mode !== "normal";
      modeSelect.value = mode;
    }
    modeSelect.addEventListener("change", () => syncMode(modeSelect.value));
    syncMode(initialMode);

    addBase.addEventListener("click", () => {
      const index = anchorWrap.querySelectorAll(".apply-next-location-anchor-row").length;
      anchorWrap.append(makeAnchorRow({ commuteMiles: 50, locationScore: 16 }, index));
    });
    anchorWrap.addEventListener("click", event => {
      const button = event.target.closest("[data-remove-anchor]");
      if (!button) return;
      const rows = anchorWrap.querySelectorAll(".apply-next-location-anchor-row");
      if (rows.length <= 1) return;
      button.closest(".apply-next-location-anchor-row")?.remove();
    });

    form.__readLocationPreferences = function () {
      const regionScores = {};
      for (const input of regionGrid.querySelectorAll("[data-region-id]")) {
        if (input.value !== "") regionScores[input.dataset.regionId] = input.value;
      }
      return {
        locationMode: mode,
        homeZip: oldBase?.value,
        homeCommuteMiles: oldMiles?.value,
        anchors: readAnchorRows(anchorWrap),
        remoteScore: remoteScore.value,
        relocationScore: relocationScore.value,
        regionScores,
        excludeRelocation: excludeRelocation.checked,
      };
    };

    form.dataset.locationPreferencesEnhanced = "true";
  }

  function enhanceCurrentForm() {
    enhanceForm(document.querySelector(".apply-next-profile-wizard"));
  }

  function wrapSaveProfile() {
    const ui = window.YartchivesApplyNextUI;
    if (!ui || typeof ui.saveProfile !== "function" || ui.saveProfile.__locationPreferencesWrapped) return false;
    const prior = ui.saveProfile;
    const wrapped = function (storage, profile) {
      const form = document.querySelector(".apply-next-profile-wizard");
      const values = typeof form?.__readLocationPreferences === "function"
        ? form.__readLocationPreferences()
        : { locationMode: normalizedLocationMode(profile) };
      return prior.call(ui, storage, applyLocationPreferences(profile, values));
    };
    wrapped.__locationPreferencesWrapped = true;
    wrapped.__priorSaveProfile = prior;
    ui.saveProfile = wrapped;
    return true;
  }

  function init() {
    const start = () => {
      wrapSaveProfile();
      enhanceCurrentForm();
      const panel = document.querySelector("#applyNextPanel");
      if (!panel) return;
      const observer = new MutationObserver(() => {
        wrapSaveProfile();
        enhanceCurrentForm();
      });
      observer.observe(panel, { childList: true, subtree: true });
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
    else start();
  }

  return {
    LOCATION_PREFERENCES_VERSION,
    LOCATION_MODE_OPTIONS,
    RELOCATION_REGIONS,
    clampScore,
    normalizedLocationMode,
    anchorsFromProfile,
    defaultRemoteScore,
    defaultRelocationScore,
    applyLocationPreferences,
    init,
  };
});
