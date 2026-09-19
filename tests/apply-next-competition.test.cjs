const assert = require("node:assert/strict");
const C = require("../apply-next-competition.js");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software", "testing", "systems", "linux", "java", "c"],
  cautiousKeywords: ["python", "bash"],
  facts: {
    graduation: "May 2028",
    supportedSkills: ["Java", "C", "Linux", "testing"],
    cautiousSkills: ["Python", "Bash"],
  },
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer", "software developer"] },
    { id: "testing", label: "Testing / systems", priority: 1, keywords: ["test engineer", "testing", "systems"] },
  ],
  preferredStates: ["NY", "CT", "MD", "DC"],
  relocationAllowed: true,
};
const now = new Date("2026-09-16T16:00:00Z");

function inspectedSkills(required) {
  return {
    status: "inspected",
    posting: { application_status: "available" },
    requirements: {
      skills: {
        classification: required.length ? "required" : "unknown",
        required: required.map(([statement, technologies]) => ({
          statement,
          technologies,
          requirement_state: "required",
          negated: false,
        })),
        preferred: [], unspecified: [], not_required: [],
      },
    },
  };
}

const neutral = {
  company: "SmallCo",
  title: "Business Operations Intern",
  profiles: ["cs"],
  states: ["CT"],
  location: "Hartford, CT",
  term: "Summer 2027",
  posted_at: "2026-09-15T12:00:00Z",
  link_kind: "direct",
  url: "https://example.com/neutral",
};
assert.equal(C.scoreRoi(neutral, profile).score, 10);
assert.match(C.scoreRoi(neutral, profile).detail, /Neutral application-value baseline/);

const directFresh = { ...neutral, link_kind: "direct", term: "Summer 2027", posted_at: "2026-09-16T12:00:00Z" };
const listingOlder = { ...neutral, link_kind: "listing", term: "Fall 2026", posted_at: "2026-08-01T12:00:00Z" };
assert.equal(C.scoreRoi(directFresh, profile).score, C.scoreRoi(listingOlder, profile).score);
assert.doesNotMatch(C.scoreRoi(directFresh, profile).detail, /fresh posting|direct application|exact target term/i);

const genericNy = {
  ...neutral,
  company: "BigCo",
  title: "Software Engineering Intern",
  location: "New York, NY",
  states: ["NY"],
};
assert.equal(C.isGenericRole(genericNy), true);
assert.equal(C.marketPressure(genericNy).penalty, 2);

const remoteGeneric = { ...genericNy, location: "Remote", states: ["Remote"] };
assert.ok(C.scoreRoi(remoteGeneric, profile).score < C.scoreRoi(neutral, profile).score);

const footprintJobs = Array.from({ length: 8 }, (_, index) => ({
  ...genericNy,
  id: `big-${index}`,
  title: index === 0 ? "Software Engineering Intern" : `Engineering Intern ${index}`,
}));
const context = C.buildCompetitionContext(footprintJobs);
assert.equal(context.employerCounts.bigco, 8);
assert.equal(context.employerRoleCounts["bigco::software engineering"], 8);
const observedDemand = C.scoreRoi(genericNy, profile, context);
assert.equal(observedDemand.competitionPenalty, 0);
assert.equal(observedDemand.demandBonus, 5);
assert.equal(observedDemand.score, 15);
assert.deepEqual(observedDemand.observedDemand, { count: 8, role: "software engineering" });
assert.match(observedDemand.detail, /observed employer demand: 8 current software engineering openings/);
assert.doesNotMatch(observedDemand.detail, /fallback competition heuristic/);
assert.doesNotMatch(observedDemand.detail, /acceptance|probability|odds|chance/i);

const mediumDemandJobs = Array.from({ length: 3 }, (_, index) => ({
  ...genericNy,
  id: `medium-${index}`,
  company: "MediumCo",
  title: `Software Engineering Intern ${index}`,
}));
const mediumContext = C.buildCompetitionContext(mediumDemandJobs);
const mediumDemand = C.scoreRoi(mediumDemandJobs[0], profile, mediumContext);
assert.equal(mediumDemand.demandBonus, 3);
assert.equal(mediumDemand.score, 13);

const fallbackContext = {
  employerCounts: { bigco: 8 },
  employerRoleCounts: {},
};
const fallbackPressure = C.scoreRoi(genericNy, profile, fallbackContext);
assert.equal(fallbackPressure.competitionPenalty, 4);
assert.equal(fallbackPressure.demandBonus, 0);
assert.equal(fallbackPressure.score, 6);
assert.match(fallbackPressure.detail, /fallback competition heuristic/);
assert.doesNotMatch(fallbackPressure.detail, /hiring footprint/);

const smallFootprintPressure = C.scoreRoi(genericNy, profile, {
  employerCounts: { bigco: 1 },
  employerRoleCounts: {},
});
assert.equal(
  fallbackPressure.score,
  smallFootprintPressure.score,
  "employer-wide listing count is not evidence of applicant competition"
);

const differentiated = {
  ...neutral,
  company: "FocusedCo",
  title: "Systems Test Engineer Intern",
  location: "New York, NY",
  states: ["NY"],
  _inspection: inspectedSkills([
    ["Linux experience required.", ["Linux"]],
    ["Software testing experience required.", ["testing"]],
  ]),
};
const differentiatedRoi = C.scoreRoi(differentiated, profile);
const differentProfileRoi = C.scoreRoi(differentiated, {
  ...profile,
  supportedKeywords: [],
  cautiousKeywords: [],
  facts: { graduation: "May 2028", supportedSkills: [], cautiousSkills: [] },
});
assert.equal(C.isSpecializedRole(differentiated), true);
assert.equal(differentiatedRoi.differentiationBonus, 0);
assert.equal(differentiatedRoi.score, 8);
assert.equal(differentProfileRoi.score, differentiatedRoi.score);
assert.equal(differentProfileRoi.detail, differentiatedRoi.detail);
assert.doesNotMatch(differentiatedRoi.detail, /required-skill differentiation|specialized role aligns/i);

const genericPool = footprintJobs.map((job, index) => ({
  ...job,
  posted_at: "2026-09-16T12:00:00Z",
  term: "Summer 2027",
  profiles: ["cs"],
  states: ["NY"],
  location: "New York, NY",
  link_kind: "direct",
  url: `https://example.com/big-${index}`,
}));
const specializedOlder = {
  ...differentiated,
  posted_at: "2026-09-12T12:00:00Z",
  link_kind: "direct",
  url: "https://example.com/focused",
};
const ranked = C.rankJobs([...genericPool, specializedOlder], profile, now);
const rankedBigCo = ranked.find(result => result.job.company === "BigCo");
assert.equal(rankedBigCo.components.roi.demandBonus, 5);
assert.match(rankedBigCo.components.roi.detail, /observed employer demand/);

const score = C.scoreJob(differentiated, profile, now, C.buildCompetitionContext([differentiated]));
assert.equal(score.components.roi.score, 8);
assert.equal(score.competition.penalty, 2);
assert.equal(score.competition.differentiationBonus, 0);
assert.equal(score.competition.demandBonus, 0);
assert.equal(score.competition.observedDemand, null);

const queuedWorkday = {
  ...neutral,
  company: "QueuedCo",
  url: "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Role_REQ-9",
  _inspection: {
    status: "queued",
    retrieval_confidence: "none",
    posting: null,
    requirements: {},
    queue: {
      state: "queued",
      rank: 12,
      priority_score: 140,
      reasons: ["Summer 2027", "internship/co-op", "undergrad-friendly", "posted within 7 days"],
    },
  },
};
const queuedScore = C.scoreJob(queuedWorkday, profile, now, C.buildCompetitionContext([queuedWorkday]));
assert.equal(queuedScore.inspection.state, "metadata-only");
assert.match(queuedScore.inspection.evidence[0], /Queued for bounded Workday inspection/);
assert.match(queuedScore.inspection.evidence[0], /public priority #12/);
assert.match(queuedScore.inspection.evidence[0], /Summer 2027/);

const failedWorkday = {
  ...queuedWorkday,
  company: "RetryCo",
  _inspection: {
    status: "failed",
    retrieval_confidence: "none",
    posting: null,
    requirements: {},
    queue: { state: "retry_cooldown", priority_score: 140, reasons: ["Summer 2027"] },
  },
};
const failedScore = C.scoreJob(failedWorkday, profile, now, C.buildCompetitionContext([failedWorkday]));
assert.match(failedScore.inspection.evidence[0], /retry is cooling down/i);

const queuedIcims = {
  ...neutral,
  company: "QueuedIcims",
  url: "https://careers-example.icims.com/jobs/74848/job?mobile=true&ref=Simplify",
  _inspection: {
    provider: "icims",
    status: "queued",
    retrieval_confidence: "none",
    posting: null,
    requirements: {},
    queue: {
      provider: "icims",
      state: "queued",
      rank: 4,
      priority_score: 140,
      reasons: ["Summer 2027", "internship/co-op", "undergrad-friendly"],
    },
  },
};
const queuedIcimsScore = C.scoreJob(queuedIcims, profile, now, C.buildCompetitionContext([queuedIcims]));
assert.equal(queuedIcimsScore.inspection.label, "Queued for inspection");
assert.match(queuedIcimsScore.inspection.evidence[0], /Queued for bounded iCIMS inspection/);
assert.match(queuedIcimsScore.inspection.evidence[0], /public priority #4/);

const unsupportedIcims = {
  ...neutral,
  company: "OddIcims",
  url: "https://careers-example.icims.com/jobs/search",
  _inspection: {
    provider: "icims",
    status: "unsupported_url",
    retrieval_confidence: "none",
    posting: null,
    requirements: {},
    queue: { provider: "icims", state: "unsupported_url", reasons: [] },
  },
};
const unsupportedIcimsScore = C.scoreJob(unsupportedIcims, profile, now, C.buildCompetitionContext([unsupportedIcims]));
assert.equal(unsupportedIcimsScore.inspection.label, "Unsupported iCIMS URL");
assert.match(unsupportedIcimsScore.inspection.evidence[0], /not recognized/i);

const queuedGreenhouse = {
  ...neutral,
  company: "QueuedGreenhouse",
  url: "https://job-boards.greenhouse.io/doordashusa/jobs/8171041?gh_src=feed",
  _inspection: {
    provider: "greenhouse",
    status: "queued",
    retrieval_confidence: "none",
    posting: null,
    requirements: {},
    queue: {
      provider: "greenhouse",
      state: "queued",
      rank: 3,
      priority_score: 140,
      reasons: ["Summer 2027", "internship/co-op", "undergrad-friendly"],
    },
  },
};
const queuedGreenhouseScore = C.scoreJob(
  queuedGreenhouse,
  profile,
  now,
  C.buildCompetitionContext([queuedGreenhouse])
);
assert.equal(C.isGreenhouseUrl(queuedGreenhouse), true);
assert.equal(C.inspectionProvider(queuedGreenhouse), "greenhouse");
assert.equal(queuedGreenhouseScore.inspection.label, "Queued for inspection");
assert.match(queuedGreenhouseScore.inspection.evidence[0], /Queued for bounded Greenhouse inspection/);
assert.match(queuedGreenhouseScore.inspection.evidence[0], /public priority #3/);

const unsupportedGreenhouse = {
  ...neutral,
  company: "OddGreenhouse",
  url: "https://job-boards.greenhouse.io/doordashusa",
  _inspection: {
    provider: "greenhouse",
    status: "unsupported_url",
    retrieval_confidence: "none",
    posting: null,
    requirements: {},
    queue: { provider: "greenhouse", state: "unsupported_url", reasons: [] },
  },
};
const unsupportedGreenhouseScore = C.scoreJob(
  unsupportedGreenhouse,
  profile,
  now,
  C.buildCompetitionContext([unsupportedGreenhouse])
);
assert.equal(unsupportedGreenhouseScore.inspection.label, "Unsupported Greenhouse URL");
assert.match(unsupportedGreenhouseScore.inspection.evidence[0], /not recognized/i);

const unsupportedWorkday = {
  ...neutral,
  company: "OddWorkday",
  url: "https://tenant.wd5.myworkdayjobs.com/private_shape/job/CT/Role_REQ-X",
};
const unsupportedScore = C.scoreJob(unsupportedWorkday, profile, now, C.buildCompetitionContext([unsupportedWorkday]));
assert.match(unsupportedScore.inspection.evidence[0], /not currently recognized/i);

const nonWorkday = C.scoreJob(neutral, profile, now, C.buildCompetitionContext([neutral]));
assert.equal(nonWorkday.inspection.state, "metadata-only");
assert.deepEqual(nonWorkday.inspection.evidence, []);

console.log("apply-next competition tests passed");
