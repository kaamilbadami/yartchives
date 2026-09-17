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

function trustedDistance(miles) {
  return { _distanceMiles: miles, _distanceMilesBasis: "apply-next-profile" };
}

function inspected(posting = {}) {
  return {
    status: "inspected",
    posting: { application_status: "available", ...posting },
    requirements: {},
  };
}

assert.deepEqual(L.scoreLocation({ location: "Baltimore, MD", states: ["MD"], ...trustedDistance(220) }, profile), {
  score: 10,
  detail: "Preferred state: MD",
});
assert.equal(L.scoreLocation({ location: "Remote", states: ["Remote"] }, profile).score, 9);
assert.equal(L.scoreLocation({ location: "York, PA", states: ["PA"], ...trustedDistance(35) }, profile).score, 10);
assert.equal(L.scoreLocation({ location: "York, PA", states: ["PA"], ...trustedDistance(90) }, profile).score, 8);
assert.equal(L.scoreLocation({ location: "Boston, MA", states: ["MA"], ...trustedDistance(160) }, profile).score, 7);
assert.equal(L.scoreLocation({ location: "Raleigh, NC", states: ["NC"], ...trustedDistance(330) }, profile).score, 5);
assert.equal(L.scoreLocation({ location: "Austin, TX", states: ["TX"], ...trustedDistance(1200) }, profile).score, 3);
assert.equal(L.scoreLocation({ location: "United States", states: ["US"] }, profile).score, 4);
assert.equal(L.scoreLocation({ location: "Denver, CO", states: ["CO"] }, profile).score, 4);

const noRemote = { ...profile, remoteRelevant: false };
assert.equal(L.scoreLocation({ location: "Remote", states: ["Remote"] }, noRemote).score, 2);
const noRelocation = { ...profile, relocationAllowed: false };
assert.equal(L.scoreLocation({ location: "Austin, TX", states: ["TX"], ...trustedDistance(1200) }, noRelocation).score, 1);

assert.deepEqual(L.explicitLocationStates({ location: "State College, PA" }), ["PA"]);
const stateCollege = L.scoreLocation({
  location: "State College, PA",
  states: ["CT", "PA"],
  _distanceMiles: 22,
}, profile);
assert.equal(stateCollege.score, 4);
assert.doesNotMatch(stateCollege.detail, /Preferred state: CT|Within 50 miles/);

const rtp = L.scoreLocation({
  location: "RTP North Carolina US",
  states: ["CT", "NC"],
  _distanceMiles: 12,
}, profile);
assert.equal(rtp.score, 4);
assert.doesNotMatch(rtp.detail, /Preferred state: CT|Within 50 miles/);

const pittsburghStale = L.scoreLocation({
  location: "Pittsburgh",
  states: ["PA"],
  _distanceMiles: 18,
}, profile);
assert.equal(pittsburghStale.score, 4);
assert.doesNotMatch(pittsburghStale.detail, /Within 50 miles/);
const pittsburghTrusted = L.scoreLocation({
  location: "Pittsburgh",
  states: ["PA"],
  ...trustedDistance(18),
}, profile);
assert.equal(pittsburghTrusted.score, 10);

const job = {
  company: "FarCo",
  title: "Software Engineer Intern",
  profiles: ["cs"],
  states: ["TX"],
  location: "Austin, TX",
  term: "Summer 2027",
  posted_at: "2026-09-16T12:00:00Z",
  link_kind: "direct",
  url: "https://example.com/apply-far",
  _inspection: inspected(),
  ...trustedDistance(1200),
};
const now = new Date("2026-09-16T16:00:00Z");
const before = base.scoreJob(job, profile, now);
const after = L.scoreJob(job, profile, now);
assert.equal(before.components.location.score, 6);
assert.equal(after.components.location.score, 3);
assert.equal(after.total, before.total - 3);
assert.match(after.components.location.detail, /Long-distance relocation/);

const nearJob = {
  ...job,
  company: "NearCo",
  states: ["PA"],
  location: "York, PA",
  url: "https://example.com/apply-near",
  ...trustedDistance(90),
};
const metadataOnly = {
  ...nearJob,
  company: "MetadataCo",
  url: "https://example.com/metadata-only",
  _inspection: undefined,
};
assert.equal(L.hasAuthoritativeInspection(job), true);
assert.equal(L.hasAuthoritativeInspection(metadataOnly), false);
const ranked = L.rankJobs([metadataOnly, job, nearJob], profile, now);
assert.equal(ranked.length, 2);
assert.equal(ranked[0].job.company, "NearCo");
assert.ok(ranked.every(result => result.inspection?.state === "inspected"));
assert.ok(ranked[0].components.location.score > ranked[1].components.location.score);

const duolingoA = {
  ...nearJob,
  id: "duo-a",
  company: "Duolingo",
  location: "New York City, NY +2",
  states: ["NY"],
  url: "https://job-boards.greenhouse.io/duolingo/jobs/8805925002?gh_jid=8805925002&utm_source=x",
};
const duolingoB = {
  ...duolingoA,
  id: "duo-b",
  location: "New York, NY",
  url: "https://job-boards.greenhouse.io/duolingo/jobs/8805925002?gh_jid=8805925002",
};
assert.equal(L.canonicalPostingKey(duolingoA), L.canonicalPostingKey(duolingoB));
assert.equal(L.dedupeCanonicalJobs([duolingoA, duolingoB]).length, 1);

const geckoA = {
  ...nearJob,
  id: "gecko-a",
  company: "Gecko Robotics",
  location: "New York City, NY",
  states: ["NY"],
  url: "https://jobs.ashbyhq.com/gecko-robotics/01138338-ff3c-4982-8ba3-5401386bf082/application?embed=true&utm_source=Simplify",
};
const geckoB = {
  ...geckoA,
  id: "gecko-b",
  url: "https://jobs.ashbyhq.com/gecko-robotics/01138338-ff3c-4982-8ba3-5401386bf082",
};
const geckoC = {
  ...geckoA,
  id: "gecko-c",
  url: "https://jobs.ashbyhq.com/gecko-robotics/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
  location: "Boston, MA",
  states: ["MA"],
};
const geckoMetadata = {
  ...geckoA,
  id: "gecko-metadata",
  url: "https://jobs.ashbyhq.com/gecko-robotics/ffffffff-1111-4222-8333-444444444444",
  _inspection: undefined,
};
assert.equal(L.canonicalPostingKey(geckoA), L.canonicalPostingKey(geckoB));
const geckoRanked = L.rankJobs([geckoA, geckoB, geckoC, geckoMetadata], profile, now);
assert.equal(geckoRanked.length, 2);
for (const result of geckoRanked) {
  assert.match(result.components.roi.detail, /observed employer demand: 2 current software engineering openings/);
  assert.doesNotMatch(result.components.roi.detail, /3 current software engineering openings/);
}

assert.deepEqual(
  L.normalizeAuthoritativeLocations(["Denver, CO, US", "437 DENVER CO", "Sterling, VA, US"]),
  ["Denver, CO", "Sterling, VA"]
);
assert.deepEqual(
  L.normalizeAuthoritativeLocations(["US - Remote", "Minnesota - Remote Office"]),
  ["Remote"]
);
assert.deepEqual(
  L.normalizeAuthoritativeLocations(["United States - Remote", "US - California - Thousand Oaks - Field/Remote"]),
  ["Remote", "Thousand Oaks, CA"]
);

const caci = {
  ...job,
  id: "caci-331999",
  company: "CACI",
  title: "Cleared Software Engineer Intern - Summer 2027",
  location: "Denver, CO, US",
  states: ["Remote", "VA", "CO"],
  url: "https://caci.wd1.myworkdayjobs.com/External/job/Denver-CO-US/Cleared-Software-Engineer-Intern---Summer-2027_331999",
  _inspection: inspected({
    title: "Cleared Software Engineer Intern - Summer 2027",
    requisition_id: "331999",
    locations: { status: "authoritative", values: ["Denver, CO, US", "437 DENVER CO", "Sterling, VA, US"] },
  }),
  ...trustedDistance(32),
};
const caciView = L.authoritativePostingView(caci);
assert.deepEqual(caciView.states, ["CO", "VA"]);
assert.equal(caciView.location, "Denver, CO · Sterling, VA");
const caciScored = L.scoreJob(caci, profile, now);
assert.equal(caciScored.components.location.score, 10);
assert.match(caciScored.components.location.detail, /Within 50 miles/);
assert.doesNotMatch(caciScored.components.location.detail, /Remote opportunity/);

const wex = {
  ...job,
  id: "wex-r22593",
  company: "WEX",
  title: "Fullstack Software Engineer Intern (Undergraduate)",
  location: "US - Remote",
  states: ["Remote"],
  url: "https://wexinc.wd5.myworkdayjobs.com/WEXInc/job/US---Remote/Backend-Software-Engineer-Intern--Undergraduate-_R22593",
  _inspection: inspected({
    title: "Fullstack Software Engineer Intern (Undergraduate)",
    requisition_id: "R22593",
    locations: { status: "authoritative", values: ["US - Remote", "Minnesota - Remote Office"] },
  }),
};
const wexView = L.authoritativePostingView(wex);
assert.equal(wexView.title, "Fullstack Software Engineer Intern (Undergraduate)");
assert.equal(wexView.location, "Remote");
assert.deepEqual(wexView.states, ["Remote"]);
assert.match(wexView.url, /Fullstack-Software-Engineer-Intern-Undergraduate_R22593$/);
assert.doesNotMatch(wexView.url, /Backend-Software-Engineer/);
assert.equal(L.scoreJob(wex, profile, now).components.location.detail, "Remote opportunity");

console.log("apply-next authoritative-only, location, and canonical dedupe tests passed");
