const assert = require("node:assert/strict");
const UI = require("../apply-next-ui.js");

const jobs = [{ id: "job-1", posted_at: "2026-09-17T00:00:00Z" }];
const artifact = {
  listing_index: { "job-1": "canonical-1" },
  entries: {
    "canonical-1": {
      inspection: {
        status: "inspected",
        posting: { posted_at: "2026-09-02", posted_on_text: "Posted 15 Days Ago" },
      },
    },
  },
};

UI.attachInspections(jobs, artifact);
assert.equal(jobs[0].posted_at, "2026-09-02");
assert.equal(jobs[0]._postedAtBasis, "authoritative");
assert.equal(jobs[0]._metadataPostedAt, "2026-09-17T00:00:00Z");
assert.equal(UI.formatPostedDate(jobs[0].posted_at), "Posted Sep 2, 2026");

console.log("apply-next authoritative posting date test passed");
