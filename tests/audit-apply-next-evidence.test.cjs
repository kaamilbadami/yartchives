const assert = require("node:assert/strict");
const audit = require("../scripts/audit_apply_next_evidence.cjs");

assert.equal(audit.metadataReason({}), "no_inspection");
assert.equal(audit.metadataReason({ _inspection: { status: "queued" } }), "throughput");
assert.equal(audit.metadataReason({ _inspection: { status: "failed" } }), "retrieval_failure");
assert.equal(audit.metadataReason({ _inspection: { status: "unsupported_url" } }), "unsupported_provider_or_url_shape");
assert.equal(audit.metadataReason({ _inspection: { status: "unavailable" } }), "unavailable_posting");

const inspected = {
  id: "inspected", company: "Inspected", title: "Software Engineer Intern", profiles: ["cs"], states: ["CT"],
  location: "Hartford, CT", term: "Summer 2027", opportunity_type: "internship", link_kind: "direct",
  url: "https://job-boards.greenhouse.io/example/jobs/1",
};
const metadata = { ...inspected, id: "metadata", company: "Metadata", url: "https://example.test/jobs/2" };
const inspectedUrl = "https://job-boards.greenhouse.io/example/jobs/1";
const report = audit.audit({ jobs: [inspected, metadata] }, {
  entries: { [inspectedUrl]: { inspection: { status: "inspected", posting: { application_status: "available" }, requirements: {} } } },
  listing_index: { inspected: inspectedUrl },
}, new Date("2026-09-18T00:00:00Z"));

assert.equal(report.ranked_candidates, 1);
assert.equal(report.top_10.authoritative_coverage_percent, 100);
assert.equal(report.top_10.metadata_only_candidates, 0);
assert.equal(report.top_10.recommendations[0].id, "inspected");
console.log("Apply Next evidence audit tests passed");
