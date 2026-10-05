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

function inspectedJob({ required = [], preferred = [], other = [], citizenship = [], authorization = [], studentRequired = [], studentPreferred = [] } = {}) {
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
        student_status: {
          classification: studentRequired.length ? "required" : (studentPreferred.length ? "preferred" : "unknown"),
          required: studentRequired,
          preferred: studentPreferred,
          unspecified: [],
          not_required: [],
        },
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
const preparedCPlusPlus = R.analyzeRequiredSkills(cPlusPlus, profile);
assert.deepEqual(
  R.scoreFit(cPlusPlus, profile, preparedCPlusPlus),
  R.scoreFit(cPlusPlus, profile),
  "Prepared required-skill analysis must preserve fit scoring semantics"
);
assert.deepEqual(
  R.scoreReadiness(cPlusPlus, profile, preparedCPlusPlus),
  R.scoreReadiness(cPlusPlus, profile),
  "Prepared required-skill analysis must preserve readiness semantics"
);

const cautiousPython = inspectedJob({ required: [
  { statement: "Python experience required", technologies: ["Python"] },
] });
assert.equal(R.scoreReadiness(cautiousPython, profile).delta, -4);
assert.match(R.scoreReadiness(cautiousPython, profile).details.join(" "), /cautiously supported/i);

const analyticsStack = inspectedJob({ required: [
  {
    statement: "Foundational knowledge of Python, SQL/PLSQL, Tableau, and Oracle (coursework or project experience acceptable).",
    technologies: ["Python", "SQL", "Tableau", "Oracle"],
  },
] });
analyticsStack.title = "IT Data Analytics Intern";
const analyticsReadiness = R.scoreReadiness(analyticsStack, profile);
assert.equal(analyticsReadiness.label, "Major required gaps");
assert.ok(analyticsReadiness.delta <= -20);
assert.match(analyticsReadiness.details.join(" "), /Required gap: (oracle|sql|tableau)/i);
assert.match(analyticsReadiness.details.join(" "), /cautiously supported: python/i);

const gisDomain = inspectedJob({ required: [
  { statement: "Previous GIS coursework or relevant GIS experience." },
  { statement: "Familiarity with Esri Geographic Information Systems (GIS) product line." },
] });
gisDomain.title = "GIS Intern - Geographic Information Systems";
const broadSystemsProfile = JSON.parse(JSON.stringify(profile));
broadSystemsProfile.supportedKeywords.push("systems");
broadSystemsProfile.facts.supportedSkills.push("systems");
const gisAnalysis = R.analyzeRequiredSkills(gisDomain, broadSystemsProfile);
assert.equal(gisAnalysis.supported.includes("systems"), false, "generic systems evidence must not satisfy a specific GIS domain requirement");
assert.equal(gisAnalysis.unverifiedDomainRequirements.length, 2);
const gisReadiness = R.scoreReadiness(gisDomain, broadSystemsProfile);
assert.equal(gisReadiness.delta, -12);
assert.match(gisReadiness.details.join(" "), /Unverified required domain experience: Previous GIS coursework/i);
assert.match(gisReadiness.details.join(" "), /Esri Geographic Information Systems/i);

const gisProfile = JSON.parse(JSON.stringify(broadSystemsProfile));
gisProfile.supportedKeywords.push("gis");
gisProfile.facts.supportedSkills.push("GIS");
const gisSupportedAnalysis = R.analyzeRequiredSkills(gisDomain, gisProfile);
assert.deepEqual(gisSupportedAnalysis.unverifiedDomainRequirements, []);
assert.equal(gisSupportedAnalysis.supported.includes("gis"), true);
assert.equal(R.scoreReadiness(gisDomain, gisProfile).delta, 0);

const communicationOnly = inspectedJob({ required: [
  { statement: "Strong communication and interpersonal skills." },
] });
assert.deepEqual(R.analyzeRequiredSkills(communicationOnly, profile).unverifiedDomainRequirements, []);
assert.equal(R.scoreReadiness(communicationOnly, profile).delta, 0);

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

const sophomoreProfile = JSON.parse(JSON.stringify(profile));
sophomoreProfile.facts.graduation = "May 2029";
sophomoreProfile.facts.studentStage = "";
sophomoreProfile.facts.workExperienceEvidence = [];
sophomoreProfile.facts.courseworkEvidence = ["Corporate Finance and Excel modeling"];
sophomoreProfile.facts.projectEvidence = [];
sophomoreProfile.facts.leadershipEvidence = [];

assert.equal(R.profileStudentStage ? R.profileStudentStage : undefined, undefined, "stage derivation belongs to deterministic eligibility base");

const sophomoreRequired = inspectedJob({
  studentRequired: [{ statement: "Must be a current sophomore." }],
});
assert.equal(
  R.scoreJob(sophomoreRequired, sophomoreProfile, new Date("2026-10-05T12:00:00Z")).excluded,
  false,
  "May 2029 graduation should derive to sophomore in fall 2026"
);

const risingJuniorRequired = inspectedJob({
  studentRequired: [{ statement: "Applicants must be rising juniors." }],
});
assert.equal(
  R.scoreJob(risingJuniorRequired, sophomoreProfile, new Date("2026-10-05T12:00:00Z")).excluded,
  false,
  "current sophomores should satisfy a rising-junior requirement"
);

const seniorRequired = inspectedJob({
  studentRequired: [{ statement: "Applicants must be current seniors." }],
});
const seniorConflict = R.scoreJob(seniorRequired, sophomoreProfile, new Date("2026-10-05T12:00:00Z"));
assert.equal(seniorConflict.excluded, true);
assert.match(seniorConflict.reasons.join(" "), /student-stage condition/i);

const stageOverride = JSON.parse(JSON.stringify(sophomoreProfile));
stageOverride.facts.studentStage = "Senior";
assert.equal(
  R.scoreJob(seniorRequired, stageOverride, new Date("2026-10-05T12:00:00Z")).excluded,
  false,
  "explicit student-stage correction should override graduation-derived stage"
);

const silentExperience = inspectedJob();
assert.equal(R.scoreReadiness(silentExperience, sophomoreProfile).delta, 0, "silence about experience must stay neutral");

const preferredInternship = inspectedJob({
  preferred: [{ statement: "Previous internship experience preferred." }],
});
const preferredInternshipReadiness = R.scoreReadiness(preferredInternship, sophomoreProfile);
assert.ok(preferredInternshipReadiness.delta < 0 && preferredInternshipReadiness.delta > -10);
assert.match(preferredInternshipReadiness.details.join(" "), /Preferred prior internship experience/i);

const requiredInternship = inspectedJob({
  required: [{ statement: "Previous internship experience required." }],
});
const requiredInternshipReadiness = R.scoreReadiness(requiredInternship, sophomoreProfile);
assert.ok(requiredInternshipReadiness.delta <= -10);
assert.match(requiredInternshipReadiness.details.join(" "), /Required prior internship experience/i);

const courseworkAccepted = inspectedJob({
  required: [{ statement: "Relevant coursework or project experience is acceptable in lieu of prior professional experience." }],
});
const courseworkReadiness = R.scoreReadiness(courseworkAccepted, sophomoreProfile);
assert.equal(courseworkReadiness.delta, 0);
assert.match(courseworkReadiness.details.join(" "), /Coursework\/project evidence can satisfy/i);

const yearsRequired = inspectedJob({
  required: [{ statement: "2+ years of relevant professional experience required." }],
});
const yearsReadiness = R.scoreReadiness(yearsRequired, sophomoreProfile);
assert.ok(yearsReadiness.delta <= -10);
assert.match(yearsReadiness.details.join(" "), /Required 2 years of experience/i);

const noExperienceRequired = inspectedJob({
  required: [{ statement: "No prior experience is required." }],
});
const noExperienceReadiness = R.scoreReadiness(noExperienceRequired, sophomoreProfile);
assert.equal(noExperienceReadiness.delta, 0);
assert.match(noExperienceReadiness.details.join(" "), /explicitly says prior experience is not required/i);

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
assert.match(greenhouseScore.inspection.label, /^Authoritative evidence/);
assert.match(greenhouseScore.inspection.evidence.join(" "), /Required gap: c\+\+/i);

console.log("apply-next readiness tests passed");
