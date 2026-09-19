const fs = require('fs');
const UI = require('./apply-next-ui.js');
const D = require('./apply-next-dimensions.js');

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software", "java", "python", "c++", "c", "javascript", "react"],
  facts: { supportedSkills: ["java", "python", "javascript"] },
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] },
  ],
  preferredStates: ["NY", "CA", "WA", "TX"],
  relocationAllowed: true,
};

const listings = JSON.parse(fs.readFileSync('data/listings.json', 'utf8')).jobs || [];
const now = new Date("2026-09-17T12:00:00Z");

const ranked1 = D.rankJobs(listings, profile, now);

console.log(`Ranked 1 length: ${ranked1.length}`);

// Let's test the stable sorting of rankJobs in apply-next-dimensions.js.
const top10_1 = ranked1.slice(0, 10).map(r => r.job.id);
console.log(top10_1);

// Shuffle array
const shuf = [...listings];
shuf.reverse();
const ranked2 = D.rankJobs(shuf, profile, now);
const top10_2 = ranked2.slice(0, 10).map(r => r.job.id);
console.log(top10_2);
