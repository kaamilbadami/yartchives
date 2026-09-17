const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const UI = require("../apply-next-location-profile-ui.js");

assert.equal(UI.normalizedRemotePreference({}), "acceptable");
assert.equal(UI.normalizedRemotePreference({ remoteRelevant: false }), "not_preferred");
assert.equal(UI.normalizedRemotePreference({ remotePreference: "preferred" }), "preferred");

assert.equal(UI.normalizedRelocationPreference({}), "open");
assert.equal(UI.normalizedRelocationPreference({ relocationAllowed: false }), "not_open");
assert.equal(UI.normalizedRelocationPreference({ relocationPreference: "preferred" }), "preferred");

const preferred = UI.applyLocationPreferences({}, {
  remotePreference: "preferred",
  relocationPreference: "preferred",
});
assert.equal(preferred.remotePreference, "preferred");
assert.equal(preferred.remoteRelevant, true);
assert.equal(preferred.relocationPreference, "preferred");
assert.equal(preferred.relocationAllowed, true);

const restrictive = UI.applyLocationPreferences({}, {
  remotePreference: "not_preferred",
  relocationPreference: "not_open",
});
assert.equal(restrictive.remoteRelevant, false);
assert.equal(restrictive.relocationAllowed, false);

const legacy = UI.applyLocationPreferences({ remoteRelevant: false, relocationAllowed: true }, {});
assert.equal(legacy.remotePreference, "not_preferred");
assert.equal(legacy.relocationPreference, "open");

assert.deepEqual(UI.REMOTE_OPTIONS.map(([value]) => value), ["preferred", "acceptable", "not_preferred"]);
assert.deepEqual(UI.RELOCATION_OPTIONS.map(([value]) => value), ["not_open", "open", "preferred"]);

const index = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
assert.ok(index.includes('src="apply-next-location-profile-ui.js"'));
assert.ok(index.indexOf('src="apply-next-profile-setup.js"') < index.indexOf('src="apply-next-location-profile-ui.js"'), "location preference UI should enhance the profile editor after profile setup loads");

const source = fs.readFileSync(path.join(__dirname, "..", "apply-next-location-profile-ui.js"), "utf8");
assert.match(source, /Base ZIPs, in priority order/);
assert.match(source, /Prefer remote/);
assert.match(source, /Remote is acceptable/);
assert.match(source, /Prefer in-person \/ hybrid/);
assert.match(source, /Not open to relocating/);
assert.match(source, /Open to relocating for a worthwhile role/);
assert.match(source, /Prefer relocating for the right role/);

console.log("apply-next visible location preference tests passed");
