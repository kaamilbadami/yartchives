const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const jsdom = new JSDOM(html, { url: "http://localhost" });
const window = jsdom.window;
globalThis.window = window;
globalThis.document = window.document;
globalThis.performance = require("node:perf_hooks").performance;
globalThis.navigator = window.navigator;

const UI = require("../apply-next-ui.js");
const D = require("../apply-next-dimensions.js");
const A = require("../apply-next.js");
globalThis.YartchivesApplyNext = A;

// mock fetch for inspection artifact
globalThis.fetch = async () => ({
  ok: true,
  json: async () => ({}) // empty artifact
});

// Mock environment
let persistenceTime = 0;
const store = new Map();
globalThis.localStorage = {
  getItem: (key) => store.get(key),
  setItem: (key, value) => {
    const s = performance.now();
    store.set(key, value);
    persistenceTime += performance.now() - s;
  },
  removeItem: (key) => store.delete(key),
};
globalThis.applyFilters = () => {};
globalThis.persist = () => {};
globalThis.updateStats = () => {};
globalThis.renderJobs = () => {};

// create dummy jobs
const jobs = [];
for (let i = 0; i < 5000; i++) {
  jobs.push({
    id: `job-${i}`,
    title: `Software Engineer ${i}`,
    company: `Company ${i % 100}`,
    _metadata_normalized_company: `Company ${i % 100}`,
    posted_at: new Date().toISOString(),
    location: "New York, NY",
    states: ["NY"],
    url: `https://example.com/job/${i}`
  });
}

globalThis.feed = { jobs };
globalThis.state = {
  actioned: new Map(),
  hidden: new Map(),
  profile: "all",
  search: "",
  location: ""
};
globalThis.YartchivesUtils = {
  distanceForJob: () => 10
};
globalThis.currentZip = () => "10001";
globalThis.geoIndex = { zips: new Map([["10001", { lat: 40, lon: -73 }]]) };

const profile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship"],
  roleFamilies: [{ id: "software", label: "Software", priority: 1, keywords: ["software"] }],
  baseZips: ["10001"],
  baseLabels: ["Home"],
};

async function runBenchmark() {
  console.log(`Starting benchmark with ${jobs.length} jobs...`);

  const panel = document.createElement("div");
  panel.classList.add("apply-next-panel");
  panel.innerHTML = '<div class="apply-next-list"></div><p class="apply-next-note"></p>';
  document.body.appendChild(panel);

  // Isolate rankJobs cost
  const pool = UI.candidatePool(feed.jobs, profile, state);
  const startRank = performance.now();
  const ranked = A.rankJobs(pool, profile, new Date(), "recommended");
  const endRank = performance.now();
  const rankCost = endRank - startRank;
  console.log(`Ranking cost: ${rankCost.toFixed(2)}ms`);

  // Isolate renderQueue cost (which includes rankJobs again internally)
  const startRender = performance.now();
  await UI.renderQueue(panel, profile);
  const endRender = performance.now();
  const renderCost = endRender - startRender;
  console.log(`Initial renderQueue total: ${renderCost.toFixed(2)}ms`);

  // Measure state transition (Apply) - this calls updateQueueOptimistically
  const startTransition = performance.now();
  UI.updateQueueOptimistically(panel, profile, "job-0");
  const endTransition = performance.now();
  const transitionCost = endTransition - startTransition;
  console.log(`Transition (DOM updateQueueOptimistically): ${transitionCost.toFixed(2)}ms`);
  console.log(`State persistence (mocked setItem): ${persistenceTime.toFixed(2)}ms`);

  // Asserts
  assert.ok(transitionCost < renderCost, "Optimistic transition DOM update should be significantly faster than a full renderQueue");
  assert.ok(transitionCost < 500, "Optimistic transition should complete within a reasonable threshold (< 500ms)");
  assert.ok(renderCost < 1500, "Full renderQueue including ranking on 5000 jobs should not be catastrophically slow");

  console.log("Benchmark passed!");
}

runBenchmark().catch(error => {
  console.error(error);
  process.exit(1);
});
