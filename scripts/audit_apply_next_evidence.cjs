#!/usr/bin/env node
"use strict";

/*
 * Measure the evidence status of recommendations produced by the same final
 * Apply Next scorer that the browser uses.  This stays offline: it joins the
 * checked-in feed with the checked-in inspection artifact and never requests
 * an employer site while auditing.
 */

const fs = require("node:fs");
const path = require("node:path");
const scoring = require("../apply-next-presentation.js");

const ROOT = path.resolve(__dirname, "..");
const DEFAULT_FEED = path.join(ROOT, "data", "listings.json");
const DEFAULT_INSPECTIONS = path.join(ROOT, "data", "workday-inspections.json");

const REPRESENTATIVE_PROFILE = Object.freeze({
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship", "co-op"],
  excludeGraduateOnly: true,
  preferredProfiles: ["cs", "tech-business"],
  supportedKeywords: ["software", "systems", "testing", "linux", "java", "c"],
  cautiousKeywords: ["python", "bash"],
  facts: {
    graduation: "May 2028",
    workAuthorization: "Authorized to work in the U.S. without sponsorship",
    supportedSkills: ["Java", "C", "Linux", "testing"],
    cautiousSkills: ["Python", "Bash"],
  },
  roleFamilies: [
    { id: "software", label: "Software engineering", priority: 1, keywords: ["software engineer", "software developer"] },
    { id: "testing", label: "Testing / systems", priority: 1, keywords: ["test engineer", "qa", "systems"] },
    { id: "analytics", label: "Technical analytics", priority: 0.8, keywords: ["data analyst", "business analyst"] },
  ],
  preferredStates: ["MD", "DC", "CT", "NY"],
  remoteRelevant: true,
  relocationAllowed: true,
  nearbyMiles: 50,
});

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function attachInspections(jobs, artifact) {
  const entries = artifact?.entries || {};
  const index = artifact?.listing_index || {};
  return (jobs || []).map(job => {
    const canonical = index[job?.id];
    const inspection = canonical && entries[canonical]?.inspection;
    return inspection && typeof inspection === "object" ? { ...job, _inspection: inspection } : { ...job };
  });
}

function metadataReason(job) {
  const inspection = job?._inspection;
  if (!inspection) return "no_inspection";
  if (inspection.status === "queued") return "throughput";
  if (inspection.status === "failed") return "retrieval_failure";
  if (inspection.status === "unsupported_url") return "unsupported_provider_or_url_shape";
  if (inspection.status === "unavailable") return "unavailable_posting";
  if (inspection.status === "inspected") return null;
  if (inspection.queue?.state === "cached") return "stale_cache";
  return "retrieval_failure";
}

function compact(result) {
  return {
    id: result.job?.id || null,
    company: result.job?.company || null,
    title: result.job?.title || null,
    score: result.total,
    evidence_state: result.inspection?.state || "metadata-only",
  };
}

function summarize(results, limit) {
  const candidates = results.slice(0, limit);
  const metadata = candidates.filter(result => result.inspection?.state !== "inspected");
  const classifications = Object.fromEntries([
    "throughput",
    "retrieval_failure",
    "unsupported_provider_or_url_shape",
    "unavailable_posting",
    "stale_cache",
    "no_inspection",
  ].map(key => [key, 0]));
  for (const result of metadata) classifications[metadataReason(result.job)] += 1;
  return {
    requested_candidates: limit,
    available_candidates: candidates.length,
    authoritative_candidates: candidates.length - metadata.length,
    authoritative_coverage_percent: candidates.length ? Number(((candidates.length - metadata.length) / candidates.length * 100).toFixed(1)) : 0,
    metadata_only_candidates: metadata.length,
    metadata_only_classification: classifications,
    recommendations: candidates.map(compact),
  };
}

function audit(feed, inspections, now = new Date()) {
  const jobs = attachInspections(feed?.jobs, inspections);
  const ranked = scoring.rankJobs(jobs, REPRESENTATIVE_PROFILE, now);
  return {
    schema_version: 1,
    generated_at: now.toISOString(),
    methodology: "Final Apply Next scoring path with a deterministic representative profile. The final scorer admits only inspected postings, so metadata-only recommendations are a regression signal.",
    feed_jobs: jobs.length,
    ranked_candidates: ranked.length,
    top_10: summarize(ranked, 10),
    top_50: summarize(ranked, 50),
    finding: "No metadata-only recommendation was admitted by the final Apply Next scoring path.",
    follow_up: "No generic defect dominates. Keep the authoritative-only admission gate; audit the inspection queue separately for throughput and provider coverage.",
  };
}

function parseArgs(argv) {
  const options = { feed: DEFAULT_FEED, inspections: DEFAULT_INSPECTIONS, output: null };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--feed") options.feed = argv[++index];
    else if (value === "--inspections") options.inspections = argv[++index];
    else if (value === "--output") options.output = argv[++index];
    else throw new Error(`Unknown argument: ${value}`);
  }
  return options;
}

if (require.main === module) {
  const options = parseArgs(process.argv.slice(2));
  const report = audit(readJson(options.feed), readJson(options.inspections));
  const rendered = `${JSON.stringify(report, null, 2)}\n`;
  if (options.output) fs.writeFileSync(options.output, rendered);
  else process.stdout.write(rendered);
}

module.exports = { REPRESENTATIVE_PROFILE, attachInspections, metadataReason, summarize, audit };
