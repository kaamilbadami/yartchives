const assert = require("node:assert/strict");
const R = require("../apply-next-readiness.js");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  preferredProfiles: ["cs"],
  supportedKeywords: ["software", "c", "linux", "testing"],
  cautiousKeywords: ["python", "bash"],
  facts: {
    workAuthorization: "U.S. citizen; no sponsorship needed",
    supportedSkills: ["C", "Linux", "testing"],
    cautiousSkills: ["Python", "Bash"],
  },
  roleFamilies: [{ id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] }],
  preferredStates: ["CT", "MA"],
  relocationAllowed: true,
};

function inspectedJob({ required = [], preferred = [], other = [], citizenship = [], authorization = [] } = {}) {
  return {
    company: "Test",
    title: "Software Engineer Intern",
    profiles: ["cs"],
    states: ["MA"],
    term: "Summer 2027",
    posted_at: "2026-09-16T12:00:00Z",
    link_kind: "direct",
    url: "https://careers-example.icims.com/jobs/1234/job",
    _inspection: {
      provider: "icims",
      status: "inspected",
      posting: { application_status: "available" },
      requirements: {
        skills: { classification: "mixed", required, preferred, unspecified: [], not_required: [] },
        other_eligibility: { classification: other.length ? "required" : "unknown", required: other, preferred: [], unspecified: [], not_required: [] },
        citizenship: { classification: citizenship.length ? "required" : "unknown", required: citizenship, preferred: [], unspecified: [], not_required: [] },
        work_authorization: { classification: authorization.length ? "required" : "unknown", required: authorization, preferred: [], unspecified: [], not_required: [] },
      },
    },
  };
}

const cPlusPlus = inspectedJob({ required: [
  { statement: "Experience using Linux", technologies: ["Linux"] },
  { statement: "C++ software development experience", technologies: ["C++"] },
] });
const analysis = R.analyzeRequiredSkills(cPlusPlus, profile);
assert.deepEqual(analysis.supported, ["linux"]);
assert.deepEqual(analysis.unsupported, ["c++"]);
assert.equal(analysis.supported.includes("c++"), false, "C must not satisfy C++");
assert.equal(R.scoreReadiness(cPlusPlus, profile).delta, -10);
assert.match(R.scoreReadiness(cPlusPlus, profile).details.join(" "), /Required gap: c\+\+/i);

const cautiousPython = inspectedJob({ required: [
  { statement: "Python experience required", technologies: ["Python"] },
] });
assert.equal(R.scoreReadiness(cautiousPython, profile).delta, -4);
assert.match(R.scoreReadiness(cautiousPython, profile).details.join(" "), /cautiously supported/i);

const preferredCPlusPlus = inspectedJob({ preferred: [
  { statement: "C++ preferred", technologies: ["C++"] },
] });
assert.equal(R.scoreReadiness(preferredCPlusPlus, profile).delta, 0);

const clearance = inspectedJob({ other: [
  { statement: "Active and existing security clearance required after day 1", requirement_state: "required", negated: false },
] });
const clearanceReadiness = R.scoreReadiness(clearance, profile);
assert.equal(clearanceReadiness.delta, -5);
assert.match(clearanceReadiness.details.join(" "), /Unverified requirement: active security clearance/i);

const noClearanceProfile = JSON.parse(JSON.stringify(profile));
noClearanceProfile.facts.securityClearance = "None; no active clearance";
const clearanceConflict = R.scoreJob(clearance, noClearanceProfile, new Date("2026-09-16T16:00:00Z"));
assert.equal(clearanceConflict.excluded, true);
assert.match(clearanceConflict.readiness.details.join(" "), /requires an active security clearance/i);

const activeClearanceProfile = JSON.parse(JSON.stringify(profile));
activeClearanceProfile.facts.securityClearance = "Active Secret clearance";
assert.equal(R.scoreReadiness(clearance, activeClearanceProfile).delta, 0);

const sponsorshipJob = inspectedJob({ authorization: [
  { statement: "Applicants must be authorized to work in the U.S.; the company does not sponsor.", requirement_state: "required", negated: false },
] });
const needsSponsorship = JSON.parse(JSON.stringify(profile));
needsSponsorship.facts.workAuthorization = "Requires visa sponsorship";
const sponsorshipConflict = R.scoreJob(sponsorshipJob, needsSponsorship, new Date("2026-09-16T16:00:00Z"));
assert.equal(sponsorshipConflict.excluded, true);

const metadataOnly = {
  company: "Metadata",
  title: "Software Engineer Intern",
  profiles: ["cs"],
  states: ["CT"],
  term: "Summer 2027",
  posted_at: "2026-09-16T12:00:00Z",
  link_kind: "direct",
  url: "https://example.com/metadata",
};
assert.equal(R.scoreReadiness(metadataOnly, profile).delta, 0);

const rtxLike = inspectedJob({
  required: [
    { statement: "Experience using Linux", technologies: ["Linux"] },
    { statement: "C++ software development experience", technologies: ["C++"] },
  ],
  other: [{ statement: "Active and existing security clearance required after day 1", requirement_state: "required", negated: false }],
});
rtxLike.company = "Fresh gap";
rtxLike.posted_at = "2026-09-16T14:00:00Z";
const supportedOlder = inspectedJob({ required: [
  { statement: "Experience using Linux and C", technologies: ["Linux", "C"] },
] });
supportedOlder.company = "Older supported";
supportedOlder.posted_at = "2026-09-12T14:00:00Z";
const ranked = R.rankJobs([rtxLike, supportedOlder], profile, new Date("2026-09-16T16:00:00Z"));
assert.equal(ranked[0].job.company, "Older supported");
assert.ok(ranked[0].total > ranked[1].total);
assert.match(ranked[1].inspection.label, /required gaps/i);
assert.match(ranked[1].inspection.evidence.join(" "), /Required gap: c\+\+/i);

const scored = R.scoreJob(cPlusPlus, profile, new Date("2026-09-16T16:00:00Z"));
const componentTotal = Object.values(scored.components).reduce((sum, part) => sum + part.score, 0);
assert.equal(scored.total, Math.max(0, Math.min(100, componentTotal + scored.readiness.delta)));

const greenhouseEvidence = JSON.parse(JSON.stringify(cPlusPlus));
greenhouseEvidence.url = "https://job-boards.greenhouse.io/example/jobs/8171041";
greenhouseEvidence._inspection.provider = "greenhouse";
greenhouseEvidence._inspection.provenance = { provider: "greenhouse", interface: "greenhouse_job_board_api" };
const greenhouseScore = R.scoreJob(greenhouseEvidence, profile, new Date("2026-09-16T16:00:00Z"));
assert.equal(greenhouseScore.readiness.delta, scored.readiness.delta);
assert.equal(greenhouseScore.components.fit.score, scored.components.fit.score);
assert.match(greenhouseScore.inspection.label, /^Posting inspected/);
assert.match(greenhouseScore.inspection.evidence.join(" "), /Required gap: c\+\+/i);

console.log("apply-next readiness tests passed");
