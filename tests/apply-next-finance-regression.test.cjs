const assert = require("node:assert/strict");
const D = require("../apply-next-dimensions.js");

const now = new Date("2027-01-01T12:00:00Z");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["finance-econ"],
  supportedKeywords: ["finance", "excel", "analytical"],
  cautiousKeywords: [],
  facts: {
    degree: "Bachelor of Science",
    major: "Finance",
    supportedSkills: ["Excel", "Analytical skills"],
    cautiousSkills: [],
    graduation: "May 2029",
  },
  roleFamilies: [{ id: "finance", label: "Finance", priority: 1, keywords: ["finance"] }],
  preferredStates: ["MD"],
  relocationAllowed: true,
  locationMode: "normal",
  baseZips: ["21014"],
  baseLabels: ["Home Base"],
  nearbyMiles: 50,
};

function inspection(required = [], preferred = [], status = "inspected") {
  return {
    status,
    posting: status === "inspected" ? { application_status: "available" } : null,
    requirements: {
      skills: {
        classification: required.length || preferred.length ? "mixed" : "unknown",
        required: required.map(([statement, technologies]) => ({ statement, technologies })),
        preferred: preferred.map(([statement, technologies]) => ({ statement, technologies })),
        unspecified: [],
        not_required: [],
      },
      education: {
        classification: "required",
        required: [{ statement: "Currently pursuing a Bachelor's degree." }],
        preferred: [], unspecified: [], not_required: [],
      },
      graduation: {
        classification: "required",
        required: [{ statement: "Graduating between Dec 2028 and June 2029." }],
        preferred: [], unspecified: [], not_required: [],
      },
    },
  };
}

function job(overrides = {}) {
  return {
    company: "ExampleCo",
    title: "Finance Intern",
    profiles: ["finance-econ"],
    term: "Summer 2027",
    opportunity_type: "internship",
    posted_at: "2026-12-01T12:00:00Z",
    link_kind: "direct",
    url: "https://example.com/job",
    ...overrides,
  };
}

const strongFitLocal = job({
  id: "strong-fit-local",
  company: "Local Strong",
  states: ["MD"],
  url: "https://example.com/1",
  location: "Baltimore, MD",
  _locationAnchorDistances: [{ zip: "21014", distanceMiles: 25 }],
  _inspection: inspection([
    ["Excel and analytical skills required.", ["Excel", "Analytical skills"]],
  ]),
});

const strongFitRemote = job({
  id: "strong-fit-remote",
  company: "Remote Strong",
  states: ["Remote"],
  url: "https://example.com/2",
  location: "Remote",
  _inspection: inspection([
    ["Excel and analytical skills required.", ["Excel", "Analytical skills"]],
  ]),
});

const strongFitRelocation = job({
  id: "strong-fit-relocation",
  company: "Relocation Strong",
  states: ["NY"],
  url: "https://example.com/3",
  location: "New York, NY",
  _locationAnchorDistances: [{ zip: "21014", distanceMiles: 170 }],
  _inspection: inspection([
    ["Excel and analytical skills required.", ["Excel", "Analytical skills"]],
  ]),
});


const pool = [
  strongFitLocal,
  strongFitRemote,
  strongFitRelocation,
];

const ranked = D.rankJobs(pool, profile, now);
const ids = ranked.map(r => r.job.id);

console.log("Ranked IDs:", ids);

assert.ok(
  ranked.findIndex(r => r.job.id === "strong-fit-local") < ranked.findIndex(r => r.job.id === "strong-fit-remote"),
  "A strong plausible local Finance role outranks an otherwise comparable remote role"
);

assert.ok(
  ranked.findIndex(r => r.job.id === "strong-fit-remote") < ranked.findIndex(r => r.job.id === "strong-fit-relocation"),
  "A remote Finance role outranks an otherwise comparable relocation role (relocation allowed but penalized)"
);

console.log("apply-next finance regression test passed");
