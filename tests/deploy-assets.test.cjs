const assert = require("node:assert/strict");
const fs = require("node:fs");

const index = fs.readFileSync("index.html", "utf8");
const workflow = fs.readFileSync(".github/workflows/deploy-pages.yml", "utf8");

const assets = [...index.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)]
  .map(match => match[1])
  .filter(asset => !/^https?:\/\//i.test(asset));

assert.ok(assets.length > 0, "index.html should reference local JS/CSS assets");
assert.ok(workflow.includes('- "*.js"'), "top-level JS changes should trigger a Pages deploy");
assert.ok(workflow.includes('- "*.css"'), "top-level CSS changes should trigger a Pages deploy");
assert.ok(workflow.includes("cp ./*.js ./*.css _site/"), "Pages artifact should package top-level JS/CSS generically");
assert.ok(workflow.includes("for asset in ./*.css ./*.js; do"), "Pages build should cache-bust packaged JS/CSS generically");
assert.ok(workflow.includes('?v=${VERSION}'), "Pages build should append the deployment version to local assets");

for (const asset of assets) {
  assert.ok(fs.existsSync(asset), `${asset} is referenced by index.html but does not exist`);
  assert.equal(asset.includes("/"), false, `${asset} is nested; update the generic Pages asset packaging contract`);
}


const workflowFiles = fs.readdirSync(".github/workflows")
  .filter(name => /\.ya?ml$/i.test(name))
  .sort();
assert.deepEqual(
  workflowFiles,
  ["coverage-audit.yml", "deploy-pages.yml", "quality.yml", "update-feed.yml"],
  "Production workflow set changed; update the workflow-health contract intentionally and do not leave temporary workflows on main"
);

const coverageWorkflow = fs.readFileSync(".github/workflows/coverage-audit.yml", "utf8");
const qualityWorkflow = fs.readFileSync(".github/workflows/quality.yml", "utf8");
const feedWorkflow = fs.readFileSync(".github/workflows/update-feed.yml", "utf8");

for (const name of workflowFiles) {
  const content = fs.readFileSync(`.github/workflows/${name}`, "utf8");
  assert.match(content, /\n\s*workflow_dispatch:/, `${name} should remain manually runnable for recovery/diagnosis`);
}

assert.match(
  coverageWorkflow,
  /group:\s*coverage-audit-\$\{\{ github\.ref \}\}[\s\S]*?cancel-in-progress:\s*false/,
  "Coverage audits should finish rather than lose an audit result to a newer sample push"
);

assert.match(
  qualityWorkflow,
  /group:\s*quality-\$\{\{ github\.ref \}\}[\s\S]*?cancel-in-progress:\s*true/,
  "Replaceable quality runs should cancel superseded runs on the same ref"
);

assert.match(
  feedWorkflow,
  /group:\s*update-opportunity-feed[\s\S]*?cancel-in-progress:\s*false/,
  "The active state-producing feed refresh must finish instead of being cancelled by newer pushes"
);
assert.equal(
  /\n\s*queue:\s*/.test(feedWorkflow),
  false,
  "GitHub concurrency has no queue key; cancel-in-progress=false provides one protected active run plus the latest pending run"
);
assert.match(
  feedWorkflow,
  /python scripts\/parallel_ats_collect\.py data\/listings\.json/,
  "Workday, iCIMS, Greenhouse, and Oracle collection should use the parallel ATS orchestrator"
);
for (const serialCommand of [
  "python scripts/direct_ct_workday.py data/listings.json",
  "python scripts/direct_icims.py data/listings.json",
  "python scripts/direct_greenhouse.py data/listings.json",
  "python scripts/direct_oracle.py data/listings.json",
]) {
  assert.equal(
    feedWorkflow.includes(serialCommand),
    false,
    `Feed workflow should not serialize ATS collector: ${serialCommand}`
  );
}
assert.match(
  feedWorkflow,
  /timeout-minutes:\s*45/,
  "The feed build should have an explicit upper runtime bound"
);

const primaryBenchmark = "audit/samples/northeast-midatlantic-cs-2026-09-17.json";
const legacyBenchmark = "audit/samples/ct-ny-md-dc-cs-2026-09-17.json";
for (const [name, content] of [["quality", qualityWorkflow], ["feed", feedWorkflow]]) {
  assert.ok(
    content.includes(primaryBenchmark),
    `${name} workflow should measure the frozen 142-role Northeast/Mid-Atlantic benchmark`
  );
  assert.equal(
    content.includes(`python scripts/coverage_audit.py ${legacyBenchmark}`),
    false,
    `${name} workflow should not use the 106-role legacy panel as the primary automated benchmark`
  );
}

assert.equal(
  /\n\s*workflow_run:\s*\n/.test(workflow),
  false,
  "Pages should not start shell workflows for every feed completion; the successful feed commit already triggers deployment"
);
assert.equal(
  /github\.event\.workflow_run/.test(workflow),
  false,
  "Pages should not depend on upstream workflow completion state"
);
assert.ok(
  workflow.includes('- "data/listings.json"') && workflow.includes('- "data/workday-inspections.json"'),
  "Successful feed commits must directly trigger Pages deployment"
);
assert.match(
  workflow,
  /group:\s*github-pages[\s\S]*?cancel-in-progress:\s*true/,
  "Pages deployments are replaceable and should keep only the latest commit"
);

console.log("deploy asset and workflow health contract tests passed");
