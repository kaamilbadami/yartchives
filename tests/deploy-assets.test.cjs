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
assert.match(
  feedWorkflow,
  /group:\s*update-opportunity-feed[\s\S]*?queue:\s*single/,
  "Feed refreshes should keep only the newest pending run while one protected run finishes"
);
assert.match(
  feedWorkflow,
  /timeout-minutes:\s*45/,
  "The feed build should have an explicit upper runtime bound"
);

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
