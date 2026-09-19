const fs = require('fs');
const jsdom = require('jsdom');
const { JSDOM } = jsdom;

const dom = new JSDOM(`<!DOCTYPE html><html><body></body></html>`, {
  url: "https://example.com",
  runScripts: "dangerously"
});

// Load the dependencies into the DOM window
const files = [
  'apply-next.js',
  'apply-next-location.js',
  'apply-next-location-preferences.js',
  'apply-next-competition.js',
  'apply-next-readiness.js',
  'apply-next-dimensions.js',
  'apply-next-presentation.js'
];

for (const file of files) {
  const content = fs.readFileSync(file, 'utf8');
  dom.window.eval(content);
}

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

const ranked1 = dom.window.YartchivesApplyNext.rankJobs(listings, profile, now);
console.log(`Ranked 1 length: ${ranked1.length}`);

// Test the stable sorting of rankJobs.
const top10_1 = ranked1.slice(0, 10).map(r => r.job.id);
console.log(top10_1);

// Shuffle array
const shuf = [...listings];
shuf.reverse();
const ranked2 = dom.window.YartchivesApplyNext.rankJobs(shuf, profile, now);
const top10_2 = ranked2.slice(0, 10).map(r => r.job.id);
console.log(top10_2);
