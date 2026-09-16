const assert = require("node:assert/strict");
const U = require("../frontend-utils.js");

assert.equal(U.matchesTextLocation({ location: "Acton, Massachusetts", states: ["MA"] }, "CT"), false);
assert.equal(U.matchesTextLocation({ location: "Danbury, CT", states: ["CT"] }, "CT"), true);
assert.equal(U.matchesTextLocation({ location: "Acton, Massachusetts", states: ["MA"] }, "Massachusetts"), true);

assert.equal(U.classifyEducationFromTitle("Business Data Scientist Intern, PhD, Summer 2027"), "graduate-only");
assert.equal(U.classifyEducationFromTitle("Software Engineering Intern, BS/MS, Summer 2027"), "undergrad");
assert.equal(U.classifyEducationFromTitle("Software Engineer Intern"), "unspecified");
assert.equal(U.classifyOpportunityTypeFromTitle("Embedded Software Engineering Co-op"), "co-op");
assert.equal(U.classifyOpportunityTypeFromTitle("Software Engineer Intern"), "internship");

const csv = [
  "zip_code,city,state,latitude,longitude,population",
  "06897,Wilton,CT,41.1954,-73.4379,18000",
  "20740,College Park,MD,38.9966,-76.9275,32000",
  "06810,Danbury,CT,41.3948,-73.4540,52000",
].join("\n");
const geo = U.buildGeoIndex(csv);
assert.equal(geo.zips.get("06897").city, "Wilton");
assert.equal(geo.zips.get("20740").state, "MD");

const same = U.milesBetween(geo.zips.get("06897"), geo.zips.get("06897"));
assert.ok(same < 0.001);
const wiltonToCollegePark = U.milesBetween(geo.zips.get("06897"), geo.zips.get("20740"));
assert.ok(wiltonToCollegePark > 230 && wiltonToCollegePark < 280, `unexpected distance ${wiltonToCollegePark}`);

const exactZipJob = { location: "Office 06810", states: ["CT"] };
const exactResult = U.distanceForJob(exactZipJob, geo.zips.get("06897"), geo);
assert.equal(exactResult.precision, "zip");
assert.ok(exactResult.miles < 20);

const cityJob = { location: "Danbury, CT", states: ["CT"] };
const cityResult = U.distanceForJob(cityJob, geo.zips.get("06897"), geo);
assert.equal(cityResult.precision, "city");
assert.ok(cityResult.miles < 20);

require("./results-language.test.cjs");
console.log("frontend-utils tests passed");
