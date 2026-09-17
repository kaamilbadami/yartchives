const assert = require("node:assert/strict");
const P = require("../apply-next-presentation.js");

let priorCalls = 0;
const scope = {
  YartchivesUtils: null,
  distanceForJob(job) {
    priorCalls += 1;
    job._applyNextAnchorDistanceSamples = [{ distanceMiles: 12 }];
    return 12;
  },
};

assert.equal(P.captureMatchedLocationPoints(scope), true);
assert.equal(P.captureMatchedLocationPoints(scope), true, "capture wrapper should be idempotent");
assert.equal(typeof scope.distanceForJob, "function");
const job = {};
assert.equal(scope.distanceForJob(job, { city: "college park", state: "MD" }, {}), 12);
assert.equal(priorCalls, 1);

console.log("apply-next presentation browser hook tests passed");
