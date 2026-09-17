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

const defaultProfile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship"],
  preferredProfiles: ["cs"],
  supportedKeywords: ["software engineer"],
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
  locationPreferencesVersion: 2,
  locationMode: "normal",
  baseZips: ["06897"],
  baseLabels: ["Home"],
  nearbyMiles: 50,
};

assert.equal(L.customLocationMode(defaultProfile), false);
assert.equal(L.DEFAULT_REMOTE_SCORE, 20);
assert.equal(L.DEFAULT_RELOCATION_SCORE, 8);
assert.equal(L.DEFAULT_UNKNOWN_SCORE, 10);
assert.equal(L.DEFAULT_MIN_COMMUTE_SCORE, 16);
assert.equal(L.defaultCommuteScore(0, 50), 20);
assert.equal(L.defaultCommuteScore(25, 50), 18);
assert.equal(L.defaultCommuteScore(50, 50), 16);
assert.equal(L.defaultCommuteScore(51, 50), 8);

const remote = inspectedJob({ states: ["Remote"], location: "Remote", url: "https://example.com/remote" });
assert.deepEqual(L.scoreLocation(remote, defaultProfile), { score: 20, detail: "Remote opportunity" });

const easyCommute = inspectedJob({
  _locationAnchorDistances: [{ zip: "06897", distanceMiles: 5 }],
});
const mediumCommute = inspectedJob({
  url: "https://example.com/medium",
  _locationAnchorDistances: [{ zip: "06897", distanceMiles: 25 }],
});
const edgeCommute = inspectedJob({
  url: "https://example.com/edge",
  _locationAnchorDistances: [{ zip: "06897", distanceMiles: 50 }],
});
const relocation = inspectedJob({
  states: ["TX"],
  location: "Austin, TX",
  url: "https://example.com/relocation",
  _locationAnchorDistances: [{ zip: "06897", distanceMiles: 1700 }],
});
assert.equal(L.scoreLocation(easyCommute, defaultProfile).score, 20);
assert.equal(L.scoreLocation(mediumCommute, defaultProfile).score, 18);
assert.equal(L.scoreLocation(edgeCommute, defaultProfile).score, 16);
assert.equal(L.scoreLocation(relocation, defaultProfile).score, 8);

const unknown = inspectedJob({
  states: ["MA"],
  location: "Boston, MA",
  url: "https://example.com/unknown",
  _locationAnchorDistances: [],
});
assert.equal(L.scoreLocation(unknown, defaultProfile).score, 10, "missing distance is uncertainty, not a relocation penalty");

const customProfile = {
  ...defaultProfile,
  locationMode: "custom",
  baseZips: ["06897", "20740"],
  baseLabels: ["Home", "School"],
  locationAnchors: [
    { zip: "06897", label: "Home", commuteMiles: 45, locationScore: 20 },
    { zip: "20740", label: "School", commuteMiles: 30, locationScore: 13 },
  ],
  remoteScore: 17,
  relocationScore: 6,
  relocationRegionScores: {
    new_england: 11,
    mid_atlantic: 10,
    south_central: 4,
    west_coast: 5,
  },
  excludeRelocation: false,
};

assert.equal(L.customLocationMode(customProfile), true);
assert.deepEqual(L.orderedAnchors(customProfile).map(anchor => anchor.locationScore), [20, 13]);
assert.equal(L.scoreLocation(remote, customProfile).score, 17);

const nearPrimary = inspectedJob({
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 18 },
    { zip: "20740", distanceMiles: 240 },
  ],
});
const nearSecondary = inspectedJob({
  states: ["MD"],
  location: "College Park, MD",
  url: "https://example.com/secondary",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 260 },
    { zip: "20740", distanceMiles: 9 },
  ],
});
assert.equal(L.scoreLocation(nearPrimary, customProfile).score, 20);
assert.equal(L.scoreLocation(nearSecondary, customProfile).score, 13);

const overlap = inspectedJob({
  url: "https://example.com/overlap",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 20 },
    { zip: "20740", distanceMiles: 15 },
  ],
});
const reversed = {
  ...customProfile,
  locationAnchors: [
    { zip: "06897", label: "Home", commuteMiles: 45, locationScore: 12 },
    { zip: "20740", label: "School", commuteMiles: 30, locationScore: 18 },
  ],
};
assert.equal(L.scoreLocation(overlap, reversed).score, 18, "highest matching base score wins");

const boston = inspectedJob({
  states: ["MA"],
  location: "Boston, MA",
  url: "https://example.com/boston",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 160 },
    { zip: "20740", distanceMiles: 430 },
  ],
});
const austin = inspectedJob({
  states: ["TX"],
  location: "Austin, TX",
  url: "https://example.com/austin",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 1700 },
    { zip: "20740", distanceMiles: 1400 },
  ],
});
const colorado = inspectedJob({
  states: ["CO"],
  location: "Denver, CO",
  url: "https://example.com/denver",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: 1750 },
    { zip: "20740", distanceMiles: 1650 },
  ],
});
assert.equal(L.regionForState("MA"), "new_england");
assert.equal(L.regionForState("TX"), "south_central");
assert.equal(L.scoreLocation(boston, customProfile).score, 11);
assert.equal(L.scoreLocation(austin, customProfile).score, 4);
assert.equal(L.scoreLocation(colorado, customProfile).score, 6, "regions without an override use the default relocation score");

const noMove = { ...customProfile, excludeRelocation: true };
const excluded = L.scoreLocation(austin, noMove);
assert.equal(excluded.excluded, true);
assert.equal(excluded.score, 0);
assert.equal(L.scoreJob(austin, noMove, new Date("2026-09-16T16:00:00Z")).excluded, true);

const unresolvedCustom = inspectedJob({
  states: ["NC"],
  location: "RTP, NC",
  url: "https://example.com/rtp",
  _locationAnchorDistances: [
    { zip: "06897", distanceMiles: null },
    { zip: "20740", distanceMiles: null },
  ],
});
assert.equal(L.scoreLocation(unresolvedCustom, customProfile).score, 10, "custom unknown distance remains neutral uncertainty");

const legacyCustom = {
  ...defaultProfile,
  locationPreferencesVersion: 1,
  locationMode: "custom",
  baseZips: ["06897", "20740"],
  locationAnchors: [
    { zip: "06897", locationScore: 15 },
    { zip: "20740", locationScore: 10 },
  ],
};
assert.deepEqual(L.orderedAnchors(legacyCustom).map(anchor => anchor.locationScore), [20, 13], "legacy 0-15 custom scores migrate onto the final 0-20 range");

const scope = {
  distanceForJob(job, origin) {
    return origin.distance;
  },
};
assert.equal(L.captureGlobalDistanceSamples(scope), true);
const capturedJob = {};
scope.distanceForJob(capturedJob, { distance: 15, state: "CT", city: "Wilton" }, {});
assert.deepEqual(capturedJob._applyNextAnchorDistanceSamples.map(x => x.distanceMiles), [15]);
assert.equal(L.captureGlobalDistanceSamples(scope), true, "distance capture remains idempotent");

console.log("apply-next default/custom location preference tests passed");
