const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const UI = require("../apply-next-location-profile-ui.js");

assert.equal(UI.normalizedLocationMode({}), "normal");
assert.equal(UI.normalizedLocationMode({ locationMode: "custom" }), "custom");
assert.equal(UI.normalizedLocationMode({ locationAnchors: [{ zip: "06897", locationScore: 15 }] }), "custom");

const defaults = UI.applyLocationPreferences({ baseZips: ["06897"], nearbyMiles: 50 }, {
  locationMode: "normal",
  homeZip: "06897",
  homeCommuteMiles: 45,
});
assert.equal(defaults.locationPreferencesVersion, 2);
assert.equal(defaults.locationMode, "normal");
assert.deepEqual(defaults.baseZips, ["06897"]);
assert.equal(defaults.nearbyMiles, 45);
assert.deepEqual(defaults.preferredStates, []);
assert.equal(defaults.remoteScore, 20);
assert.equal(defaults.relocationScore, 8);
assert.deepEqual(defaults.relocationRegionScores, {});
assert.equal(defaults.excludeRelocation, false);

const custom = UI.applyLocationPreferences({}, {
  locationMode: "custom",
  anchors: [
    { zip: "06897", label: "Home", commuteMiles: 45, locationScore: 20 },
    { zip: "20740", label: "School", commuteMiles: 30, locationScore: 13 },
  ],
  remoteScore: 17,
  relocationScore: 6,
  regionScores: {
    new_england: 11,
    south_central: 4,
    west_coast: 5,
  },
  excludeRelocation: false,
});
assert.equal(custom.locationMode, "custom");
assert.equal(custom.locationPreferencesVersion, 2);
assert.deepEqual(custom.preferredStates, []);
assert.deepEqual(custom.baseZips, ["06897", "20740"]);
assert.deepEqual(custom.locationAnchors, [
  { zip: "06897", label: "Home", commuteMiles: 45, locationScore: 20 },
  { zip: "20740", label: "School", commuteMiles: 30, locationScore: 13 },
]);
assert.equal(custom.remoteScore, 17);
assert.equal(custom.relocationScore, 6);
assert.deepEqual(custom.relocationRegionScores, {
  new_england: 11,
  south_central: 4,
  west_coast: 5,
});
assert.equal(custom.excludeRelocation, false);

const noMove = UI.applyLocationPreferences(custom, {
  locationMode: "custom",
  anchors: custom.locationAnchors,
  remoteScore: 17,
  relocationScore: 6,
  regionScores: custom.relocationRegionScores,
  excludeRelocation: true,
});
assert.equal(noMove.excludeRelocation, true);
assert.equal(noMove.relocationAllowed, false);

assert.throws(
  () => UI.applyLocationPreferences({}, { locationMode: "custom", anchors: [] }),
  /at least one commute base/i
);
assert.throws(
  () => UI.applyLocationPreferences({}, { locationMode: "custom", anchors: [{ zip: "nope", commuteMiles: 50, locationScore: 20 }] }),
  /valid 5-digit ZIP/i
);

const legacy = {
  locationMode: "custom",
  locationPreferencesVersion: 1,
  baseZips: ["06897", "20740"],
  locationAnchors: [
    { zip: "06897", label: "Home", commuteMiles: 35, locationScore: 15 },
    { zip: "20740", label: "School", commuteMiles: 20, locationScore: 10 },
  ],
  remotePreference: "acceptable",
  relocationPreference: "preferred",
};
assert.deepEqual(UI.anchorsFromProfile(legacy).map(anchor => anchor.locationScore), [20, 13]);
assert.equal(UI.defaultRemoteScore(legacy), 16);
assert.equal(UI.defaultRelocationScore(legacy), 11);

assert.deepEqual(UI.LOCATION_MODE_OPTIONS, [
  ["normal", "Default scoring (recommended)"],
  ["custom", "Custom scoring (advanced)"],
]);
assert.ok(UI.RELOCATION_REGIONS.some(region => region.label === "New England" && /MA/.test(region.states)));
assert.ok(UI.RELOCATION_REGIONS.some(region => region.label === "South Central" && /TX/.test(region.states)));

const index = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
assert.ok(index.includes('src="apply-next-location-profile-ui.js"'));
assert.ok(index.indexOf('src="apply-next-profile-setup.js"') < index.indexOf('src="apply-next-location-profile-ui.js"'), "location UI should enhance the profile editor after profile setup loads");

const source = fs.readFileSync(path.join(__dirname, "..", "apply-next-location-profile-ui.js"), "utf8");
assert.match(source, /Location preferences/);
assert.match(source, /Location scoring/);
assert.match(source, /Default scoring \(recommended\)/);
assert.match(source, /Custom scoring \(advanced\)/);
assert.match(source, /relocation—not a larger commute radius/);
assert.match(source, /Daily commute radius \(miles\)/);
assert.doesNotMatch(source, /makeModeToggle/);
assert.match(source, /Remote = 20/);
assert.match(source, /20 to 16/);
assert.match(source, /Custom scoring/);
assert.match(source, /Remote score \/20/);
assert.match(source, /Default relocation score \/20/);
assert.match(source, /Fine-tune relocation by area/);
assert.match(source, /included states are shown/);
assert.match(source, /Hide roles that require moving outside my commute bases/);
assert.doesNotMatch(source, /Prefer relocating for the right role/);
assert.doesNotMatch(source, /Remote is acceptable/);

const css = fs.readFileSync(path.join(__dirname, "..", "apply-next-profile-setup.css"), "utf8");
assert.match(css, /apply-next-location-anchor-row/);
assert.match(css, /apply-next-location-region-card/);

console.log("apply-next location preference UI tests passed");
