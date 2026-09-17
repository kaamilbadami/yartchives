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

assert.deepEqual(D.SCORE_MAXIMA, {
  fit: 40,
  eligibility: 0,
  freshness: 10,
  roi: 15,
  role: 20,
  location: 15,
  link: 0,
});
assert.equal(Object.values(D.SCORE_MAXIMA).reduce((sum, value) => sum + value, 0), 100);
assert.equal(D.scaleScore(25, 25, 40), 40);
assert.equal(D.scaleScore(10, 10, 20), 20);
assert.equal(D.scaleScore(15, 15, 10), 10);

const metadataOnly = D.scoreJob(job({ _inspection: undefined }), profile, now);
assert.equal(metadataOnly.components.fit.score, 19);
assert.equal(metadataOnly.components.role.score, 20);
assert.equal(metadataOnly.components.location.score, 15);
assert.equal(metadataOnly.components.freshness.score, 10);
assert.equal(metadataOnly.components.eligibility.score, 0);
assert.equal(metadataOnly.components.link.score, 0);
assert.match(metadataOnly.components.fit.detail, /neutral qualification-fit/i);
assert.deepEqual(metadataOnly.scoreMaxima, D.SCORE_MAXIMA);

const supported = D.scoreJob(job({
  _inspection: inspection([["Java required", ["Java"]]]),
}), profile, now);
const unsupported = D.scoreJob(job({
  url: "https://example.com/unsupported",
  _inspection: inspection([["Rust required", ["Rust"]]]),
}), profile, now);
assert.ok(supported.components.fit.score > unsupported.components.fit.score);
assert.doesNotMatch(supported.components.fit.detail, /Career-area overlap|Supported metadata matches/i);
assert.ok(supported.components.fit.score <= D.SCORE_MAXIMA.fit);

const exactTerm = D.scoreJob(job({ _inspection: inspection() }), profile, now);
const unknownTerm = D.scoreJob(job({ term: null, url: "https://example.com/unknown", _inspection: inspection() }), profile, now);
assert.equal(exactTerm.components.eligibility.score, 0);
assert.equal(unknownTerm.components.eligibility.score, 0);
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
assert.ok(demandRanked[0].components.roi.score <= D.SCORE_MAXIMA.roi);

const direct = D.scoreJob(job({ _inspection: inspection() }), profile, now);
const listing = D.scoreJob(job({ link_kind: "listing", url: "https://example.com/listing", _inspection: inspection() }), profile, now);
assert.equal(direct.components.link.score, 0);
assert.equal(listing.components.link.score, 0);
assert.match(direct.components.link.detail, /provenance only/i);
assert.equal(direct.total, listing.total);
assert.equal(direct.scoringSemantics.link, "provenance only");

const cautious = D.scoreJob(job({
  url: "https://example.com/cautious",
  _inspection: inspection([["Python required", ["Python"]]]),
}), profile, now);
assert.ok(cautious.components.fit.score < supported.components.fit.score);
assert.ok(cautious.total <= 100);
assert.ok(!cautious.inspection.evidence.some(x => /^Qualification readiness adjustment:/i.test(x)));

for (const result of [metadataOnly, supported, unsupported, exactTerm, unknownTerm, direct, listing, cautious]) {
  const weightedTotal = Object.values(result.components).reduce((sum, component) => sum + Number(component.score || 0), 0);
  assert.equal(result.total, weightedTotal);
  assert.ok(result.total >= 0 && result.total <= 100);
}

console.log("apply-next dimension weighting tests passed");
