const D = require('./apply-next-dimensions.js');
const fs = require('fs');
const jobs = JSON.parse(fs.readFileSync('data/listings.json', 'utf8')).jobs.slice(0, 10);
const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software"],
  facts: { supportedSkills: ["java"] },
  preferredStates: ["NY"],
  relocationAllowed: true,
};
const now = new Date("2026-09-17T12:00:00Z");
const ranked = D.rankJobs(jobs, profile, now);
console.log("Ranked:", ranked.length);
if (ranked.length === 0) {
  // Let's manually trace one job
  const job = jobs[0];
  const L = require('./apply-next-location.js');
  const locRes = L.scoreJob(job, profile, now);
  console.log("Loc result excluded?", locRes.excluded);
  const dimRes = D.transform(locRes, profile);
  console.log("Dim result excluded?", dimRes.excluded, dimRes.reasons);
}
