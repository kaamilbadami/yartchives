const assert = require("node:assert/strict");
const A = require("../apply-next.js");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs", "tech-business"],
  supportedKeywords: ["software", "testing", "systems", "linux", "java", "c"],
  cautiousKeywords: ["python", "bash"],
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

const cautiousOnly = A.scoreFit({ title: "Python Bash Intern", profiles: [] }, profile);
assert.equal(cautiousOnly.score, 0);
assert.match(cautiousOnly.detail, /Not credited as strengths/);

const direct = A.scoreJob({ ...freshDirect, company: "D", link_kind: "direct" }, profile, now);
const listing = A.scoreJob({ ...freshDirect, company: "E", link_kind: "listing" }, profile, now);
assert.ok(direct.total > listing.total);
assert.equal(direct.components.link.score, 5);
assert.equal(listing.components.link.score, 2);

const remote = A.scoreLocation({ states: ["Remote"] }, profile);
assert.equal(remote.score, 9);
const nearby = A.scoreLocation({ states: ["PA"], _distanceMiles: 28 }, profile);
assert.equal(nearby.score, 10);
const relocation = A.scoreLocation({ states: ["CA"] }, profile);
assert.equal(relocation.score, 6);

const exactTerm = A.scoreEligibility(freshDirect, profile);
assert.equal(exactTerm.score, 18);
const unknownTerm = A.scoreEligibility({ ...freshDirect, term: null }, profile);
assert.ok(exactTerm.score > unknownTerm.score);

const totalFromParts = Object.values(direct.components).reduce((sum, part) => sum + part.score, 0);
assert.equal(direct.total, totalFromParts);
assert.equal(direct.total <= 100, true);

console.log("apply-next tests passed");
