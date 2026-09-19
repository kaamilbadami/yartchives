const assert = require("node:assert/strict");
const Companies = require("../companies.js");

const grouped = Companies.groupCompanies([
  { company: "Capital One", _metadata_normalized_company: "capital one", posted_at: "2026-09-18T12:00:00Z" },
  { company: "Capital One Financial", _metadata_normalized_company: "capital one", posted_at: "2026-09-19T12:00:00Z" },
  { company: "Adobe", posted_at: "2026-09-17T12:00:00Z" },
]);

assert.equal(grouped.length, 2);
assert.equal(grouped[0].key, "capital one");
assert.equal(grouped[0].count, 2);
assert.equal(grouped[0].name, "Capital One");
assert.equal(grouped[0].latestPostedAt, "2026-09-19T12:00:00Z");
assert.equal(grouped[1].name, "Adobe");
assert.equal(Companies.normalizedCompanyKey({ company: "  Foo, Inc. " }), "foo inc");

console.log("company directory regression tests passed");
