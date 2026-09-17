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

  function applyLocationPreferences(profile, values = {}) {
    const remotePreference = REMOTE_OPTIONS.some(([value]) => value === values.remotePreference)
      ? values.remotePreference
      : normalizedRemotePreference(profile);
    const relocationPreference = RELOCATION_OPTIONS.some(([value]) => value === values.relocationPreference)
      ? values.relocationPreference
      : normalizedRelocationPreference(profile);
    return {
      ...profile,
      remotePreference,
      relocationPreference,
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
    grid.append(
      makeField("Remote work", remote),
      makeField("Relocation", relocation)
    );

    const note = document.createElement("p");
    note.className = "muted apply-next-location-preference-note";
    note.textContent = "Base ZIP order matters: the first is your primary commute base, the second is your next choice. Jobs outside every commute base are excluded when relocation is set to Not open.";
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
    normalizedRemotePreference,
    normalizedRelocationPreference,
    applyLocationPreferences,
    init,
  };
});
