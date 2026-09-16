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

console.log("deploy asset parity tests passed");
