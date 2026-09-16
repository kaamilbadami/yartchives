const assert = require("node:assert/strict");
const base = require("../apply-next-competition.js");
const L = require("../apply-next-location.js");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software engineer"],
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] },
  ],
  preferredStates: ["MD", "CT", "NY"],
  remoteRelevant: true,
  relocationAllowed: true,
  nearbyMiles: 50,
};

assert.deepEqual(L.scoreLocation({ states: ["MD"], _distanceMiles: 220 }, profile), {
  score: 10,
  detail: "Preferred state: MD",
});
assert.equal(L.scoreLocation({ states: ["Remote"] }, profile).score, 9);
assert.equal(L.scoreLocation({ states: ["PA"], _distanceMiles: 35 }, profile).score, 10);
assert.equal(L.scoreLocation({ states: ["PA"], _distanceMiles: 90 }, profile).score, 8);
assert.equal(L.scoreLocation({ states: ["MA"], _distanceMiles: 160 }, profile).score, 7);
assert.equal(L.scoreLocation({ states: ["NC"], _distanceMiles: 330 }, profile).score, 5);
assert.equal(L.scoreLocation({ states: ["TX"], _distanceMiles: 1200 }, profile).score, 3);
assert.equal(L.scoreLocation({ states: ["US"] }, profile).score, 4);
assert.equal(L.scoreLocation({ states: ["CO"] }, profile).score, 4);

const noRemote = { ...profile, remoteRelevant: false };
assert.equal(L.scoreLocation({ states: ["Remote"] }, noRemote).score, 2);
const noRelocation = { ...profile, relocationAllowed: false };
assert.equal(L.scoreLocation({ states: ["TX"], _distanceMiles: 1200 }, noRelocation).score, 1);

const job = {
  company: "FarCo",
  title: "Software Engineer Intern",
  profiles: ["cs"],
  states: ["TX"],
  term: "Summer 2027",
  posted_at: "2026-09-16T12:00:00Z",
  link_kind: "direct",
  url: "https://example.com/apply",
  _distanceMiles: 1200,
};
const now = new Date("2026-09-16T16:00:00Z");
const before = base.scoreJob(job, profile, now);
const after = L.scoreJob(job, profile, now);
assert.equal(before.components.location.score, 6);
assert.equal(after.components.location.score, 3);
assert.equal(after.total, before.total - 3);
assert.match(after.components.location.detail, /Long-distance relocation/);

const nearJob = { ...job, company: "NearCo", states: ["PA"], _distanceMiles: 90 };
const ranked = L.rankJobs([job, nearJob], profile, now);
assert.equal(ranked[0].job.company, "NearCo");
assert.ok(ranked[0].components.location.score > ranked[1].components.location.score);

console.log("apply-next location tests passed");
