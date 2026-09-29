/* Public profile set. Keep weak-coverage fields internal until their source layer is ready. */
(() => {
  if (typeof PROFILE_LABELS === "undefined" || typeof PROFILE_TITLES === "undefined") return;

  PROFILE_LABELS["tech-business"] = "Business / Product / Analytics";
  PROFILE_TITLES["tech-business"] = "Business / Product / Analytics";

  // Engineering disciplines are role-family metadata, not peer career profiles.
  for (const legacyEngineeringProfile of ["mechanical", "aero", "electrical"]) {
    delete PROFILE_LABELS[legacyEngineeringProfile];
    delete PROFILE_TITLES[legacyEngineeringProfile];
  }

  // These tags remain internal until their source layer is ready.
  delete PROFILE_LABELS.policy;
  delete PROFILE_TITLES.policy;
  delete PROFILE_LABELS.health;
  delete PROFILE_TITLES.health;
})();
