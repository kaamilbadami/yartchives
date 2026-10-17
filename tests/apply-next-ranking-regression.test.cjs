const assert = require("node:assert/strict");
const D = require("../apply-next-dimensions.js");
const UI = require("../apply-next-ui.js");

const now = new Date("2026-09-17T12:00:00Z");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software", "java", "python", "git", "linux", "sql"],
  cautiousKeywords: ["c++", "c#"],
  facts: {
    degree: "Bachelor of Science",
    major: "Computer Science",
    supportedSkills: ["Java", "Python", "Git", "Linux", "SQL"],
    cautiousSkills: ["C++", "C#"],
    graduation: "May 2028",
  },
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
  preferredStates: ["MD", "VA", "DC"],
  relocationAllowed: true,
  locationMode: "normal",
  baseZips: ["20740"],
  baseLabels: ["School"],
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
        required: [{ statement: "Graduating between Dec 2027 and June 2028." }],
        preferred: [], unspecified: [], not_required: [],
      },
    },
  };
}

function job(overrides = {}) {
  return {
    company: "ExampleCo",
    title: "Software Engineer Intern",
    profiles: ["cs"],
    term: "Summer 2027",
    opportunity_type: "internship",
    posted_at: "2026-09-16T12:00:00Z",
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
  location: "College Park, MD",
  _locationAnchorDistances: [{ zip: "20740", distanceMiles: 5 }],
  _inspection: inspection([
    ["Java and Python experience required.", ["Java", "Python"]],
    ["Git and Linux experience required.", ["Git", "Linux"]],
  ]),
});

const strongFitRemote = job({
  id: "strong-fit-remote",
  company: "Remote Strong",
  states: ["Remote"],
  url: "https://example.com/2",
  location: "Remote",
  _inspection: inspection([
    ["Java and Python experience required.", ["Java", "Python"]],
    ["Git and Linux experience required.", ["Git", "Linux"]],
  ]),
});

const learnableGapsLocal = job({
  id: "learnable-local",
  company: "Local Learnable",
  states: ["MD"],
  url: "https://example.com/3",
  location: "College Park, MD",
  _locationAnchorDistances: [{ zip: "20740", distanceMiles: 5 }],
  _inspection: inspection([
    ["Java experience required.", ["Java"]],
    ["React and Node.js familiarity expected.", ["React", "Node.js"]],
  ]),
});

const requiredGapsLocal = job({
  id: "required-gaps-local",
  company: "Local Required Gaps",
  states: ["MD"],
  url: "https://example.com/4",
  location: "College Park, MD",
  _locationAnchorDistances: [{ zip: "20740", distanceMiles: 5 }],
  _inspection: inspection([
    ["Kubernetes and Docker experience required.", ["Kubernetes", "Docker"]],
    ["Rust experience required.", ["Rust"]],
  ]),
});

const metadataOnlyLocal = job({
  id: "metadata-local",
  company: "Local Metadata",
  states: ["MD"],
  url: "https://example.com/5",
  location: "College Park, MD",
  _locationAnchorDistances: [{ zip: "20740", distanceMiles: 5 }],
  _inspection: { status: "queued", posting: null, requirements: {} },
});

const strongFitRelocation = job({
  id: "strong-fit-relocation",
  company: "Relocation Strong",
  states: ["CA"],
  url: "https://example.com/6",
  location: "San Francisco, CA",
  _locationAnchorDistances: [{ zip: "20740", distanceMiles: 2800 }],
  _inspection: inspection([
    ["Java and Python experience required.", ["Java", "Python"]],
    ["Git and Linux experience required.", ["Git", "Linux"]],
  ]),
});

// For optimization/distance tests, jobs that sit just outside the boundary
const baseJobs = Array.from({length: 15}, (_, i) => {
  const isMultiLocation = i % 2 === 0;
  return job({
    id: `filler-${i}`,
    company: `Filler ${i}`,
    states: isMultiLocation ? ["NY", "NJ", "MD"] : ["NY"],
    url: `https://example.com/filler-${i}`,
    location: isMultiLocation ? "Multiple locations" : "New York, NY",
    // Base jobs intentionally do not have `_locationAnchorDistances` pre-populated so they
    // rely on distance selection
    _inspection: inspection([
      ["Java experience required.", ["Java"]],
    ]),
    posted_at: new Date(now.getTime() - i * 3600000).toISOString(), // Spread out fresh times
  });
});

const excludedJob = job({
  id: "graduate-only",
  title: "Software Engineer Intern (Graduate Only)",
  company: "ExcludedCo",
  states: ["MD"],
  url: "https://example.com/excluded",
  location: "College Park, MD",
  _locationAnchorDistances: [{ zip: "20740", distanceMiles: 5 }],
  _inspection: inspection([
    ["Java and Python experience required.", ["Java", "Python"]],
  ]),
});

const pool = [
  strongFitLocal,
  strongFitRemote,
  learnableGapsLocal,
  requiredGapsLocal,
  metadataOnlyLocal,
  strongFitRelocation,
  excludedJob,
  ...baseJobs
];

const ranked = D.rankJobs(pool, profile, now);
const metadataOnlyLocalScore = D.scoreJob(metadataOnlyLocal, profile, now);
const ids = ranked.map(r => r.job.id);

console.log("Ranked IDs:", ids);

// Assert directional expectations rather than brittle exact absolute scores
assert.ok(
  ranked.findIndex(r => r.job.id === "strong-fit-local") < ranked.findIndex(r => r.job.id === "strong-fit-remote"),
  "A strong local fit (score 87) should rank higher than an identical remote fit (score 83) because base distances score 20 whereas remote scores 18"
);

assert.ok(
  ranked.findIndex(r => r.job.id === "strong-fit-local") < ranked.findIndex(r => r.job.id === "learnable-local"),
  "A strong fit with all exact required matches should rank higher than a learnable gap"
);

assert.ok(
  ranked.findIndex(r => r.job.id === "learnable-local") < ranked.findIndex(r => r.job.id === "required-gaps-local"),
  "A learnable gap should rank higher than major required/hard gaps"
);

assert.ok(
  ranked.findIndex(r => r.job.id === "strong-fit-remote") < ranked.findIndex(r => r.job.id === "strong-fit-relocation"),
  "Remote should generally rank higher than major relocation (unless custom anchors prioritize relocation)"
);

const strongFitLocalScore = ranked.find(r => r.job.id === "strong-fit-local");

assert.ok(
  strongFitLocalScore.total > metadataOnlyLocalScore.total,
  "Authoritative inspected fit should rank higher than a metadata-only equivalent"
);

assert.ok(
  !ids.includes("graduate-only"),
  "Graduate-only jobs should be strictly gated/excluded according to profile preferences"
);

// Semantic Equivalence of visible queue optimized vs. exhaustive reference path
// 1. Reference path (exhaustively score all with full distances attached, which we mock here by cloning baseJobs and assigning distances to represent post-enrichment)
const exhaustivePool = pool.map(j => {
  if (j.id.startsWith('filler')) {
    // If we resolved their location, maybe it's 5 miles away for the multi-location ones that hit MD,
    // and far for NY
    const distanceMiles = j.states.includes("MD") ? 5 : 200;
    return { ...j, _locationAnchorDistances: [{ zip: "20740", distanceMiles }] };
  }
  return j;
});
const referenceRanked = D.rankJobs(exhaustivePool, profile, now);
const referenceRecommendedQueue = UI.visibleQueueResults(referenceRanked, "recommended", now).map(r => r.job.id);
const referenceFreshQueue = UI.visibleQueueResults(referenceRanked, "fresh", now).map(r => r.job.id);

// 2. Optimized path (UI flow)
const preliminaryRanked = D.rankJobs(pool, profile, now); // Without exhaustive _locationAnchorDistances for fillers
const candidatesForEnrichment = UI.distanceEnrichmentCandidates(preliminaryRanked, now);
const candidateIds = new Set(candidatesForEnrichment.map(j => j.id));

const optimizedPool = pool.map(j => {
  if (candidateIds.has(j.id) && j.id.startsWith('filler')) {
    const distanceMiles = j.states.includes("MD") ? 5 : 200;
    return { ...j, _locationAnchorDistances: [{ zip: "20740", distanceMiles }] };
  }
  return j;
});
const optimizedRanked = D.rankJobs(optimizedPool, profile, now);
const optimizedRecommendedQueue = UI.visibleQueueResults(optimizedRanked, "recommended", now).map(r => r.job.id);
const optimizedFreshQueue = UI.visibleQueueResults(optimizedRanked, "fresh", now).map(r => r.job.id);

assert.deepEqual(optimizedRecommendedQueue, referenceRecommendedQueue, "Optimized recommended queue must be identical to exhaustive reference queue (no skipped legitimate jobs)");
assert.deepEqual(optimizedFreshQueue, referenceFreshQueue, "Optimized fresh queue must be identical to exhaustive reference queue (no skipped legitimate jobs)");

// To ensure ties or profile changes still rank identically
const profileChange = { ...profile, facts: { ...profile.facts, degree: "Master of Science" } };

// Profile change on Reference Path
const referenceRankedChange = D.rankJobs(exhaustivePool, profileChange, now);

// Profile change on Optimized Path
// We must redo preliminary ranking and distance enrichment candidates for the new profile,
// mimicking real application logic, to properly evaluate equivalence.
const preliminaryRankedChange = D.rankJobs(pool, profileChange, now);
const candidatesForEnrichmentChange = UI.distanceEnrichmentCandidates(preliminaryRankedChange, now);
const candidateIdsChange = new Set(candidatesForEnrichmentChange.map(j => j.id));

const optimizedPoolChange = pool.map(j => {
  if (candidateIdsChange.has(j.id) && j.id.startsWith('filler')) {
    const distanceMiles = j.states.includes("MD") ? 5 : 200;
    return { ...j, _locationAnchorDistances: [{ zip: "20740", distanceMiles }] };
  }
  return j;
});
const optimizedRankedChange = D.rankJobs(optimizedPoolChange, profileChange, now);

assert.deepEqual(
  UI.visibleQueueResults(optimizedRankedChange, "recommended", now).map(r => r.job.id),
  UI.visibleQueueResults(referenceRankedChange, "recommended", now).map(r => r.job.id),
  "Optimized path should survive profile changes identically"
);

console.log("apply-next ranking regression test passed");
