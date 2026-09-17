const assert = require("node:assert/strict");
const D = require("../apply-next-dimensions.js");

const now = new Date("2026-09-16T16:00:00Z");
const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software", "java", "systems"],
  cautiousKeywords: ["python"],
  facts: { supportedSkills: ["Java", "systems"], cautiousSkills: ["Python"] },
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
  preferredStates: ["CT"],
  relocationAllowed: true,
};

function inspection(required = [], preferred = []) {
  return {
    status: "inspected",
    posting: { application_status: "available" },
    requirements: {
      skills: {
        required: required.map(([statement, technologies]) => ({ statement, technologies })),
        preferred: preferred.map(([statement, technologies]) => ({ statement, technologies })),
        unspecified: [], not_required: [],
      },
    },
  };
}

function job(overrides = {}) {
  return {
    company: "ExampleCo",
    title: "Software Engineer Intern",
    profiles: ["cs"],
    states: ["CT"],
    location: "Hartford, CT",
    term: "Summer 2027",
    posted_at: "2026-09-15T12:00:00Z",
    link_kind: "direct",
    url: "https://example.com/job",
    ...overrides,
  };
}

const metadataOnly = D.scoreJob(job({ _inspection: undefined }), profile, now);
assert.equal(metadataOnly.components.fit.score, 12);
assert.equal(metadataOnly.components.role.score, 10);
assert.match(metadataOnly.components.fit.detail, /neutral qualification-fit/i);

const supported = D.scoreJob(job({
  _inspection: inspection([["Java required", ["Java"]]]),
}), profile, now);
const unsupported = D.scoreJob(job({
  url: "https://example.com/unsupported",
  _inspection: inspection([["Rust required", ["Rust"]]]),
}), profile, now);
assert.ok(supported.components.fit.score > unsupported.components.fit.score);
assert.doesNotMatch(supported.components.fit.detail, /Career-area overlap|Supported metadata matches/i);

const exactTerm = D.scoreJob(job({ _inspection: inspection() }), profile, now);
const unknownTerm = D.scoreJob(job({ term: null, url: "https://example.com/unknown", _inspection: inspection() }), profile, now);
assert.equal(exactTerm.components.eligibility.score, 20);
assert.equal(unknownTerm.components.eligibility.score, 20);
assert.match(exactTerm.components.eligibility.detail, /gate, not a ranking advantage/i);

const demandPool = [
  job({ id: "a", _inspection: inspection([["Java required", ["Java"]]]) }),
  job({ id: "b", url: "https://example.com/b", location: "Stamford, CT", _inspection: inspection([["Java required", ["Java"]]]) }),
];
const demandRanked = D.rankJobs(demandPool, profile, now);
assert.equal(demandRanked.length, 2);
assert.match(demandRanked[0].components.roi.detail, /observed employer demand/i);
assert.doesNotMatch(demandRanked[0].components.roi.detail, /required-skill differentiation|specialized role aligns/i);
assert.equal(demandRanked[0].competition.differentiationBonus, 0);

const direct = D.scoreJob(job({ _inspection: inspection() }), profile, now);
const listing = D.scoreJob(job({ link_kind: "listing", url: "https://example.com/listing", _inspection: inspection() }), profile, now);
assert.equal(direct.components.link.score, 0);
assert.equal(listing.components.link.score, 0);
assert.match(direct.components.link.detail, /provenance only/i);
assert.equal(direct.total, listing.total);
assert.equal(direct.scoringSemantics.neutralScaleOffset, 5);

const cautious = D.scoreJob(job({
  url: "https://example.com/cautious",
  _inspection: inspection([["Python required", ["Python"]]]),
}), profile, now);
assert.ok(cautious.components.fit.score < supported.components.fit.score);
assert.ok(cautious.total <= 100);
assert.ok(!cautious.inspection.evidence.some(x => /^Qualification readiness adjustment:/i.test(x)));

console.log("apply-next dimension separation tests passed");
