/* Public profile set. Keep weak-coverage fields internal until their source layer is ready. */
(() => {
  if (typeof PROFILE_LABELS === "undefined" || typeof PROFILE_TITLES === "undefined") return;

  PROFILE_LABELS["tech-business"] = "Business / Product / Analytics";
  PROFILE_TITLES["tech-business"] = "Business / Product / Analytics";

  PROFILE_LABELS.mechanical = "Mechanical / Manufacturing";
  PROFILE_TITLES.mechanical = "Mechanical / Manufacturing";

  PROFILE_LABELS.electrical = "Electrical / Computer Eng.";
  PROFILE_TITLES.electrical = "Electrical / Computer Engineering";

  // These tags remain in the feed for internal auditing, but current source
  // coverage is not strong enough to present them as first-class public profiles.
  delete PROFILE_LABELS.policy;
  delete PROFILE_TITLES.policy;
  delete PROFILE_LABELS.health;
  delete PROFILE_TITLES.health;
})();
