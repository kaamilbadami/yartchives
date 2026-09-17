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
  "20166,Sterling,VA,38.9440,-77.4558,30000",
  "80202,Denver,CO,39.7525,-104.9995,12000",
  "94105,San Francisco,CA,37.7898,-122.3942,34000",
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

const authoritativeMultiLocation = {
  location: "Denver, CO, US",
  states: ["CO"],
  _inspection: {
    status: "inspected",
    posting: {
      locations: {
        status: "authoritative",
        values: ["Denver, CO, US", "437 DENVER CO", "Sterling, VA, US"],
      },
    },
  },
};
assert.equal(U.locationTextForJob(authoritativeMultiLocation), "Denver, CO, US ; 437 DENVER CO ; Sterling, VA, US");
assert.deepEqual(U.statesForLocation(U.locationTextForJob(authoritativeMultiLocation)), ["CO", "VA"]);
const authoritativeDistance = U.distanceForJob(authoritativeMultiLocation, geo.zips.get("20740"), geo);
assert.equal(authoritativeDistance.point.state, "VA");
assert.equal(authoritativeDistance.point.city, "sterling");
assert.ok(authoritativeDistance.miles < 40, `unexpected Sterling distance ${authoritativeDistance.miles}`);

require("./results-language.test.cjs");
require("./apply-next.test.cjs");
require("./apply-next-ui.test.cjs");
console.log("frontend-utils tests passed");
