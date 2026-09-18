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
  facts: {
    degree: "Bachelor of Science",
    major: "Computer Science",
    supportedSkills: ["Java", "systems"],
    cautiousSkills: ["Python"],
  },
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
  roi: 30,
  role: 0,
  location: 20,
  link: 0,
});
assert.deepEqual(D.APPLICATION_VALUE_PARTS, { role: 15, market: 15 });
assert.equal(Object.values(D.SCORE_MAXIMA).reduce((sum, value) => sum + value, 0), 100);
assert.equal(D.LEGACY_MAXIMA, undefined);
assert.equal(D.scaleScore, undefined);

const metadataOnly = D.scoreJob(job({ _inspection: undefined }), profile, now);
assert.equal(metadataOnly.components.fit.score, 19);
assert.equal(metadataOnly.components.role, undefined);
assert.equal(metadataOnly.components.roi.score, 23);
assert.equal(metadataOnly.applicationValue.role.score, 15);
assert.equal(metadataOnly.applicationValue.market.score, 8);
assert.equal(metadataOnly.components.location.score, 20);
assert.equal(metadataOnly.components.freshness.score, 10);
assert.equal(metadataOnly.components.eligibility.score, 0);
assert.equal(metadataOnly.components.link.score, 0);
assert.match(metadataOnly.components.fit.detail, /neutral qualification-fit/i);
assert.match(metadataOnly.components.roi.detail, /Role value 15\/15/i);
assert.match(metadataOnly.components.roi.detail, /Market opportunity 8\/15/i);
assert.deepEqual(metadataOnly.scoreMaxima, D.SCORE_MAXIMA);

const supported = D.scoreJob(job({
  _inspection: inspection([["Java required", ["Java"]]]),
}), profile, now);
const unsupported = D.scoreJob(job({
  url: "https://example.com/unsupported",
  _inspection: inspection([["Kubernetes required", ["Kubernetes"]]]),
}), profile, now);
assert.ok(supported.components.fit.score > unsupported.components.fit.score);
assert.match(supported.components.fit.detail, /Exact required skills: java/i);
assert.match(unsupported.components.fit.detail, /Unsupported hard required skills: kubernetes/i);
assert.ok(supported.components.fit.score <= D.SCORE_MAXIMA.fit);
assert.match(supported.inspection.label, /Ready on known requirements/i);
assert.match(unsupported.inspection.label, /Some required gaps/i);

const adjacent = D.scoreJob(job({
  url: "https://example.com/adjacent",
  _inspection: inspection([["Experience with C# required", ["C#"]]]),
}), profile, now);
assert.ok(adjacent.components.fit.score > unsupported.components.fit.score);
assert.ok(adjacent.components.fit.score < supported.components.fit.score);
assert.match(adjacent.components.fit.detail, /Transferable capability: java supports c#/i);
assert.match(adjacent.inspection.label, /Ready on known requirements/i);

const learnable = D.scoreJob(job({
  url: "https://example.com/learnable",
  _inspection: inspection([["Familiarity or interest in React is expected", ["React"]]]),
}), profile, now);
assert.equal(learnable.components.fit.score, 18);
assert.match(learnable.components.fit.detail, /Learnable\/low-threshold stack gaps: react/i);
assert.doesNotMatch(learnable.components.fit.detail, /Unsupported hard required skills/i);
assert.match(learnable.inspection.label, /Ready on known requirements/i);

const major = D.scoreJob(job({
  url: "https://example.com/major",
  _inspection: inspection([
    ["Docker required", ["Docker"]],
    ["Kubernetes required", ["Kubernetes"]],
  ]),
}), profile, now);
assert.match(major.inspection.label, /Major required gaps/i);

const domainOnly = D.scoreJob(job({
  url: "https://example.com/domain",
  _inspection: inspection([["Experience with data structures, algorithms, and software design principles.", []]]),
}), profile, now);
assert.equal(domainOnly.components.fit.score, 18);
assert.match(domainOnly.inspection.label, /Ready on known requirements/i);
assert.doesNotMatch(domainOnly.components.fit.detail, /Unverified required domain experience/i);
assert.ok(!domainOnly.inspection.evidence.some(x => /^Unverified required domain experience:/i.test(String(x))));

const aeroLike = D.scoreJob(job({
  url: "https://example.com/aero",
  _inspection: inspection([
    ["Strong foundational knowledge in programming languages such as Python, C++, or Java.", ["Python", "C++", "Java"]],
    ["Experience with data structures, algorithms, and software design principles.", []],
  ]),
}), profile, now);
assert.match(aeroLike.components.fit.detail, /Exact required skills: java/i);
assert.doesNotMatch(aeroLike.components.fit.detail, /Transferable capability: java supports c\+\+/i);
assert.doesNotMatch(aeroLike.components.fit.detail, /cautiously evidenced: python/i);
assert.match(aeroLike.inspection.label, /Ready on known requirements/i);

const conjunctiveLanguages = D.scoreJob(job({
  url: "https://example.com/conjunctive",
  _inspection: inspection([
    ["Strong foundational knowledge in Python, C++, and Java.", ["Python", "C++", "Java"]],
  ]),
}), profile, now);
assert.match(conjunctiveLanguages.components.fit.detail, /Exact required skills: java/i);
assert.match(conjunctiveLanguages.components.fit.detail, /cautiously evidenced: python/i);
assert.match(conjunctiveLanguages.inspection.label, /Some required gaps/i);

const gradIntern = D.scoreJob(job({
  title: "Grad Intern – Software Engineer – Technology, AI & Data (Summer 2027)",
  url: "https://example.com/grad",
  _inspection: inspection(),
}), profile, now);
assert.equal(D.explicitGraduateOnlyTitle(gradIntern.job), true);
assert.equal(gradIntern.excluded, true);
assert.match(gradIntern.reasons[0], /Graduate-only opportunity/i);

const academicInspection = inspection([], [["Proficient in Java preferred.", ["Java"]]]);
academicInspection.requirements.education = {
  required: [{ statement: "Currently enrolled in a full-time Bachelor's Degree program." }],
  preferred: [], unspecified: [], not_required: [],
};
academicInspection.requirements.major_fields = {
  required: [],
  preferred: [{ statement: "Degree concentration in Information Technology, Computer Science, Engineering, Business, or related field." }],
  unspecified: [], not_required: [],
};
const academicMatch = D.scoreJob(job({
  company: "AcademicMatch",
  url: "https://example.com/academic",
  _inspection: academicInspection,
}), profile, now);
assert.equal(academicMatch.components.fit.score, 28);
assert.match(academicMatch.components.fit.detail, /Academic match/i);
assert.match(academicMatch.components.fit.detail, /Computer Science matches a preferred major/i);
assert.match(academicMatch.components.fit.detail, /Exact preferred skills: java/i);

const wexLikeInspection = inspection([
  ["Academic or project experience with React, C#/.NET, and SQL.", ["React", "C#", ".NET", "SQL"]],
]);
wexLikeInspection.requirements.education = {
  required: [{ statement: "Currently pursuing a Bachelor's degree." }],
  preferred: [], unspecified: [], not_required: [],
};
wexLikeInspection.requirements.major_fields = {
  required: [{ statement: "Bachelor's degree in Computer Science, Software Engineering, or related field." }],
  preferred: [], unspecified: [], not_required: [],
};
const wexLike = D.scoreJob(job({
  company: "WEX-like",
  url: "https://example.com/wex-like",
  _inspection: wexLikeInspection,
}), profile, now);
assert.ok(wexLike.components.fit.score >= 25);
assert.match(wexLike.components.fit.detail, /Transferable capability: java supports c#/i);
assert.doesNotMatch(wexLike.components.fit.detail, /Learnable\/low-threshold stack gaps:/i);
assert.doesNotMatch(wexLike.components.fit.detail, /Unsupported hard required skills/i);
assert.match(wexLike.inspection.label, /Ready on known requirements/i);

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
assert.equal(demandRanked[0].components.role, undefined);
assert.match(demandRanked[0].components.roi.detail, /Role value 15\/15/i);
assert.match(demandRanked[0].components.roi.detail, /Market opportunity/i);
assert.match(demandRanked[0].components.roi.detail, /observed employer demand/i);
assert.doesNotMatch(demandRanked[0].components.roi.detail, /required-skill differentiation|specialized role aligns/i);
assert.equal(demandRanked[0].competition.differentiationBonus, 0);
assert.equal(demandRanked[0].applicationValue.role.score, 15);
assert.ok(demandRanked[0].applicationValue.market.score <= 15);
assert.ok(demandRanked[0].components.roi.score <= D.SCORE_MAXIMA.roi);

const lowerRoleProfile = {
  ...profile,
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 0.5, keywords: ["software engineer"] }],
};
const lowerRole = D.scoreJob(job({ url: "https://example.com/lower-role", _inspection: inspection() }), lowerRoleProfile, now);
assert.equal(lowerRole.applicationValue.market.score, metadataOnly.applicationValue.market.score);
assert.ok(lowerRole.applicationValue.role.score < metadataOnly.applicationValue.role.score);
assert.ok(lowerRole.components.roi.score < metadataOnly.components.roi.score);

const direct = D.scoreJob(job({ _inspection: inspection() }), profile, now);
const listing = D.scoreJob(job({ link_kind: "listing", url: "https://example.com/listing", _inspection: inspection() }), profile, now);
assert.equal(direct.components.link.score, 0);
assert.equal(listing.components.link.score, 0);
assert.match(direct.components.link.detail, /provenance only/i);
assert.equal(direct.total, listing.total);
assert.equal(direct.scoringSemantics.link, "provenance only");
assert.match(direct.scoringSemantics.fit, /screening evidence plus transferable capability/i);
assert.match(direct.scoringSemantics.applicationValue, /role preference plus market\/opportunity evidence/i);
assert.equal(direct.scoringSemantics.role, undefined);

const cautious = D.scoreJob(job({
  url: "https://example.com/cautious",
  _inspection: inspection([["Python required", ["Python"]]]),
}), profile, now);
assert.ok(cautious.components.fit.score < supported.components.fit.score);
assert.match(cautious.components.fit.detail, /cautiously evidenced: python/i);
assert.ok(cautious.total <= 100);
assert.ok(!cautious.inspection.evidence.some(x => /^Qualification readiness adjustment:/i.test(String(x))));
assert.match(cautious.inspection.label, /Some required gaps/i);

for (const result of [metadataOnly, supported, unsupported, adjacent, learnable, major, domainOnly, aeroLike, conjunctiveLanguages, academicMatch, wexLike, exactTerm, unknownTerm, direct, listing, cautious, lowerRole]) {
  const weightedTotal = Object.values(result.components).reduce((sum, component) => sum + Number(component.score || 0), 0);
  assert.equal(result.total, weightedTotal);
  assert.ok(result.total >= 0 && result.total <= 100);
  assert.equal(result.components.role, undefined);
}

console.log("apply-next evidence-based dimension tests passed");