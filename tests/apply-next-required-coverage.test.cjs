const assert = require("node:assert/strict");
const D = require("../apply-next-dimensions.js");

const now = new Date("2026-09-17T12:00:00Z");
const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship"],
  excludeGraduateOnly: true,
  supportedKeywords: ["java", "git", "linux"],
  cautiousKeywords: ["python"],
  facts: {
    degree: "Bachelor of Science",
    major: "Computer Science",
    supportedSkills: ["Java", "Git", "Linux"],
    cautiousSkills: ["Python"],
  },
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
  preferredStates: ["MD"],
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
        unspecified: [],
        not_required: [],
      },
      education: {
        required: [{ statement: "Currently pursuing a Bachelor's degree." }],
        preferred: [], unspecified: [], not_required: [],
      },
      major_fields: {
        required: [], preferred: [], unspecified: [], not_required: [],
      },
    },
  };
}

function job(inspectionValue) {
  return {
    id: "fit-calibration",
    company: "ExampleCo",
    title: "Software Engineer Intern",
    profiles: ["cs"],
    states: ["MD"],
    location: "Maryland",
    term: "Summer 2027",
    posted_at: "2026-09-16T12:00:00Z",
    link_kind: "direct",
    url: "https://example.com/job",
    _inspection: inspectionValue,
  };
}

const aeroLike = D.scoreJob(job(inspection([
  ["Strong foundational knowledge in programming languages such as Python, C++, or Java.", ["Python", "C++", "Java"]],
  ["Experience with Git.", ["Git"]],
], [
  ["Experience with Linux.", ["Linux"]],
  ["Experience with Python is preferred.", ["Python"]],
])), profile, now);

assert.equal(aeroLike.components.fit.score, 35);
assert.match(aeroLike.components.fit.detail, /Required coverage: All known required evidence is satisfied/i);
assert.match(aeroLike.components.fit.detail, /Exact required skills: java, git/i);
assert.match(aeroLike.inspection.label, /Ready on known requirements/i);

const withRequiredGap = D.scoreJob(job(inspection([
  ["Java required.", ["Java"]],
  ["Python required.", ["Python"]],
])), profile, now);
assert.doesNotMatch(withRequiredGap.components.fit.detail, /Required coverage:/i);
assert.match(withRequiredGap.components.fit.detail, /cautiously evidenced: python/i);
assert.match(withRequiredGap.inspection.label, /Some required gaps/i);
assert.ok(withRequiredGap.components.fit.score < aeroLike.components.fit.score);

const emptyInspection = D.scoreJob(job({
  status: "inspected",
  posting: { application_status: "available" },
  requirements: {
    skills: { required: [], preferred: [], unspecified: [], not_required: [] },
  },
}), profile, now);
assert.equal(emptyInspection.components.fit.score, 18);
assert.doesNotMatch(emptyInspection.components.fit.detail, /Required coverage:/i);

const metadataOnly = D.scoreJob({ ...job(undefined), _inspection: undefined }, profile, now);
assert.equal(metadataOnly.components.fit.score, 19);

console.log("apply-next required coverage calibration tests passed");
