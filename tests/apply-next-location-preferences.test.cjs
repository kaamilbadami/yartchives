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
  { zip: "06897", label: "Home", commuteMiles: 50, locationScore: null, order: 0 },
  { zip: "20740", label: "School", commuteMiles: 50, locationScore: null, order: 1 },
]);

const explicitProfile = {
  ...profile,
  locationAnchors: [
    { zip: "06897", label: "Home", commuteMiles: 35 },
    { zip: "20740", label: "School", commuteMiles: 20 },
  ],
};
assert.equal(L.customLocationMode(explicitProfile), true, "legacy profiles with explicit anchors stay custom");
assert.equal(L.orderedAnchors(explicitProfile)[0].commuteMiles, 35);
assert.equal(L.orderedAnchors(explicitProfile)[1].commuteMiles, 20);

const normalWithStaleAnchors = {
  ...explicitProfile,
  locationMode: "normal",
};
assert.equal(L.customLocationMode(normalWithStaleAnchors), false);
assert.equal(L.orderedAnchors(normalWithStaleAnchors)[0].commuteMiles, 50, "normal mode ignores stale custom anchors");

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

const customProfile = {
  ...profile,
  locationMode: "custom",
  baseZips: ["06897", "20740", "10001"],
  baseLabels: ["Home", "School", "NYC"],
  locationAnchors: [
    { zip: "06897", label: "Home", locationScore: 15 },
    { zip: "20740", label: "School", locationScore: 10 },
    { zip: "10001", label: "NYC", locationScore: 4 },
  ],
};
assert.deepEqual(L.orderedAnchors(customProfile).map(anchor => anchor.locationScore), [15, 10, 4]);

const customNearPrimary = inspectedJob({
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 18 },
    { zip: "20740", distanceMiles: 240 },
    { zip: "10001", distanceMiles: 65 },
  ],
});
const customNearSecondary = inspectedJob({
  states: ["MD"],
  location: "Washington, DC",
  url: "https://example.com/custom-secondary",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 260 },
    { zip: "20740", distanceMiles: 9 },
    { zip: "10001", distanceMiles: 220 },
  ],
});
const nearThird = inspectedJob({
  states: ["NY"],
  location: "New York, NY",
  url: "https://example.com/job-third",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 70 },
    { zip: "20740", distanceMiles: 210 },
    { zip: "10001", distanceMiles: 8 },
  ],
});
assert.equal(L.scoreLocation(customNearPrimary, customProfile).score, 10, "15/15 custom anchor maps to legacy 10/10 before dimension scaling");
assert.equal(L.scoreLocation(customNearSecondary, customProfile).score, 10 / 1.5, "10/15 custom anchor maps proportionally before dimension scaling");
assert.equal(L.scoreLocation(nearThird, customProfile).score, 4 / 1.5, "third and later anchors can have arbitrary scores");

const overlapping = inspectedJob({
  states: ["MD"],
  location: "Overlap",
  url: "https://example.com/overlap",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 20 },
    { zip: "20740", distanceMiles: 15 },
    { zip: "10001", distanceMiles: 500 },
  ],
});
const reversedScores = {
  ...customProfile,
  locationAnchors: [
    { zip: "06897", label: "Home", locationScore: 7 },
    { zip: "20740", label: "School", locationScore: 12 },
    { zip: "10001", label: "NYC", locationScore: 4 },
  ],
};
const overlappingScore = L.scoreLocation(overlapping, reversedScores);
assert.equal(overlappingScore.score, 8, "overlapping anchors use the highest configured score");
assert.match(overlappingScore.detail, /School/);

assert.equal(L.customRelocationScore(200, "preferred") * 1.5, 8, "custom preferred relocation starts at 8/15 through 200 miles");
assert.equal(L.customRelocationScore(300, "preferred") * 1.5, 4, "custom preferred relocation decays linearly between 200 and 400 miles");
assert.equal(L.customRelocationScore(400, "preferred"), 0, "custom preferred relocation reaches zero at 400 miles");
assert.equal(L.customRelocationScore(200, "open") * 1.5, 6, "custom open relocation uses the same curve with a lower ceiling");
assert.equal(L.customRelocationScore(300, "open") * 1.5, 3);
assert.equal(L.customRelocationScore(400, "open"), 0);

const customMidDistance = inspectedJob({
  states: ["PA"],
  location: "Custom mid-distance",
  url: "https://example.com/custom-mid-distance",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 300 },
    { zip: "20740", distanceMiles: 350 },
    { zip: "10001", distanceMiles: 325 },
  ],
});
const customFarDistance = inspectedJob({
  states: ["IN"],
  location: "Custom far-distance",
  url: "https://example.com/custom-far-distance",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 494 },
    { zip: "20740", distanceMiles: 560 },
    { zip: "10001", distanceMiles: 645 },
  ],
});
const customPreferred = { ...customProfile, relocationPreference: "preferred" };
assert.equal(L.scoreLocation(customMidDistance, customPreferred).score * 1.5, 4, "300-mile custom fallback displays as 4/15");
assert.equal(L.scoreLocation(customFarDistance, customPreferred).score, 0, "494-mile custom fallback no longer floors at 9/15");
assert.match(L.scoreLocation(customFarDistance, customPreferred).detail, /about 494 miles/);

const normalFarDistance = inspectedJob({
  states: ["IN"],
  location: "Normal far-distance",
  url: "https://example.com/normal-far-distance",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 494 },
    { zip: "20740", distanceMiles: 560 },
  ],
});
const normalPreferred = { ...normalWithStaleAnchors, relocationPreference: "preferred" };
assert.equal(L.scoreLocation(normalFarDistance, normalPreferred).score, 6, "Normal mode keeps existing generic relocation semantics");

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
assert.equal(L.scoreLocation(far, openRelocation).score, 0, "custom open relocation also decays to zero beyond 400 miles");

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

const unresolvedCaptured = inspectedJob({
  states: ["NC"],
  location: "RTP, NC",
  _applyNextAnchorDistanceSamples: [
    { distanceMiles: null },
    { distanceMiles: null },
  ],
});
assert.deepEqual(L.anchorDistances(unresolvedCaptured, explicitProfile), []);
assert.notEqual(L.scoreLocation(unresolvedCaptured, explicitProfile).score, 10, "unknown distance must not become zero-mile commute");

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
