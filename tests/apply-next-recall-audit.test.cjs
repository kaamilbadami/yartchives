const assert = require("node:assert/strict");
const Audit = require("../scripts/apply_next_recall_audit.cjs");

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs"],
  supportedKeywords: ["software"],
  cautiousKeywords: [],
  facts: {
    workAuthorization: "Requires visa sponsorship",
    citizenship: "Not a U.S. citizen",
    securityClearance: "No active clearance",
    supportedSkills: ["Java"],
    cautiousSkills: [],
  },
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer"] },
  ],
  preferredStates: [],
  relocationAllowed: true,
};

function job(id, overrides = {}) {
  return {
    id,
    company: `Company ${id}`,
    title: "Software Engineering Intern",
    profiles: ["cs"],
    states: ["CT"],
    term: "Summer 2027",
    opportunity_type: "internship",
    education_level: "undergrad",
    posted_at: "2026-09-16T12:00:00Z",
    link_kind: "direct",
    url: `https://jobs.example.com/${id}`,
    ...overrides,
  };
}

function field(classification = "unknown", required = []) {
  return { classification, required, preferred: [], unspecified: [], not_required: [] };
}

function inspected(overrides = {}) {
  return {
    status: "inspected",
    posting: { application_status: "available" },
    requirements: Object.fromEntries(Audit.REQUIREMENT_FIELDS.map(key => [key, field()])),
    ...overrides,
  };
}

const jobs = [
  job("irrelevant", { profiles: ["finance-econ"], title: "Finance Intern" }),
  job("wrong-term", { term: "Fall 2027" }),
  job("graduate", { education_level: "graduate-only", title: "Software Intern, PhD" }),
  job("not-selected"),
  job("queued", { url: "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Queued_REQ-1" }),
  job("failed", { url: "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Failed_REQ-2" }),
  job("unsupported", { url: "https://careers-example.icims.com/jobs/search" }),
  job("unavailable", { url: "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Unavailable_REQ-3" }),
  job("thin", { url: "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Thin_REQ-4" }),
  job("rich", { url: "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Rich_REQ-5" }),
  job("conflict", { url: "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Conflict_REQ-6" }),
];

const urls = Object.fromEntries(jobs
  .filter(item => !["irrelevant", "wrong-term", "graduate", "not-selected"].includes(item.id))
  .map(item => [item.id, item.url]));
const richRequirements = Object.fromEntries(Audit.REQUIREMENT_FIELDS.map(key => [
  key,
  field("required", [{ statement: `${key} is required.`, technologies: key === "skills" ? ["Java"] : [] }]),
]));
const conflictRequirements = Object.fromEntries(Audit.REQUIREMENT_FIELDS.map(key => [key, field()]));
conflictRequirements.work_authorization = field("required", [{
  statement: "Applicants must be authorized to work in the U.S.; the company does not sponsor.",
  requirement_state: "required",
  negated: false,
}]);

const cache = {
  updated_at: "2026-09-16T17:30:00Z",
  listing_index: urls,
  entries: {
    [urls.queued]: { provider: "workday", inspection: { status: "queued", queue: { state: "queued" } } },
    [urls.failed]: { provider: "workday", inspection: { status: "failed", queue: { state: "retry_cooldown" } } },
    [urls.unsupported]: { provider: "icims", inspection: { status: "unsupported_url", queue: { state: "unsupported_url" } } },
    [urls.unavailable]: { provider: "workday", inspection: { status: "unavailable", posting: null, requirements: {} } },
    [urls.thin]: { provider: "workday", inspection: inspected() },
    [urls.rich]: { provider: "workday", inspection: inspected({ requirements: richRequirements }) },
    [urls.conflict]: { provider: "workday", inspection: inspected({ requirements: conflictRequirements }) },
  },
};

const report = Audit.auditFunnel({ generated_at: "2026-09-16T17:30:00Z", jobs }, cache, profile, { topN: 1 });

assert.equal(report.funnel.full_feed.entered, 11);
assert.equal(report.funnel.relevance_filter.reasons.genuinely_irrelevant_for_selected_profiles, 1);
assert.equal(report.funnel.term_and_eligibility_filter.reasons.known_wrong_term, 1);
assert.equal(report.funnel.term_and_eligibility_filter.reasons.known_ineligible_graduate_only, 1);
assert.equal(report.funnel.term_and_eligibility_filter.reasons.known_eligibility_conflict, 1);
assert.equal(report.funnel.term_and_eligibility_filter.reasons.authoritative_posting_unavailable, 1);

assert.equal(report.classifications.relevant_but_not_selected_for_inspection, 1);
assert.equal(report.classifications.queued_bounded_throughput, 1);
assert.equal(report.classifications.inspection_retrieval_failure_or_cooldown, 1);
assert.equal(report.classifications.unsupported_provider_or_source_shape, 2);
assert.equal(report.classifications.authoritative_posting_unavailable, 1);
assert.equal(report.classifications.inspected_semantically_thin, 1);

assert.equal(report.product_behavior.authoritative_only_gate_active, false);
assert.equal(report.classifications.excluded_solely_by_authoritative_gate, 0);
assert.ok(report.funnel.authoritative_only_gate.counterfactual_excluded_if_gate_were_enabled > 0);
assert.equal(report.funnel.ranking.dropped, 0);
assert.equal(report.funnel.visible_top_n.visible, 1);
assert.equal(report.classifications.ranked_below_visible_set, report.funnel.ranking.ranked - 1);

assert.equal(Audit.semanticCoverage(inspected()).mostly_unknown, true);
assert.equal(Audit.semanticCoverage(inspected({ requirements: richRequirements })).mostly_unknown, false);
assert.match(Audit.humanSummary(report), /does not silently erase metadata-only opportunities/i);

console.log("apply-next recall audit tests passed");
