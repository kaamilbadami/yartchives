const fs = require('fs');
const D = require('./apply-next-dimensions.js'); // The final layer?
// Let's use the UI layer which probably uses everything
const UI = require('./apply-next-ui.js');

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

// Shuffle listings to simulate feed refresh
function shuffle(array) {
  const newArr = array.slice();
  for (let i = newArr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [newArr[i], newArr[j]] = [newArr[j], newArr[i]];
  }
  return newArr;
}

const listingsShuffled = shuffle(listings);
const ranked2 = D.rankJobs(listingsShuffled, profile, now);

const top10_1 = ranked1.slice(0, 10).map(r => r.job.id);
const top10_2 = ranked2.slice(0, 10).map(r => r.job.id);

console.log("Top 10 Run 1:");
top10_1.forEach((id, i) => console.log(`${i+1}. ${id}`));

console.log("\nTop 10 Run 2:");
top10_2.forEach((id, i) => console.log(`${i+1}. ${id}`));

let overlap = 0;
for (const id of top10_1) {
  if (top10_2.includes(id)) overlap++;
}
console.log(`\nOverlap: ${overlap}/10`);
