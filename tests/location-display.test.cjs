const assert = require("node:assert/strict");
const U = require("../frontend-utils.js");
global.YartchivesUtils = U;
const L = require("../location-display.js");

const cigna = "4 locations Bloomington, MN / Morris Plains, NJ / St. Louis, MO / Bloomfield, CT";
const bloomfield = L.summarizeLocationForMatch(cigna, { city: "bloomfield", state: "CT" });
assert.equal(bloomfield.matched, true);
assert.equal(bloomfield.text, "Bloomfield, CT + 3 more");
assert.equal(bloomfield.matchedText, "Bloomfield, CT");
assert.equal(bloomfield.full, cigna);

const bloomington = L.summarizeLocationForMatch(cigna, { city: "Bloomington", state: "MN" });
assert.equal(bloomington.text, "Bloomington, MN + 3 more");

const noPoint = L.summarizeLocationForMatch(cigna, null);
assert.equal(noPoint.matched, false);
assert.equal(noPoint.text, cigna);

const single = L.summarizeLocationForMatch("Bloomfield, CT", { city: "Bloomfield", state: "CT" });
assert.equal(single.matched, false);
assert.equal(single.text, "Bloomfield, CT");

const duplicateCity = "Springfield, MA / Springfield, IL";
assert.equal(
  L.summarizeLocationForMatch(duplicateCity, { city: "Springfield", state: "IL" }).text,
  "Springfield, IL + 1 more"
);

console.log("location display tests passed");
