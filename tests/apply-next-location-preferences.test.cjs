const assert = require("node:assert/strict");
const L = require("../apply-next-location-preferences.js");

function inspectedJob(overrides = {}) {
  return {
    company: "Example",
    title: "Software Engineer Intern",
    profiles: ["cs"],
    states: ["CT"],
    location: "Stamford, CT",
    term: "Summer 2027",
    posted_at: "2026-09-16T12:00:00Z",
    link_kind: "direct",
    url: "https://example.com/job",
    _inspection: {
      status: "inspected",
      posting: { application_status: "available" },
      requirements: {},
    },
    ...overrides,
  };
}

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship"],
  preferredProfiles: ["cs"],
  supportedKeywords: ["software engineer"],
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
  baseZips: ["06897", "20740"],
  baseLabels: ["Home", "School"],
  nearbyMiles: 50,
  preferredStates: ["CT", "MD"],
  remoteRelevant: true,
  relocationAllowed: true,
};

assert.deepEqual(L.orderedAnchors(profile), [
  { zip: "06897", label: "Home", commuteMiles: 50, order: 0 },
  { zip: "20740", label: "School", commuteMiles: 50, order: 1 },
]);

const explicitProfile = {
  ...profile,
  locationAnchors: [
    { zip: "06897", label: "Home", commuteMiles: 35 },
    { zip: "20740", label: "School", commuteMiles: 20 },
  ],
};
assert.equal(L.orderedAnchors(explicitProfile)[0].commuteMiles, 35);
assert.equal(L.orderedAnchors(explicitProfile)[1].commuteMiles, 20);

const nearPrimary = inspectedJob({
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 18 },
    { zip: "20740", distanceMiles: 240 },
  ],
});
const nearSecondary = inspectedJob({
  states: ["MD"],
  location: "Washington, DC",
  url: "https://example.com/job-secondary",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 260 },
    { zip: "20740", distanceMiles: 9 },
  ],
});
const primaryScore = L.scoreLocation(nearPrimary, explicitProfile);
const secondaryScore = L.scoreLocation(nearSecondary, explicitProfile);
assert.equal(primaryScore.score, 10);
assert.match(primaryScore.detail, /Home/);
assert.equal(secondaryScore.score, 9);
assert.match(secondaryScore.detail, /School/);
assert.ok(primaryScore.score > secondaryScore.score, "primary commute anchor should outrank a secondary anchor");

const far = inspectedJob({
  states: ["TX"],
  location: "Austin, TX",
  url: "https://example.com/job-far",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 1700 },
    { zip: "20740", distanceMiles: 1400 },
  ],
});
const noRelocation = { ...explicitProfile, relocationAllowed: false, relocationPreference: "not_open" };
const farDecision = L.scoreLocation(far, noRelocation);
assert.equal(farDecision.excluded, true);
assert.equal(farDecision.score, 0);
assert.match(farDecision.detail, /relocation is turned off/i);
assert.equal(L.scoreJob(far, noRelocation, new Date("2026-09-16T16:00:00Z")).excluded, true);
assert.equal(L.rankJobs([nearPrimary, far], noRelocation, new Date("2026-09-16T16:00:00Z")).length, 1);

const openRelocation = { ...explicitProfile, relocationPreference: "open" };
assert.equal(L.scoreLocation(far, openRelocation).excluded, undefined);
assert.ok(L.scoreLocation(far, openRelocation).score > 0);

const remote = inspectedJob({ states: ["Remote"], location: "Remote", url: "https://example.com/remote" });
assert.equal(L.scoreLocation(remote, { ...explicitProfile, remotePreference: "preferred" }).score, 10);
assert.equal(L.scoreLocation(remote, { ...explicitProfile, remotePreference: "acceptable" }).score, 8);
assert.equal(L.scoreLocation(remote, { ...explicitProfile, remotePreference: "not_preferred" }).score, 3);

const captured = inspectedJob({
  _applyNextAnchorDistanceSamples: [
    { distanceMiles: 12 },
    { distanceMiles: 230 },
  ],
});
assert.equal(L.anchorDistances(captured, explicitProfile)[0].distanceMiles, 12);
assert.equal(L.scoreLocation(captured, explicitProfile).score, 10);

const unknownCaptured = inspectedJob({
  states: ["NC"],
  location: "RTP, North Carolina, US",
  _applyNextAnchorDistanceSamples: [
    { distanceMiles: null },
    { distanceMiles: null },
  ],
});
assert.deepEqual(L.anchorDistances(unknownCaptured, explicitProfile), [], "null captured distances must remain unknown instead of becoming zero miles");
assert.notEqual(L.scoreLocation(unknownCaptured, explicitProfile).score, 10, "unknown RTP distance must not earn a primary-base commute score");
assert.match(L.scoreLocation(unknownCaptured, explicitProfile).detail, /distance is unavailable|cannot be verified/i);

const scope = {
  distanceForJob(job, origin) {
    return origin.distance;
  },
};
assert.equal(L.captureGlobalDistanceSamples(scope), true);
const capturedJob = {};
scope.distanceForJob(capturedJob, { distance: 15, state: "CT", city: "Wilton" }, {});
scope.distanceForJob(capturedJob, { distance: 250, state: "MD", city: "College Park" }, {});
assert.deepEqual(capturedJob._applyNextAnchorDistanceSamples.map(x => x.distanceMiles), [15, 250]);
assert.equal(L.captureGlobalDistanceSamples(scope), true, "wrapping distanceForJob should be idempotent");

const legacy = {
  targetTerm: "Summer 2027",
  preferredStates: ["CT"],
  nearbyMiles: 50,
  remoteRelevant: true,
  relocationAllowed: true,
};
assert.deepEqual(L.scoreLocation({ location: "Stamford, CT", states: ["CT"] }, legacy), {
  score: 10,
  detail: "Preferred state: CT",
});

console.log("apply-next multi-anchor location preference tests passed");