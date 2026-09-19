const assert = require("node:assert/strict");
const D = require("../apply-next-dimensions.js");

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

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software"],
  facts: { supportedSkills: [] },
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] },
  ],
  preferredStates: ["CT"],
  relocationAllowed: true,
};

const job = {
  company: "ExampleCo",
  title: "Software Engineer Intern",
  profiles: ["cs"],
  states: ["CT"],
  location: "Hartford, CT",
  term: "Summer 2027",
  posted_at: "2026-09-17T12:00:00Z",
  link_kind: "direct",
  url: "https://example.com/job",
};

const scored = D.scoreJob(job, profile, new Date("2026-09-17T16:00:00Z"));
assert.equal(scored.components.role, undefined);
assert.equal(scored.components.location.score, 20);
assert.equal(scored.components.roi.score, 23);
assert.deepEqual(scored.applicationValue.role, { score: 15, max: 15 });
assert.deepEqual(scored.applicationValue.market, { score: 8, max: 15 });
assert.match(scored.components.roi.detail, /Role value 15\/15/);
assert.match(scored.components.roi.detail, /Market opportunity 8\/15/);
assert.ok(scored.total <= 100);

const lowerRoleProfile = {
  ...profile,
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 0.5, keywords: ["software engineer"] },
  ],
};
const lowerRole = D.scoreJob(
  { ...job, url: "https://example.com/lower-role" },
  lowerRoleProfile,
  new Date("2026-09-17T16:00:00Z")
);
assert.equal(lowerRole.applicationValue.market.score, scored.applicationValue.market.score);
assert.ok(lowerRole.applicationValue.role.score < scored.applicationValue.role.score);
assert.ok(lowerRole.components.roi.score < scored.components.roi.score);

console.log("apply-next final weight tests passed");
