const assert = require("node:assert/strict");
const { groupCompanies, sortCompanies } = require("../companies.js");

const jobs = [
  { company: "Alpha", posted_at: "2026-09-10T00:00:00Z" },
  { company: "Alpha", posted_at: "2026-09-11T00:00:00Z" },
  { company: "Beta", posted_at: "2026-09-18T00:00:00Z" },
  { company: "Gamma", posted_at: "2026-09-12T00:00:00Z" },
  { company: "Gamma", posted_at: "2026-09-13T00:00:00Z" },
  { company: "Gamma", posted_at: "2026-09-14T00:00:00Z" },
];

assert.deepEqual(groupCompanies(jobs, "openings").map(x => x.name), ["Gamma", "Alpha", "Beta"]);
assert.deepEqual(groupCompanies(jobs, "newest").map(x => x.name), ["Beta", "Gamma", "Alpha"]);
assert.deepEqual(groupCompanies(jobs, "company").map(x => x.name), ["Alpha", "Beta", "Gamma"]);

const grouped = groupCompanies(jobs);
assert.equal(grouped.find(x => x.name === "Gamma").count, 3);
assert.equal(grouped.find(x => x.name === "Beta").latestPostedAt, "2026-09-18T00:00:00Z");

assert.deepEqual(sortCompanies(grouped, "openings").map(x => x.name), ["Gamma", "Alpha", "Beta"]);

const fs = require("node:fs");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "..", "companies.js"), "utf8");
assert.match(source, /id="companySortSelect"/, "Companies should own a dedicated sort select");
assert.doesNotMatch(source, /sortSelect\.innerHTML/, "Companies must not rewrite the Jobs sort select");
assert.doesNotMatch(source, /stopImmediatePropagation/, "Company sorting should not suppress the Jobs sort listener");

const css = fs.readFileSync(path.join(__dirname, "..", "ui.css"), "utf8");
assert.match(css, /\.sort-field\[hidden\]\s*\{\s*display:\s*none;/, "Hidden sort fields must not be displayed");

console.log("company sort regression tests passed");
