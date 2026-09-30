const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const index = fs.readFileSync("index.html", "utf8");
const workflow = fs.readFileSync(".github/workflows/deploy-pages.yml", "utf8");

const assets = [...index.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)]
  .map(match => match[1])
  .filter(asset => !/^https?:\/\//i.test(asset));

assert.ok(assets.length > 0, "index.html should reference local JS/CSS assets");
assert.match(workflow, /push:\s*[\s\S]*?branches:\s*[\s\S]*?- main/, "Every main advance should trigger a Pages deploy");
assert.equal(/push:\s*[\s\S]*?paths:\s*/.test(workflow.split("workflow_run:")[0]), false, "Main deploy triggering must not use path filters that can leave production stale");
assert.ok(workflow.includes("cp ./*.js ./*.css _site/"), "Pages artifact should package top-level CSS generically");
assert.ok(workflow.includes("cp ./*.js ./*.css _site/"), "Pages artifact should package top-level JS/CSS generically");
assert.ok(fs.existsSync("service-worker.js"), "persistent deploy notifications require the service worker source");
assert.ok(fs.existsSync("manifest.webmanifest"), "iPhone Home Screen support requires a web app manifest");
const manifest = JSON.parse(fs.readFileSync("manifest.webmanifest", "utf8"));
assert.equal(manifest.display, "standalone", "Home Screen installs should launch as a standalone web app");
assert.equal(manifest.id, "./", "PWA identity should stay stable across deploys");
assert.match(index, /<link rel="manifest" href="manifest\.webmanifest" \/>/, "index should expose the PWA manifest");
assert.match(index, /<link rel="apple-touch-icon" href="assets\/yartchives-hedgehog\.png" \/>/, "iPhone Home Screen installs should use the Yartchives icon");
assert.ok(workflow.includes("cp index.html .nojekyll manifest.webmanifest _site/"), "Pages artifact should package the web app manifest");
assert.ok(workflow.includes("cp index.html .nojekyll manifest.webmanifest _site/"), "Pages artifact should package the PWA manifest");
const serviceWorker = fs.readFileSync("service-worker.js", "utf8");
assert.match(serviceWorker, /addEventListener\("push"/, "service worker should receive background Web Push events");
assert.match(serviceWorker, /registration\.showNotification/, "traditional Web Push should display a notification from the service worker");
assert.match(serviceWorker, /payload\?\.web_push === 8030/, "declarative Web Push payloads should avoid duplicate service-worker notifications");

assert.ok(workflow.includes("for asset in ./*.css ./*.js; do"), "Pages build should cache-bust packaged JS/CSS generically");
assert.ok(workflow.includes('?v=${VERSION}'), "Pages build should append the deployment version to local assets");
assert.match(index, /<meta name="yartchives-build" content="__YARTCHIVES_BUILD_SHA__" \/>/, "index should carry a build marker placeholder");
assert.match(index, /<meta name="yartchives-deployment-id" content="__YARTCHIVES_DEPLOYMENT_ID__" \/>/, "index should carry a unique deployment marker placeholder");
assert.ok(workflow.includes('sed -i "s|__YARTCHIVES_BUILD_SHA__|${BUILD_SHA}|g" _site/index.html'), "Pages build should stamp the exact commit SHA into HTML");
assert.ok(workflow.includes("> _site/deploy-manifest.txt"), "Pages artifact should include a deployment manifest");
assert.match(workflow, /- name: Verify live deployment[\s\S]*?PAGE_URL:[\s\S]*?steps\.deployment\.outputs\.page_url/, "Pages should verify the URL returned by the deployment step");
assert.match(workflow, /LIVE_SHA[\s\S]*?yartchives-build[\s\S]*?BUILD_SHA/, "Pages verification should require the live HTML build marker to match the merged commit");
assert.match(workflow, /DEPLOYMENT_ID="\$\{GITHUB_RUN_ID\}-\$\{GITHUB_RUN_ATTEMPT\}"/, "Pages should assign a unique identity to each deployment attempt");
assert.match(workflow, /LIVE_DEPLOYMENT_ID[\s\S]*?yartchives-deployment-id[\s\S]*?DEPLOYMENT_ID/, "Pages verification should wait for the exact deployment, not merely the same commit SHA");
assert.match(workflow, /deployment_id=\$\{DEPLOYMENT_ID\}|deployment_id=%s/, "Pages manifest/status should persist the unique deployment identity");
assert.match(workflow, /deploy-manifest\.txt[\s\S]*?sha256sum[\s\S]*?Live asset/, "Pages verification should compare live frontend asset hashes with the built artifact");
assert.match(workflow, /deployment-status\.json[\s\S]*?interactive/, "Pages should expose an interactive deployment readiness signal");
assert.match(workflow, /commits\/\$BUILD_SHA\/pulls[\s\S]*?agent\/interactive\//, "Interactive deploys should be inferred from the merged PR branch");
assert.match(workflow, /Send successful deploy push/, "Closed-app pushes should be sent after every verified deployment");
assert.equal(workflow.includes("if: github.event_name == 'push'"), false, "Deploy push delivery should not depend on the workflow trigger type");
assert.match(workflow, /Web Push secrets are not configured; a verified production deploy must not silently skip its notification/);
assert.match(workflow, /Verified deploy notification sent/);
assert.match(workflow, /YARTCHIVES_PUSH_SUBSCRIPTION:[\s\S]*?secrets\.YARTCHIVES_PUSH_SUBSCRIPTION/, "Push subscription must come from Actions secrets");
assert.match(workflow, /YARTCHIVES_VAPID_PRIVATE_KEY:[\s\S]*?secrets\.YARTCHIVES_VAPID_PRIVATE_KEY/, "VAPID private key must come from Actions secrets");
assert.match(workflow, /Verified live Pages deployment[\s\S]*?Send successful deploy push/, "Push delivery must happen only after live deployment verification");

assert.match(workflow, /for attempt in \$\(seq 1 12\)[\s\S]*?sleep 5/, "Live verification should tolerate bounded Pages propagation delay");

assert.match(workflow, /fetch_live\(\)[\s\S]*?--retry 5[\s\S]*?--retry-delay 2[\s\S]*?--retry-max-time 20[\s\S]*?--retry-all-errors/, "Post-deploy verification should retry transient Pages/CDN failures with a bounded helper");
assert.match(workflow, /fetch_live[\s\S]*?deploy-manifest\.txt/, "Deploy manifest verification should use the retry helper");
assert.match(workflow, /fetch_live[\s\S]*?deployment-status\.json/, "Deployment status verification should use the retry helper");
assert.match(workflow, /\*\.js\|\*\.css\)[\s\S]*?fetch_live/, "JS/CSS verification should use the retry helper");
assert.match(workflow, /listings\.json\?verify=\$\{DEPLOYMENT_ID\}[\s\S]*?\/tmp\/live-listings\.json/, "Listings verification should remain explicit and bounded");

for (const asset of assets) {
  assert.ok(fs.existsSync(asset), `${asset} is referenced by index.html but does not exist`);
  assert.equal(asset.includes("/"), false, `${asset} is nested; update the generic Pages asset packaging contract`);
}


const workflowFiles = fs.readdirSync(".github/workflows")
  .filter(name => /\.ya?ml$/i.test(name))
  .sort();
assert.deepEqual(
  workflowFiles,
  ["ai-profile-benchmark.yml", "auto-merge-agent-prs.yml", "autonomous-dispatch.yml", "branch-preflight.yml", "coverage-audit.yml", "coverage-automation.yml", "deploy-pages.yml", "feed-freshness.yml", "quality.yml", "refresh-inspections.yml", "repository-housekeeping.yml", "triage-workflow-failures.yml", "update-feed.yml"],
  "Production workflow set changed; update the workflow-health contract intentionally and do not leave temporary workflows on main"
);

const housekeepingWorkflow = fs.readFileSync(".github/workflows/repository-housekeeping.yml", "utf8");
assert.match(
  housekeepingWorkflow,
  /pull_request:\s*[\s\S]*?types:\s*[\s\S]*?- closed/,
  "Repository housekeeping should run immediately when a pull request closes"
);
assert.match(
  housekeepingWorkflow,
  /schedule:\s*[\s\S]*?- cron: "17 4 \* \* \*"/,
  "Repository housekeeping should retain the daily stale-branch recovery sweep"
);
assert.match(
  housekeepingWorkflow,
  /reconcile-stale-branches:[\s\S]*?gh api[\s\S]*?git\/refs\/heads\/\$branch/,
  "Repository housekeeping should retain safe stale-branch deletion"
);
assert.match(
  housekeepingWorkflow,
  /reconcile-merged-pr-issues:[\s\S]*?github\.event\.pull_request\.merged == true[\s\S]*?python scripts\/reconcile_merged_pr_issues\.py/,
  "Repository housekeeping should reconcile referenced issues only for merged pull requests"
);

const coverageWorkflow = fs.readFileSync(".github/workflows/coverage-audit.yml", "utf8");
const qualityWorkflow = fs.readFileSync(".github/workflows/quality.yml", "utf8");
assert.match(
  qualityWorkflow,
  /cp data\/listings\.json \/tmp\/yartchives-old-listings\.json[\s\S]*?reconcile_workday_duplicates\.py data\/listings\.json[\s\S]*?stabilize_job_ids\.py data\/listings\.json --old-feed \/tmp\/yartchives-old-listings\.json[\s\S]*?validate_feed\.py data\/listings\.json/,
  "Live-source smoke should validate the same post-reconciliation stabilized ID state that production publishes"
);

const qualityRunner = fs.readFileSync("scripts/run_quality_checks.sh", "utf8");
const feedWorkflow = fs.readFileSync(".github/workflows/update-feed.yml", "utf8");
const autonomousWorkflow = fs.readFileSync(".github/workflows/autonomous-dispatch.yml", "utf8");
const autoMergeWorkflow = fs.readFileSync(".github/workflows/auto-merge-agent-prs.yml", "utf8");
assert.equal(qualityWorkflow.includes("jules-review:"), false, "Routine Quality runs should not spend Jules quota on PR review");
assert.match(
  autoMergeWorkflow,
  /workflow_run\.conclusion == 'success'[\s\S]*?workflow_run\.conclusion == 'action_required'/,
  "Auto-merge recovery should run for successful and action-required Quality completions"
);

assert.match(
  autoMergeWorkflow,
  /workflow_run:[\s\S]*?workflows:[\s\S]*?- Quality checks[\s\S]*?types:[\s\S]*?- completed/,
  "Autonomous PR merger should wake only after Quality checks complete"
);
assert.match(
  autoMergeWorkflow,
  /push:[\s\S]*?branches:[\s\S]*?- main/,
  "Main pushes should continue draining already-green autonomous PRs"
);
assert.match(
  autoMergeWorkflow,
  /actions:\s*write[\s\S]*?contents:\s*write[\s\S]*?pull-requests:\s*write/,
  "Autonomous PR merger needs actions write to redispatch CI plus merge permissions"
);
assert.match(
  autoMergeWorkflow,
  /run:\s*python scripts\/auto_merge_agent_prs\.py/,
  "Autonomous PR merge decisions should stay in tested Python policy"
);
assert.match(
  fs.readFileSync("scripts/auto_merge_agent_prs.py", "utf8"),
  /workflow", "run", "quality\.yml"/,
  "Automated branch updates should explicitly redispatch Quality checks because token-generated PR events are suppressed"
);

assert.match(
  autonomousWorkflow,
  /pull_request:\s*\n\s*types:\s*\n\s*- closed/,
  "Merged pull requests should wake the autonomous dispatcher immediately"
);
assert.match(
  autonomousWorkflow,
  /if:\s*github\.event_name != 'pull_request' \|\| github\.event\.pull_request\.merged == true/,
  "Closed-but-unmerged pull requests should not dispatch backlog work"
);

assert.ok(
  autonomousWorkflow.includes('- cron: "*/5 * * * *"'),
  "Autonomous dispatcher should retain a 5-minute recovery cadence"
);
assert.match(
  autonomousWorkflow,
  /timeout-minutes:\s*14/,
  "Autonomous dispatcher should retain a bounded workflow runtime"
);
assert.ok(
  autonomousWorkflow.includes('JULES_POLL_SECONDS: "30"') &&
    autonomousWorkflow.includes('JULES_WATCH_SECONDS: "780"'),
  "Dispatcher runs should keep a bounded 13-minute watch window to refill freed Jules capacity promptly"
);

for (const name of workflowFiles) {
  if (name === "triage-workflow-failures.yml") continue;
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
for (const [name, content] of [["quality", qualityRunner], ["feed", feedWorkflow]]) {
  assert.ok(
    content.includes(primaryBenchmark),
    `${name} quality path should measure the frozen 142-role Northeast/Mid-Atlantic benchmark`
  );
  assert.equal(
    content.includes(`python scripts/coverage_audit.py ${legacyBenchmark}`),
    false,
    `${name} quality path should not use the 106-role legacy panel as the primary automated benchmark`
  );
}

assert.ok(
  feedWorkflow.includes(`python scripts/refresh_employer_universe.py employer_universe.json ${primaryBenchmark}`),
  "Employer-universe refresh should seed from the same frozen 142-role Northeast/Mid-Atlantic benchmark used for primary coverage measurement"
);
assert.equal(
  feedWorkflow.includes(`python scripts/refresh_employer_universe.py employer_universe.json ${legacyBenchmark}`),
  false,
  "Employer-universe refresh should not remain pinned to the 106-role legacy benchmark"
);

assert.match(
  workflow,
  /workflow_run:[\s\S]*?workflows:[\s\S]*?- Update opportunity feed[\s\S]*?types:[\s\S]*?- completed/,
  "Pages should wake after the feed workflow completes because GITHUB_TOKEN feed commits do not trigger downstream push workflows"
);
assert.equal(
  workflow.includes("github.event.workflow_run.conclusion == 'success'"),
  false,
  "Pages must inspect publishable artifacts even when a later non-publication step fails"
);
assert.equal(
  workflow.includes('- "data/listings.json"') || workflow.includes('- "data/workday-inspections.json"'),
  false,
  "Runtime data publication should not depend on generated-data pushes to main"
);
assert.match(
  workflow,
  /Hydrate latest runtime artifacts[\s\S]*?scripts\/download_latest_feed\.py/,
  "Pages should hydrate the latest successful runtime artifacts before building"
);
assert.match(
  workflow,
  /Hydrate latest runtime artifacts[\s\S]*?id:\s*hydrate[\s\S]*?--defer-stale-feed-if-workflow-active update-feed\.yml/,
  "Pages should defer stale-feed deploys while the feed producer is already active"
);
assert.match(
  workflow,
  /Explain deferred deploy[\s\S]*?steps\.hydrate\.outputs\.deploy_ready == 'false'/,
  "Deferred stale-feed deploys should finish cleanly with an explicit explanation"
);
for (const stepName of [
  "Apply current deterministic feed semantics",
  "Configure Pages",
  "Build static artifact",
  "Upload Pages artifact",
  "Deploy to GitHub Pages",
  "Verify live deployment",
  "Send successful deploy push",
]) {
  assert.ok(
    workflow.includes("- name: " + stepName + "\n        if: steps.hydrate.outputs.deploy_ready != 'false'"),
    stepName + " should be skipped when deployment is deliberately deferred"
  );
}
assert.match(
  workflow,
  /Hydrate latest runtime artifacts[\s\S]*?Apply current deterministic feed semantics[\s\S]*?python scripts\/enrich_feed\.py data\/listings\.json[\s\S]*?Configure Pages/,
  "Pages deploys should reapply current deterministic feed semantics after hydrating runtime data so UI/filter changes cannot race an older feed artifact"
);
assert.match(
  workflow,
  /workflows:[\s\S]*?- Update opportunity feed[\s\S]*?- Refresh bounded inspections/,
  "Pages should redeploy after either runtime artifact producer succeeds"
);
assert.match(
  workflow,
  /group:\s*github-pages[\s\S]*?cancel-in-progress:\s*true/,
  "Pages deployments are replaceable and should keep only the latest commit"
);


const pushSender = fs.readFileSync(path.join(__dirname, "..", "scripts", "send_web_push.py"), "utf8");
assert.match(pushSender, /VAPID_SUBJECT\s*=\s*"mailto:[^"]+"/, "Web Push VAPID subject must be a mailto contact accepted by push providers");
assert.match(pushSender, /::error::Web Push delivery failed:[\s\S]*?return 1/, "Web Push delivery errors must fail instead of producing a false-green deploy notification");
assert.match(pushSender, /--title/, "Web Push sender should support operational alert titles");
assert.match(pushSender, /--body/, "Web Push sender should support operational alert bodies");
assert.match(pushSender, /--tag/, "Web Push sender should support stable alert tags");
const freshnessWorkflow = fs.readFileSync(".github/workflows/feed-freshness.yml", "utf8");
assert.match(freshnessWorkflow, /Send stale-feed phone alert/, "Freshness watchdog should send a phone alert for prolonged staleness");
assert.match(freshnessWorkflow, /steps\.freshness\.outputs\.alert_required == 'true'/, "Phone alerts should respect the watchdog's stale threshold output");
assert.match(freshnessWorkflow, /YARTCHIVES_PUSH_SUBSCRIPTION:[\s\S]*?secrets\.YARTCHIVES_PUSH_SUBSCRIPTION/, "Stale-feed alerts should reuse the configured phone push subscription");

console.log("deploy asset and workflow health contract tests passed");
