(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesApplyNextLocationProfileUI = api;
    if (typeof document !== "undefined") api.init();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const REMOTE_OPTIONS = [
    ["preferred", "Prefer remote"],
    ["acceptable", "Remote is acceptable"],
    ["not_preferred", "Prefer in-person / hybrid"],
  ];
  const RELOCATION_OPTIONS = [
    ["not_open", "Not open to relocating"],
    ["open", "Open to relocating for a worthwhile role"],
    ["preferred", "Prefer relocating for the right role"],
  ];
  const LOCATION_MODE_OPTIONS = [
    ["normal", "Normal location ranking"],
    ["custom", "Custom ZIP scores"],
  ];

  function normalizedRemotePreference(profile) {
    const explicit = String(profile?.remotePreference || "").trim().toLowerCase();
    if (REMOTE_OPTIONS.some(([value]) => value === explicit)) return explicit;
    return profile?.remoteRelevant === false ? "not_preferred" : "acceptable";
  }

  function normalizedRelocationPreference(profile) {
    const explicit = String(profile?.relocationPreference || "").trim().toLowerCase();
    if (RELOCATION_OPTIONS.some(([value]) => value === explicit)) return explicit;
    return profile?.relocationAllowed === false ? "not_open" : "open";
  }

  function normalizedLocationMode(profile) {
    const explicit = String(profile?.locationMode || "").trim().toLowerCase();
    if (LOCATION_MODE_OPTIONS.some(([value]) => value === explicit)) return explicit;
    return Array.isArray(profile?.locationAnchors) && profile.locationAnchors.length ? "custom" : "normal";
  }

  function clampLocationScore(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, Math.min(15, parsed)) : null;
  }

  function scoreList(profile) {
    const byZip = new Map((profile?.locationAnchors || [])
      .map(anchor => [String(anchor?.zip || anchor?.baseZip || "").trim(), clampLocationScore(anchor?.locationScore ?? anchor?.score)])
      .filter(([zip, score]) => /^\d{5}$/.test(zip) && score !== null));
    return (profile?.baseZips || []).map(zip => byZip.has(String(zip)) ? byZip.get(String(zip)) : "").join(", ");
  }

  function customAnchors(profile, rawScores) {
    const zips = (profile?.baseZips || []).map(value => String(value || "").trim()).filter(value => /^\d{5}$/.test(value));
    if (!zips.length) throw new Error("Custom ZIP scores require at least one Base ZIP.");
    const labels = Array.isArray(profile?.baseLabels) ? profile.baseLabels : [];
    const scores = String(rawScores || "").split(/[\n,;]+/).map(value => value.trim()).filter(Boolean);
    if (scores.length !== zips.length) {
      throw new Error(`Enter exactly one custom location score for each Base ZIP (${zips.length} total).`);
    }
    return zips.map((zip, index) => {
      const parsed = Number(scores[index]);
      if (!Number.isFinite(parsed) || parsed < 0 || parsed > 15) {
        throw new Error("Custom location scores must be numbers from 0 to 15.");
      }
      return {
        zip,
        label: String(labels[index] || "").trim() || zip,
        locationScore: parsed,
      };
    });
  }

  function applyLocationPreferences(profile, values = {}) {
    const remotePreference = REMOTE_OPTIONS.some(([value]) => value === values.remotePreference)
      ? values.remotePreference
      : normalizedRemotePreference(profile);
    const relocationPreference = RELOCATION_OPTIONS.some(([value]) => value === values.relocationPreference)
      ? values.relocationPreference
      : normalizedRelocationPreference(profile);
    const locationMode = LOCATION_MODE_OPTIONS.some(([value]) => value === values.locationMode)
      ? values.locationMode
      : normalizedLocationMode(profile);
    const locationAnchors = locationMode === "custom"
      ? customAnchors(profile, values.anchorScores ?? scoreList(profile))
      : [];
    return {
      ...profile,
      remotePreference,
      relocationPreference,
      locationMode,
      locationAnchors,
      remoteRelevant: remotePreference !== "not_preferred",
      relocationAllowed: relocationPreference !== "not_open",
    };
  }

  function makeSelect(name, options, selected) {
    const select = document.createElement("select");
    select.name = name;
    for (const [value, label] of options) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = value === selected;
      select.append(option);
    }
    return select;
  }

  function makeField(labelText, control) {
    const label = document.createElement("label");
    label.className = "apply-next-profile-field";
    const span = document.createElement("span");
    span.textContent = labelText;
    label.append(span, control);
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

  function enhanceForm(form) {
    if (!form || form.dataset.locationPreferencesEnhanced === "true") return;
    const locationSection = [...form.querySelectorAll(".apply-next-profile-section")]
      .find(section => /location preferences/i.test(section.querySelector("h3")?.textContent || ""));
    if (!locationSection) return;

    const profile = loadSavedProfile() || {};
    const baseZip = form.querySelector('[name="baseZips"]');
    if (baseZip) {
      const field = baseZip.closest(".apply-next-profile-field");
      const label = field?.querySelector("span");
      if (label) label.textContent = "Base ZIPs, in priority order";
      baseZip.placeholder = "Primary ZIP, secondary ZIP, ...";
    }

    const oldChecks = locationSection.querySelector(".apply-next-profile-checks");
    if (oldChecks) oldChecks.hidden = true;

    const grid = document.createElement("div");
    grid.className = "apply-next-profile-grid apply-next-location-preference-grid";
    const remote = makeSelect("remotePreference", REMOTE_OPTIONS, normalizedRemotePreference(profile));
    const relocation = makeSelect("relocationPreference", RELOCATION_OPTIONS, normalizedRelocationPreference(profile));
    const locationMode = makeSelect("locationMode", LOCATION_MODE_OPTIONS, normalizedLocationMode(profile));
    const anchorScores = document.createElement("input");
    anchorScores.name = "anchorScores";
    anchorScores.type = "text";
    anchorScores.autocomplete = "off";
    anchorScores.placeholder = "15, 10, 6";
    anchorScores.value = scoreList(profile);
    const scoreField = makeField("ZIP scores out of 15, in the same order", anchorScores);

    function syncMode() {
      const custom = locationMode.value === "custom";
      scoreField.hidden = !custom;
      anchorScores.disabled = !custom;
    }
    locationMode.addEventListener("change", syncMode);
    syncMode();

    grid.append(
      makeField("Location ranking", locationMode),
      scoreField,
      makeField("Remote work", remote),
      makeField("Relocation", relocation)
    );

    const note = document.createElement("p");
    note.className = "muted apply-next-location-preference-note";
    note.textContent = "Normal uses Yartchives' default anchor ordering. Custom assigns each Base ZIP its own 0–15 location score; enter one score per ZIP in the same order. Jobs within multiple anchors use the highest applicable score.";
    locationSection.append(grid, note);
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
      const values = {
        remotePreference: form?.querySelector('[name="remotePreference"]')?.value,
        relocationPreference: form?.querySelector('[name="relocationPreference"]')?.value,
        locationMode: form?.querySelector('[name="locationMode"]')?.value,
        anchorScores: form?.querySelector('[name="anchorScores"]')?.value,
      };
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
    REMOTE_OPTIONS,
    RELOCATION_OPTIONS,
    LOCATION_MODE_OPTIONS,
    normalizedRemotePreference,
    normalizedRelocationPreference,
    normalizedLocationMode,
    clampLocationScore,
    scoreList,
    customAnchors,
    applyLocationPreferences,
    init,
  };
});