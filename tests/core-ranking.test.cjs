const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(require.resolve("../app.js"), "utf8");
const element = {
  addEventListener() {},
  classList: { add() {}, remove() {}, toggle() {} },
  textContent: "",
};
const context = {
  document: {
    querySelector: () => element,
    querySelectorAll: () => [],
  },
  localStorage: { getItem: () => "{}", setItem() {} },
  location: { search: "", href: "https://example.test/yartchives/" },
  URLSearchParams,
  console,
};

vm.createContext(context);
vm.runInContext(
  `${source.replace(/\nboot\(\);\s*$/, "")}\nglobalThis.__core = { state, sortFiltered, updateResultsNote, els };`,
  context
);

const { state, sortFiltered, updateResultsNote, els } = context.__core;
const newerNonCt = { company: "Newer non-CT", states: ["MD"], posted_at: "2026-09-15T00:00:00Z" };
const olderCt = { company: "Older CT", states: ["CT"], posted_at: "2026-09-01T00:00:00Z" };

state.location = "";
const noLocation = [olderCt, newerNonCt];
sortFiltered(noLocation, false);
assert.deepEqual(noLocation.map(job => job.company), ["Newer non-CT", "Older CT"]);

state.location = "06897";
const distanceOrder = [
  { ...newerNonCt, _distanceMiles: 30 },
  { ...olderCt, _distanceMiles: 5 },
];
sortFiltered(distanceOrder, true);
assert.deepEqual(distanceOrder.map(job => job.company), ["Older CT", "Newer non-CT"]);

state.location = "";
updateResultsNote();
assert.equal(
  els.resultsNote.textContent,
  "No location filter is selected. Enter a ZIP code to use radius filtering or sort by distance."
);
assert.doesNotMatch(source, /Connecticut listings are ranked first/i);

console.log("core ranking tests passed");
