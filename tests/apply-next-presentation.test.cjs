const assert = require("node:assert/strict");
const P = require("../apply-next-presentation.js");

const canonicalCisco = "https://cisco.wd5.myworkdayjobs.com/Cisco_Careers/job/RTP-North-Carolina-US/Software-Engineer-I--Intern----United-States_2025890";
const rewrittenCisco = "https://cisco.wd5.myworkdayjobs.com/cisco_careers/job/RTP-North-Carolina-US/Software-Engineer-I-Intern-United-States_2025890";
const workdayJob = {
  url: rewrittenCisco,
  _inspection: {
    provider: "workday",
    provenance: { canonical_job_url: canonicalCisco },
  },
};
assert.equal(P.canonicalApplyUrl(workdayJob), canonicalCisco, "Workday display links must preserve the inspected canonical path, not synthesize a title slug");

assert.equal(P.humanizeLocationPiece("Medina, Minnesota"), "Medina, MN");
assert.equal(P.humanizeLocationPiece("Innovators Way, Simi Valley,, CA"), "Simi Valley, CA");
assert.equal(P.humanizeLocationPiece("Denver, CO, US"), "Denver, CO");
assert.equal(P.humanizeLocationPiece("RTP, North Carolina, US"), "Rtp, NC");
assert.deepEqual(P.locationPieces({ location: "Medina, Minnesota · Medina" }), ["Medina, MN"]);

const profile = {
  baseZips: ["06897", "20740"],
  nearbyMiles: 50,
};

const aeroResult = {
  job: {
    location: "Simi Valley, CA · Innovators Way, Simi Valley,, CA · Huntsville, AL · Pottstown, PA · Annapolis Junction, MD · Germantown, MD · Arlington, VA",
    _applyNextAnchorDistanceSamples: [
      { distanceMiles: 2450, point: { city: "simi valley", state: "CA" } },
      { distanceMiles: 19, point: { city: "annapolis junction", state: "MD" } },
    ],
  },
  locationDecision: { anchor: "20740" },
};
const aeroDisplay = P.displayLocation(aeroResult, profile);
assert.equal(aeroDisplay.preferred, "Annapolis Junction, MD");
assert.equal(aeroDisplay.all[0], "Annapolis Junction, MD");
assert.match(aeroDisplay.text, /^Annapolis Junction, MD · /);
assert.doesNotMatch(aeroDisplay.text, /\+ \d+ more/);
assert.doesNotMatch(aeroDisplay.text, /Innovators Way/);

const caciResult = {
  job: {
    location: "Denver, CO · Sterling, VA",
    _applyNextAnchorDistanceSamples: [
      { distanceMiles: 1700, point: { city: "denver", state: "CO" } },
      { distanceMiles: 28, point: { city: "sterling", state: "VA" } },
    ],
  },
  locationDecision: { anchor: "20740" },
};
assert.equal(P.displayLocation(caciResult, profile).text, "Sterling, VA · Denver, CO");

const authoritativeCisco = {
  location: "Stamford, CT · RTP, North Carolina, US",
  _inspection: {
    status: "inspected",
    posting: {
      locations: {
        status: "authoritative",
        values: ["RTP, North Carolina, US"],
      },
    },
  },
};
assert.deepEqual(P.locationPieces(authoritativeCisco), ["Rtp, NC"], "authoritative posting locations must replace stale feed metadata for display");

const presented = P.presentResult({
  ...aeroResult,
  job: {
    ...aeroResult.job,
    url: "https://avav.wd1.myworkdayjobs.com/avav/job/Simi-Valley-CA/Summer-2027-Software-Engineering-Intern_8611",
    _inspection: {
      provider: "workday",
      provenance: {
        canonical_job_url: "https://avav.wd1.myworkdayjobs.com/AVAV/job/Simi-Valley-CA/Summer-2027-Software-Engineering-Intern_8611",
      },
    },
  },
}, profile);
assert.equal(presented.job.location.startsWith("Annapolis Junction, MD"), true);
assert.equal(presented.job.url, "https://avav.wd1.myworkdayjobs.com/AVAV/job/Simi-Valley-CA/Summer-2027-Software-Engineering-Intern_8611");

console.log("apply-next presentation tests passed");
