const assert = require("node:assert/strict");
const D = require("../apply-next-dimensions.js");

// Test that invalid dates do not result in NaN sort order issues
const profile = {targetTerm: 'Summer 2027'};
const now = new Date("2026-09-17T12:00:00Z");

const inspection_obj = { status: "inspected", posting: { application_status: "available" }, requirements: { skills: { required: [], preferred: [], unspecified: [], not_required: [] }, education: { required: [], preferred: [], unspecified: [], not_required: [] }, major_fields: { required: [], preferred: [], unspecified: [], not_required: [] } } };

const pool = [
  { company: "Company B", term: 'Summer 2027', opportunity_type: 'internship', posted_at: "invalid_date", _inspection: inspection_obj },
  { company: "Company A", term: 'Summer 2027', opportunity_type: 'internship', posted_at: "2026-09-17T10:00:00Z", _inspection: inspection_obj },
  { company: "Company C", term: 'Summer 2027', opportunity_type: 'internship', posted_at: null, _inspection: inspection_obj },
];

const ranked = D.rankJobs(pool, profile, now);

// Company A has a valid date, so its score is technically bumped due to freshness, but
// we care about it not crashing or failing to sort due to NaN.
assert.equal(ranked.length, 3);
// B and C have invalid/null dates, so they fallback to 0 time, meaning they should sort by name after A.
// However, A is also higher ranked because of freshness (score +).
assert.equal(ranked[0].job.company, "Company A");
// Between B and C (same total score), it should fallback to company name
assert.equal(ranked[1].job.company, "Company B");
assert.equal(ranked[2].job.company, "Company C");

console.log("apply-next ranking sort test passed");
