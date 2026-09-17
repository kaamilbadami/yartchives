#!/usr/bin/env node
"use strict";

/**
 * Audit the checked-in Apply Next recommendation funnel without making network requests.
 *
 * The audit deliberately separates recommendation recall from inspection-evidence
 * coverage. A job can be absent from the bounded inspection queue while remaining
 * eligible for metadata-backed ranking; those are different outcomes and must not be
 * collapsed into one "dropped" count.
 */

const fs = require("node:fs");
const path = require("node:path");
// apply-next-dimensions is the final scoring/ranking layer loaded before the UI.
// Its CommonJS dependency chain includes the authoritative/location gate.
const ApplyNext = require("../apply-next-dimensions.js");
const ApplyNextLocation = require("../apply-next-location.js");
const ApplyNextUI = require("../apply-next-ui.js");

const ROOT = path.resolve(__dirname, "..");
const DEFAULT_FEED = path.join(ROOT, "data", "listings.json");
const DEFAULT_CACHE = path.join(ROOT, "data", "workday-inspections.json");
const DEFAULT_PROFILE = path.join(ROOT, "audit", "apply-next-cs-profile.json");
const REQUIREMENT_FIELDS = [
  "graduation",
  "education",
  "student_status",
  "major_fields",
  "citizenship",
  "work_authorization",
  "skills",
  "other_eligibility",
];

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function countBy(values, keyFn) {
  const result = {};
  for (const value of values) {
    const key = keyFn(value) || "unknown";
    result[key] = (result[key] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(result).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}

function jobSummary(job) {
  return {
    id: job?.id || null,
    company: job?.company || null,
    title: job?.title || null,
    term: job?.term || null,
    url: job?.url || null,
  };
}

function examples(jobs, limit = 5) {
  return jobs.slice(0, limit).map(jobSummary);
}

function isRelevant(job, profile) {
  const wantedProfiles = new Set((profile?.preferredProfiles || []).map(normalize).filter(Boolean));
  if (!wantedProfiles.size) return true;
  return (job?.profiles || []).some(value => wantedProfiles.has(normalize(value)));
}

function requirementKnown(field) {
  if (!field || typeof field !== "object") return false;
  if (field.classification && field.classification !== "unknown") return true;
  return ["required", "preferred", "unspecified", "not_required"]
    .some(bucket => Array.isArray(field[bucket]) && field[bucket].length > 0);
}

function semanticCoverage(inspection) {
  if (!inspection || inspection.status !== "inspected") {
    return { known_fields: 0, unknown_fields: REQUIREMENT_FIELDS.length, mostly_unknown: false };
  }
  const requirements = inspection.requirements && typeof inspection.requirements === "object"
    ? inspection.requirements
    : {};
  const known = REQUIREMENT_FIELDS.filter(key => requirementKnown(requirements[key]));
  const unknown = REQUIREMENT_FIELDS.filter(key => !known.includes(key));
  return {
    known_fields: known.length,
    unknown_fields: unknown.length,
    known_field_names: known,
    unknown_field_names: unknown,
    mostly_unknown: unknown.length > known.length,
  };
}

function applicationUnavailable(inspection) {
  return inspection?.status === "unavailable"
    || inspection?.posting?.application_status === "unavailable";
}

function inspectionClassification(job, cache) {
  const canonical = cache?.listing_index?.[job?.id] || null;
  const entry = canonical ? cache?.entries?.[canonical] : null;
  const inspection = entry?.inspection || job?._inspection || null;
  const queueState = inspection?.queue?.state || cache?.queue?.[canonical]?.state || null;
  const status = inspection?.status || null;

  if (!canonical) {
    let host = "no-authoritative-url";
    try {
      host = new URL(job?.url || "").hostname.toLowerCase() || host;
    } catch (_) {
      // The source shape itself is the useful classification.
    }
    return {
      selected: false,
      state: "not_selected",
      blocker: "unsupported_provider_or_source_shape",
      provider_or_shape: job?.link_kind && job.link_kind !== "direct" ? job.link_kind : host,
      canonical_url: null,
      semantic: null,
    };
  }

  if (applicationUnavailable(inspection)) {
    return {
      selected: true,
      state: "authoritative_posting_unavailable",
      blocker: "authoritative_posting_unavailable",
      provider_or_shape: entry?.provider || inspection?.provider || "unknown",
      canonical_url: canonical,
      semantic: null,
    };
  }

  if (status === "inspected") {
    const semantic = semanticCoverage(inspection);
    return {
      selected: true,
      state: semantic.mostly_unknown ? "inspected_semantically_thin" : "inspected",
      blocker: semantic.mostly_unknown ? "inspected_semantically_thin" : null,
      provider_or_shape: entry?.provider || inspection?.provider || "unknown",
      canonical_url: canonical,
      semantic,
    };
  }

  if (status === "unsupported_url" || queueState === "unsupported_url") {
    return {
      selected: true,
      state: "unsupported_provider_or_source_shape",
      blocker: "unsupported_provider_or_source_shape",
      provider_or_shape: entry?.provider || inspection?.provider || "unknown",
      canonical_url: canonical,
      semantic: null,
    };
  }

  if (queueState === "retry_cooldown" || ["failed", "changed_response"].includes(status)) {
    return {
      selected: true,
      state: "inspection_retrieval_failure_or_cooldown",
      blocker: "inspection_retrieval_failure_or_cooldown",
      provider_or_shape: entry?.provider || inspection?.provider || "unknown",
      canonical_url: canonical,
      semantic: null,
    };
  }

  if (status === "queued" || queueState === "queued") {
    return {
      selected: true,
      state: "queued_bounded_throughput",
      blocker: "queued_bounded_throughput",
      provider_or_shape: entry?.provider || inspection?.provider || "unknown",
      canonical_url: canonical,
      semantic: null,
    };
  }

  return {
    selected: true,
    state: "inspection_state_unknown",
    blocker: "inspection_state_unknown",
    provider_or_shape: entry?.provider || inspection?.provider || "unknown",
    canonical_url: canonical,
    semantic: null,
  };
}

function exclusionReason(score) {
  const text = [
    ...(score?.reasons || []),
    ...(score?.readiness?.details || []),
    score?.components?.eligibility?.detail,
  ].filter(Boolean).join(" ").toLowerCase();
  if (text.includes("unavailable")) return "authoritative_posting_unavailable";
  if (text.includes("known eligibility conflict") || text.includes("known requirement conflict")) {
    return "known_eligibility_conflict";
  }
  if (text.includes("graduate-only")) return "known_ineligible_graduate_only";
  if (text.includes("outside the target set")) return "known_ineligible_opportunity_type";
  return "known_ineligible_other";
}

function detectAuthoritativeGate(profile, reference) {
  const probe = {
    id: "audit-metadata-probe",
    company: "Audit probe",
    title: "Software Engineering Intern",
    profiles: profile?.preferredProfiles?.length ? [profile.preferredProfiles[0]] : ["cs"],
    states: ["US"],
    term: profile?.targetTerm || null,
    opportunity_type: profile?.opportunityTypes?.[0] || "internship",
    education_level: "undergrad",
    posted_at: reference.toISOString(),
    link_kind: "direct",
    url: "https://audit.invalid/jobs/metadata-only",
  };
  return ApplyNext.rankJobs([probe], profile, reference).length === 0;
}

function auditFunnel(feed, cache, profile, options = {}) {
  const topN = Math.max(1, Number(options.topN || 10));
  const referenceValue = options.reference
    || cache?.updated_at
    || feed?.generated_at
    || new Date().toISOString();
  const reference = new Date(referenceValue);
  if (!Number.isFinite(reference.getTime())) throw new Error(`Invalid audit reference time: ${referenceValue}`);

  const jobs = (Array.isArray(feed?.jobs) ? feed.jobs : [])
    .filter(job => job && typeof job === "object")
    .map(job => ({ ...job }));
  ApplyNextUI.attachInspections(jobs, cache || {});

  const relevant = jobs.filter(job => isRelevant(job, profile));
  const irrelevant = jobs.filter(job => !isRelevant(job, profile));
  const wrongTerm = relevant.filter(job => ApplyNextUI.knownWrongTerm(job, profile));
  const termCandidates = relevant.filter(job => !ApplyNextUI.knownWrongTerm(job, profile));

  const scored = termCandidates.map(job => ({ job, score: ApplyNext.scoreJob(job, profile, reference) }));
  const ineligible = scored.filter(item => item.score.excluded);
  const eligible = scored.filter(item => !item.score.excluded).map(item => item.job);
  const ineligibleByReason = countBy(ineligible, item => exclusionReason(item.score));

  const inspectionRows = termCandidates.map(job => ({ job, ...inspectionClassification(job, cache || {}) }));
  const eligibleIds = new Set(eligible.map(job => job.id));
  const eligibleInspectionRows = inspectionRows.filter(row => eligibleIds.has(row.job.id));
  const selected = eligibleInspectionRows.filter(row => row.selected);
  const notSelected = eligibleInspectionRows.filter(row => !row.selected);
  const inspectionStates = countBy(inspectionRows, row => row.state);
  const eligibleInspectionStates = countBy(eligibleInspectionRows, row => row.state);
  const unsupportedBreakdown = countBy(
    eligibleInspectionRows.filter(row => row.blocker === "unsupported_provider_or_source_shape"),
    row => row.provider_or_shape,
  );

  const detectedAuthoritativeGate = detectAuthoritativeGate(profile, reference);
  const hasGateOverride = typeof options.authoritativeOnly === "boolean";
  const requiresAuthoritativeInspection = hasGateOverride
    ? options.authoritativeOnly
    : detectedAuthoritativeGate;
  const authoritativeReady = new Set(eligibleInspectionRows
    .filter(row => row.state === "inspected" || row.state === "inspected_semantically_thin")
    .map(row => row.job.id));
  const counterfactualAuthoritativeExclusions = eligible.filter(job => !authoritativeReady.has(job.id));
  const afterGate = requiresAuthoritativeInspection
    ? eligible.filter(job => authoritativeReady.has(job.id))
    : eligible;

  const dedupedForRanking = ApplyNextLocation.dedupeCanonicalJobs(afterGate);
  const ranked = ApplyNext.rankJobs(afterGate, profile, reference);
  const rankedIds = new Set(ranked.map(result => result.job.id));
  const rankingExcluded = afterGate.filter(job => !rankedIds.has(job.id));
  const visible = ranked.slice(0, topN);
  const belowVisible = ranked.slice(topN);

  const blockerCounts = {
    relevant_but_not_selected_for_inspection: notSelected.length,
    queued_bounded_throughput: eligibleInspectionStates.queued_bounded_throughput || 0,
    inspection_retrieval_failure_or_cooldown: eligibleInspectionStates.inspection_retrieval_failure_or_cooldown || 0,
    unsupported_provider_or_source_shape: eligibleInspectionRows
      .filter(row => row.blocker === "unsupported_provider_or_source_shape").length,
    authoritative_posting_unavailable: inspectionStates.authoritative_posting_unavailable || 0,
    inspected_semantically_thin: eligibleInspectionStates.inspected_semantically_thin || 0,
    excluded_solely_by_authoritative_gate: requiresAuthoritativeInspection
      ? counterfactualAuthoritativeExclusions.length
      : 0,
    ranked_below_visible_set: belowVisible.length,
  };
  const evidenceBottleneckCandidates = Object.entries(blockerCounts)
    .filter(([key]) => ![
      "relevant_but_not_selected_for_inspection",
      "ranked_below_visible_set",
      "excluded_solely_by_authoritative_gate",
    ].includes(key));
  const biggestEvidenceBottleneck = evidenceBottleneckCandidates
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0] || ["none", 0];

  return {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    inputs: {
      feed_generated_at: feed?.generated_at || null,
      cache_updated_at: cache?.updated_at || null,
      reference_time: reference.toISOString(),
      target_term: profile?.targetTerm || null,
      relevance_profiles: profile?.preferredProfiles || [],
      top_n: topN,
      local_applied_or_hidden_jobs: 0,
    },
    product_behavior: {
      authoritative_only_gate_active: requiresAuthoritativeInspection,
      authoritative_only_gate_detected_in_code: detectedAuthoritativeGate,
      authoritative_only_gate_override: hasGateOverride ? requiresAuthoritativeInspection : null,
      metadata_only_jobs_can_rank: !requiresAuthoritativeInspection,
      unknown_inspection_evidence_is_a_hard_exclusion: requiresAuthoritativeInspection,
    },
    funnel: {
      full_feed: { entered: jobs.length, retained: jobs.length, dropped: 0 },
      relevance_filter: {
        entered: jobs.length,
        retained: relevant.length,
        dropped: irrelevant.length,
        reasons: { genuinely_irrelevant_for_selected_profiles: irrelevant.length },
      },
      term_and_eligibility_filter: {
        entered: relevant.length,
        retained: eligible.length,
        dropped: wrongTerm.length + ineligible.length,
        reasons: {
          known_wrong_term: wrongTerm.length,
          ...ineligibleByReason,
        },
      },
      inspection_candidate_pool: {
        entered: eligible.length,
        selected_for_inspection: selected.length,
        relevant_but_not_selected: notSelected.length,
        recommendation_candidates_retained: eligible.length,
        note: "Inspection selection affects evidence coverage, not recommendation eligibility.",
      },
      inspection_state: {
        all_term_candidates: inspectionStates,
        eligible_candidates: eligibleInspectionStates,
      },
      authoritative_only_gate: {
        entered: eligible.length,
        active: requiresAuthoritativeInspection,
        retained: afterGate.length,
        dropped: eligible.length - afterGate.length,
        excluded_solely_because_authoritative_inspection_is_required: requiresAuthoritativeInspection
          ? counterfactualAuthoritativeExclusions.length
          : 0,
        counterfactual_excluded_if_gate_were_enabled: counterfactualAuthoritativeExclusions.length,
      },
      ranking: {
        entered: afterGate.length,
        ranked: ranked.length,
        dropped: rankingExcluded.length,
        reasons: {
          canonical_duplicate: afterGate.length - dedupedForRanking.length,
          scoring_or_location_exclusion: dedupedForRanking.length - ranked.length,
        },
      },
      visible_top_n: {
        entered: ranked.length,
        visible: visible.length,
        ranked_but_below_visible_set: belowVisible.length,
      },
    },
    classifications: blockerCounts,
    inspection_unsupported_breakdown: unsupportedBreakdown,
    biggest_evidence_bottleneck: {
      classification: biggestEvidenceBottleneck[0],
      count: biggestEvidenceBottleneck[1],
    },
    examples: {
      irrelevant: examples(irrelevant),
      wrong_term: examples(wrongTerm),
      known_ineligible: ineligible.slice(0, 5).map(item => ({
        ...jobSummary(item.job),
        reason: exclusionReason(item.score),
        detail: item.score.reasons?.[0] || item.score.readiness?.details?.[0] || null,
      })),
      not_selected_for_inspection: examples(notSelected.map(row => row.job)),
      queued_bounded_throughput: examples(eligibleInspectionRows
        .filter(row => row.state === "queued_bounded_throughput").map(row => row.job)),
      retrieval_failure_or_cooldown: examples(eligibleInspectionRows
        .filter(row => row.state === "inspection_retrieval_failure_or_cooldown").map(row => row.job)),
      unsupported_provider_or_source_shape: examples(eligibleInspectionRows
        .filter(row => row.blocker === "unsupported_provider_or_source_shape").map(row => row.job)),
      authoritative_posting_unavailable: examples(inspectionRows
        .filter(row => row.state === "authoritative_posting_unavailable").map(row => row.job)),
      inspected_semantically_thin: eligibleInspectionRows
        .filter(row => row.state === "inspected_semantically_thin")
        .slice(0, 5)
        .map(row => ({ ...jobSummary(row.job), semantic: row.semantic })),
      top_n: visible.map((result, index) => ({
        rank: index + 1,
        score: result.total,
        inspection_state: inspectionClassification(result.job, cache || {}).state,
        ...jobSummary(result.job),
      })),
      first_below_top_n: belowVisible.slice(0, 5).map((result, index) => ({
        rank: topN + index + 1,
        score: result.total,
        inspection_state: inspectionClassification(result.job, cache || {}).state,
        ...jobSummary(result.job),
      })),
    },
  };
}

function humanSummary(report) {
  const funnel = report.funnel;
  const states = funnel.inspection_state.eligible_candidates;
  const topUnsupported = Object.entries(report.inspection_unsupported_breakdown).slice(0, 5);
  const gateWasForced = report.product_behavior.authoritative_only_gate_override === true
    && !report.product_behavior.authoritative_only_gate_detected_in_code;
  const gateLabel = funnel.authoritative_only_gate.active
    ? (gateWasForced ? "modeled baseline" : "active")
    : "not active";
  const lines = [
    "# Apply Next recall audit",
    "",
    `Feed snapshot: ${report.inputs.feed_generated_at || "unknown"}; inspection cache: ${report.inputs.cache_updated_at || "unknown"}.`,
    `Audit profile: ${(report.inputs.relevance_profiles || []).join(", ") || "all profiles"}; target term: ${report.inputs.target_term || "none"}; visible set: Top ${report.inputs.top_n}.`,
    "",
    "## Funnel",
    "",
    `- Full feed: ${funnel.full_feed.entered.toLocaleString()}.`,
    `- Relevant: ${funnel.relevance_filter.retained.toLocaleString()} retained; ${funnel.relevance_filter.dropped.toLocaleString()} genuinely outside the selected profile tags.`,
    `- Term / eligibility: ${funnel.term_and_eligibility_filter.retained.toLocaleString()} retained; ${funnel.term_and_eligibility_filter.reasons.known_wrong_term.toLocaleString()} known wrong-term and ${(funnel.term_and_eligibility_filter.dropped - funnel.term_and_eligibility_filter.reasons.known_wrong_term).toLocaleString()} known-ineligible/unavailable removed.`,
    `- Inspection pool: ${funnel.inspection_candidate_pool.selected_for_inspection.toLocaleString()} selected; ${funnel.inspection_candidate_pool.relevant_but_not_selected.toLocaleString()} relevant candidates have no inspection candidate mapping.`,
    `- Inspection state (eligible candidates): ${(states.inspected || 0).toLocaleString()} inspected with substantive semantics, ${(states.inspected_semantically_thin || 0).toLocaleString()} inspected but mostly unknown, ${(states.queued_bounded_throughput || 0).toLocaleString()} queued, ${(states.inspection_retrieval_failure_or_cooldown || 0).toLocaleString()} failed/cooling down, and ${(states.unsupported_provider_or_source_shape || 0).toLocaleString()} selected with an unsupported shape.`,
    `- Authoritative-only gate: ${gateLabel}; ${funnel.authoritative_only_gate.excluded_solely_because_authoritative_inspection_is_required.toLocaleString()} excluded solely for lacking authoritative inspection (${funnel.authoritative_only_gate.counterfactual_excluded_if_gate_were_enabled.toLocaleString()} would be excluded if such a gate were enabled).`,
    `- Ranking: ${funnel.ranking.ranked.toLocaleString()} ranked; ${funnel.ranking.reasons.canonical_duplicate.toLocaleString()} canonical duplicates collapsed and ${funnel.ranking.reasons.scoring_or_location_exclusion.toLocaleString()} otherwise excluded during ranking; ${funnel.visible_top_n.visible.toLocaleString()} visible and ${funnel.visible_top_n.ranked_but_below_visible_set.toLocaleString()} below Top ${report.inputs.top_n}.`,
    "",
    "## Conclusion",
    "",
    gateWasForced
      ? "This baseline models the authoritative-only behavior inherited from main before the fix; metadata-only candidates are removed before ranking."
      : report.product_behavior.metadata_only_jobs_can_rank
      ? "Current Apply Next does not silently erase metadata-only opportunities: unknown inspection evidence is not a hard mismatch, and metadata-only jobs remain rankable."
      : "Apply Next currently has an authoritative-only gate, so metadata-only candidates are removed before ranking.",
    report.product_behavior.authoritative_only_gate_active
      ? `The largest inspection-evidence bottleneck is **${report.biggest_evidence_bottleneck.classification}** (${report.biggest_evidence_bottleneck.count.toLocaleString()} candidates). Because the authoritative-only gate is active, this evidence limitation contributes directly to recommendation loss.`
      : `The largest inspection-evidence bottleneck is **${report.biggest_evidence_bottleneck.classification}** (${report.biggest_evidence_bottleneck.count.toLocaleString()} candidates). This remains an evidence-coverage limitation, but it is not a hard recommendation exclusion.`,
    `The visible-set bottleneck is the deliberate Top ${report.inputs.top_n} cap: ${funnel.visible_top_n.ranked_but_below_visible_set.toLocaleString()} otherwise-ranked candidates are below it.`,
  ];
  if (topUnsupported.length) {
    lines.push("", "Largest unsupported provider/source-shape buckets:");
    for (const [provider, count] of topUnsupported) lines.push(`- ${provider}: ${count.toLocaleString()}`);
  }
  lines.push("");
  return lines.join("\n");
}

function parseArgs(argv) {
  const args = {
    feed: DEFAULT_FEED,
    cache: DEFAULT_CACHE,
    profile: DEFAULT_PROFILE,
    output: null,
    markdownOutput: null,
    topN: 10,
    reference: null,
    authoritativeOnly: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (key === "--feed") args.feed = path.resolve(value), index += 1;
    else if (key === "--cache") args.cache = path.resolve(value), index += 1;
    else if (key === "--profile") args.profile = path.resolve(value), index += 1;
    else if (key === "--output") args.output = path.resolve(value), index += 1;
    else if (key === "--markdown-output") args.markdownOutput = path.resolve(value), index += 1;
    else if (key === "--top-n") args.topN = Number(value), index += 1;
    else if (key === "--reference") args.reference = value, index += 1;
    else if (key === "--authoritative-only") args.authoritativeOnly = true;
    else if (key === "--help" || key === "-h") args.help = true;
    else throw new Error(`Unknown argument: ${key}`);
  }
  return args;
}

function usage() {
  return [
    "Usage: node scripts/apply_next_recall_audit.cjs [options]",
    "",
    "Options:",
    "  --feed PATH              Feed JSON (default: data/listings.json)",
    "  --cache PATH             Inspection cache JSON (default: data/workday-inspections.json)",
    "  --profile PATH           Apply Next profile JSON (default: audit/apply-next-cs-profile.json)",
    "  --output PATH            Write machine-readable JSON",
    "  --markdown-output PATH   Write concise Markdown summary",
    "  --top-n N                Visible recommendation count (default: 10)",
    "  --reference ISO_TIME     Override scoring reference time",
    "  --authoritative-only     Model the former authoritative-only gate for comparison",
  ].join("\n");
}

function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.help) {
    process.stdout.write(`${usage()}\n`);
    return 0;
  }
  const report = auditFunnel(readJson(args.feed), readJson(args.cache), readJson(args.profile), {
    topN: args.topN,
    reference: args.reference,
    authoritativeOnly: args.authoritativeOnly,
  });
  const summary = humanSummary(report);
  if (args.output) {
    fs.mkdirSync(path.dirname(args.output), { recursive: true });
    fs.writeFileSync(args.output, `${JSON.stringify(report, null, 2)}\n`);
  }
  if (args.markdownOutput) {
    fs.mkdirSync(path.dirname(args.markdownOutput), { recursive: true });
    fs.writeFileSync(args.markdownOutput, summary);
  }
  process.stdout.write(summary);
  return 0;
}

module.exports = {
  REQUIREMENT_FIELDS,
  isRelevant,
  semanticCoverage,
  inspectionClassification,
  exclusionReason,
  detectAuthoritativeGate,
  auditFunnel,
  humanSummary,
  parseArgs,
};

if (require.main === module) {
  try {
    process.exitCode = main();
  } catch (error) {
    process.stderr.write(`${error.stack || error.message}\n`);
    process.exitCode = 1;
  }
}
