const assert = require("node:assert/strict");
const A = require("../apply-next.js");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs", "tech-business"],
  supportedKeywords: ["software", "testing", "systems", "linux", "java", "c"],
  cautiousKeywords: ["python", "bash"],
  facts: {
    graduation: "May 2028",
    workAuthorization: "U.S. citizen; no sponsorship needed",
    supportedSkills: ["Java", "C", "Linux", "testing"],
    cautiousSkills: ["Python", "Bash"],
  },
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer", "software developer"] },
    { id: "testing", label: "Testing / systems", priority: 1, keywords: ["test engineer", "qa", "systems"] },
    { id: "analytics", label: "Technical analytics", priority: 0.8, keywords: ["data analyst", "business analyst"] },
  ],
  preferredStates: ["MD", "DC", "CT", "NY"],
  remoteRelevant: true,
  relocationAllowed: true,
  nearbyMiles: 50,
};
const now = new Date("2026-09-16T16:00:00Z");

const freshDirect = {
  company: "A",
  title: "Software Engineer Intern",
  profiles: ["cs"],
  states: ["CT"],
  term: "Summer 2027",
  posted_at: "2026-09-15T12:00:00Z",
  link_kind: "direct",
  url: "https://example.com/apply",
};
const olderListing = {
  company: "B",
  title: "Software Engineer Intern",
  profiles: ["cs"],
  states: ["CA"],
  term: "Summer 2027",
  posted_at: "2026-08-20T12:00:00Z",
  link_kind: "listing",
  url: "https://example.com/listing",
};
const graduateOnly = {
  company: "C",
  title: "Machine Learning Intern, PhD",
  profiles: ["cs"],
  states: ["MD"],
  term: "Summer 2027",
  posted_at: "2026-09-16T10:00:00Z",
  link_kind: "direct",
};

const ranked = A.rankJobs([olderListing, graduateOnly, freshDirect], profile, now);
assert.equal(ranked.length, 2);
assert.equal(ranked[0].job.company, "A");
assert.equal(ranked[1].job.company, "B");
assert.ok(ranked[0].total > ranked[1].total);

const gradScore = A.scoreJob(graduateOnly, profile, now);
assert.equal(gradScore.excluded, true);
assert.match(gradScore.reasons[0], /Graduate-only/);

const graduationConflict = A.scoreJob({
  ...freshDirect,
  company: "Entegris",
  title: "Portfolio Analytics Analyst Co-Op",
  opportunity_type: "co-op",
  term: null,
  _inspection: {
    status: "inspected",
    posting: { application_status: "available" },
    schedule: { status: "unknown", terms: [], duration_evidence: [], date_range_evidence: [] },
    requirements: {
      graduation: {
        classification: "required",
        required: [{
          statement: "Must graduate in 2027.",
          requirement_state: "required",
          negated: false,
        }],
        preferred: [],
        unspecified: [],
        not_required: [],
      },
    },
  },
}, profile, now);
assert.equal(graduationConflict.excluded, true);
assert.match(graduationConflict.reasons[0], /2028 does not match the posting's explicit required graduation year\/window/);

const cautiousOnly = A.scoreFit({ title: "Python Bash Intern", profiles: [] }, profile);
assert.equal(cautiousOnly.score, 0);
assert.match(cautiousOnly.detail, /Not credited as strengths/);

const direct = A.scoreJob({ ...freshDirect, company: "D", link_kind: "direct" }, profile, now);
const listing = A.scoreJob({ ...freshDirect, company: "E", link_kind: "listing" }, profile, now);
assert.ok(direct.total > listing.total);
assert.equal(direct.components.link.score, 5);
assert.equal(listing.components.link.score, 2);
assert.equal(direct.components.freshness.score, 10);
assert.equal(direct.components.role.score, 15);
assert.equal(direct.components.location.score, 20);

const remote = A.scoreLocation({ states: ["Remote"] }, profile);
assert.equal(remote.score, 18);
const nearby = A.scoreLocation({ states: ["PA"], _distanceMiles: 28 }, profile);
assert.equal(nearby.score, 20);
const relocation = A.scoreLocation({ states: ["CA"] }, profile);
assert.equal(relocation.score, 12);

const exactTerm = A.scoreEligibility(freshDirect, profile);
assert.equal(exactTerm.score, 18);
const unknownTerm = A.scoreEligibility({ ...freshDirect, term: null }, profile);
assert.ok(exactTerm.score > unknownTerm.score);

const inspectedStrong = {
  ...freshDirect,
  company: "Inspected",
  url: "https://careers-example.icims.com/jobs/74848/job",
  _inspection: {
    provider: "icims",
    status: "inspected",
    retrieval_confidence: "high",
    posting: { application_status: "available" },
    requirements: {
      graduation: {
        classification: "required",
        required: [{ statement: "Candidates must graduate between December 2027 and June 2028.", requirement_state: "required", negated: false }],
        preferred: [], unspecified: [], not_required: [],
      },
      education: { classification: "required", required: [{ statement: "Pursuing a Bachelor's degree.", requirement_state: "required", negated: false }], preferred: [], unspecified: [], not_required: [] },
      student_status: { classification: "unknown", required: [], preferred: [], unspecified: [], not_required: [] },
      major_fields: { classification: "required", required: [{ statement: "Degree in Computer Science or related field.", requirement_state: "required", negated: false }], preferred: [], unspecified: [], not_required: [] },
      citizenship: { classification: "unknown", required: [], preferred: [], unspecified: [], not_required: [] },
      work_authorization: {
        classification: "required",
        required: [{ statement: "Applicants must be authorized to work in the U.S. and the company does not sponsor.", requirement_state: "required", negated: false }],
        preferred: [], unspecified: [], not_required: [],
      },
      skills: {
        classification: "mixed",
        required: [{ statement: "Experience with C and Linux is required.", technologies: ["C", "Linux"], requirement_state: "required", negated: false }],
        preferred: [{ statement: "Java experience preferred.", technologies: ["Java"], requirement_state: "preferred", negated: false }],
        unspecified: [], not_required: [],
      },
      other_eligibility: { classification: "unknown", required: [], preferred: [], unspecified: [], not_required: [] },
    },
  },
};
const inspectedStrongScore = A.scoreJob(inspectedStrong, profile, now);
const metadataScore = A.scoreJob({ ...freshDirect, company: "Metadata" }, profile, now);
assert.equal(inspectedStrongScore.excluded, false);
assert.equal(inspectedStrongScore.inspection.state, "inspected");
assert.ok(inspectedStrongScore.components.eligibility.score >= metadataScore.components.eligibility.score);
assert.match(inspectedStrongScore.components.eligibility.detail, /2028 fits/);
assert.match(inspectedStrongScore.components.eligibility.detail, /work-authorization/);
assert.match(inspectedStrongScore.components.fit.detail, /Required posting skills supported/);

const springCoop = {
  ...freshDirect,
  company: "Spring co-op",
  term: null,
  _inspection: {
    provider: "workday",
    status: "inspected",
    posting: { application_status: "available" },
    schedule: {
      status: "authoritative",
      terms: ["Spring 2027"],
      duration_evidence: ["This assignment is intended to be 6 months in duration."],
      date_range_evidence: ["Available to work beginning in January through June."],
    },
    requirements: {},
  },
};
const springCoopScore = A.scoreJob(springCoop, profile, now);
assert.equal(springCoopScore.excluded, true);
assert.match(springCoopScore.reasons[0], /Authoritative posting term is Spring 2027, not Summer 2027/);

const summerAuthoritative = A.scoreEligibility({
  ...freshDirect,
  term: null,
  _inspection: {
    status: "inspected",
    posting: { application_status: "available" },
    schedule: {
      status: "authoritative",
      terms: ["Summer 2027"],
      duration_evidence: ["12-week internship."],
      date_range_evidence: [],
    },
    requirements: {},
  },
}, profile);
assert.equal(summerAuthoritative.excluded, false);
assert.match(summerAuthoritative.detail, /Authoritative posting matches Summer 2027/);
assert.match(summerAuthoritative.detail, /Authoritative schedule: 12-week internship/);

const unavailable = A.scoreJob({
  ...freshDirect,
  url: "https://job-boards.greenhouse.io/example/jobs/9999999",
  _inspection: {
    provider: "greenhouse",
    status: "unavailable",
    posting: null,
    requirements: {},
  },
}, profile, now);
assert.equal(unavailable.excluded, true);
assert.match(unavailable.reasons[0], /unavailable/i);

const unsupportedRequiredSkill = A.scoreFit({
  ...freshDirect,
  _inspection: {
    status: "inspected",
    posting: { application_status: "available" },
    requirements: {
      skills: {
        classification: "required",
        required: [{ statement: "Kubernetes is required.", technologies: ["Kubernetes"], requirement_state: "required", negated: false }],
        preferred: [], unspecified: [], not_required: [],
      },
    },
  },
}, profile);
const metadataFit = A.scoreFit(freshDirect, profile);
assert.ok(unsupportedRequiredSkill.score < metadataFit.score);
assert.match(unsupportedRequiredSkill.detail, /not supported by profile/i);

const notRequiredAuth = A.scoreEligibility({
  ...freshDirect,
  _inspection: {
    status: "inspected",
    posting: { application_status: "available" },
    requirements: {
      citizenship: {
        classification: "not_required",
        required: [], preferred: [], unspecified: [],
        not_required: [{ statement: "U.S. citizenship is not required.", requirement_state: "not_required", negated: true }],
      },
      work_authorization: {
        classification: "not_required",
        required: [], preferred: [], unspecified: [],
        not_required: [{ statement: "Visa sponsorship is not required.", requirement_state: "not_required", negated: true }],
      },
    },
  },
}, profile);
assert.equal(notRequiredAuth.excluded, false);
assert.match(notRequiredAuth.detail, /not required/);

assert.equal(A.summarizeInspection(freshDirect).state, "metadata-only");
assert.equal(A.summarizeInspection(inspectedStrong).label, "Posting inspected");

const totalFromParts = Object.values(direct.components).reduce((sum, part) => sum + part.score, 0);
assert.equal(direct.total, totalFromParts);
assert.equal(direct.total <= 100, true);

console.log("apply-next tests passed");
