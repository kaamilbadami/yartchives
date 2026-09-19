const assert = require("assert");
const fs = require("fs");
const path = require("path");
const Metrics = require("../apply-next-metrics.js");

(function testMetrics() {
  const rankedPool = [
    { job: { id: "job1" } },
    { job: { id: "job2" } },
    { job: { id: "job3" } },
    { job: { id: "job4" } },
    { job: { id: "job5" } },
    { job: { id: "job6" } },
    { job: { id: "job7" } },
    { job: { id: "job8" } },
    { job: { id: "job9" } },
    { job: { id: "job10" } },
    { job: { id: "job11" } },
  ];

  const localState = {
    applied: new Set(["job1", "job2", "job11"]),
    hidden: new Set(["job3"]),
    saved: new Set(["job4", "job5"]),
  };

  const metrics = Metrics.measureConversion(rankedPool, localState, 10);

  assert.strictEqual(metrics.eligible, 10);
  assert.strictEqual(metrics.applied, 2); // job1, job2
  assert.strictEqual(metrics.hidden, 1); // job3
  assert.strictEqual(metrics.saved, 2); // job4, job5
  assert.strictEqual(metrics.viewedNoAction, 5); // job6-job10
  assert.strictEqual(metrics.conversionRate, 0.2);

  const metricsFile = fs.readFileSync(path.join(__dirname, "..", "apply-next-metrics.js"), "utf8");
  assert.ok(metricsFile.includes("Current Architecture Limitations for Durable Aggregate Measurement"));
  assert.ok(metricsFile.includes("Smallest Future Instrumentation Requirement"));

  console.log("Metrics tests passed!");
})();
