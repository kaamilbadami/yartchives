const assert = require("node:assert/strict");
const fs = require("node:fs");

const index = fs.readFileSync("index.html", "utf8");
const workflow = fs.readFileSync(".github/workflows/deploy-pages.yml", "utf8");

const assets = [...index.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)]
  .map(match => match[1])
  .filter(asset => !/^https?:\/\//i.test(asset));

assert.ok(assets.length > 0, "index.html should reference local JS/CSS assets");

const copyLine = workflow
  .split("\n")
  .map(line => line.trim())
  .find(line => line.startsWith("cp index.html "));
assert.ok(copyLine, "Pages workflow should copy index.html and static assets into _site");

for (const asset of assets) {
  assert.ok(fs.existsSync(asset), `${asset} is referenced by index.html but does not exist`);
  assert.ok(
    copyLine.includes(` ${asset}`),
    `${asset} is referenced by index.html but is not copied into the Pages artifact`
  );
  assert.ok(
    workflow.includes(`- "${asset}"`),
    `${asset} is referenced by index.html but does not trigger a Pages deploy when changed`
  );
  assert.ok(
    workflow.includes(`${asset}?v=\${VERSION}`),
    `${asset} is referenced by index.html but is not cache-busted in the Pages artifact`
  );
}

console.log("deploy asset parity tests passed");
