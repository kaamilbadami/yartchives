const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM } = require('jsdom');

const dom = new JSDOM(`<!DOCTYPE html>
<html>
<body>
  <input id="searchInput">
  <input id="locationInput">
  <input id="radiusInput">
  <select id="freshnessSelect"></select>
  <select id="statusSelect"></select>
  <div class="quick-locations"></div>
  <div id="jobs"></div>
  <div id="profileChips"></div>
  <div id="shownCount"></div>
  <div id="totalCount"></div>
  <div id="savedCount"></div>
  <div id="newCount"></div>
  <div id="hiddenCount"></div>
  <div id="resultsNote"></div>
  <div id="errorBox"></div>
  <div id="feedMeta"></div>
  <button id="clearFiltersBtn"></button>
  <button id="loadMoreBtn"></button>
  <h1 id="resultsTitle"></h1>
  <template id="jobCardTemplate">
    <div class="job-card">
        <button class="save-btn"></button>
        <button class="applied-btn"></button>
        <button class="hide-btn"></button>
        <a class="apply-btn"></a>
        <div class="job-title"></div>
        <div class="job-company"></div>
    </div>
  </template>
</body>
</html>`, { url: 'http://localhost/' });

const window = dom.window;
const document = window.document;

const context = {
  window,
  document,
  console,
  localStorage: {
    data: {},
    getItem(key) { return this.data[key] || null; },
    setItem(key, val) { this.data[key] = String(val); }
  },
  location: window.location,
  URLSearchParams: window.URLSearchParams,
  Set, Map, Array, Object, Number, Date, JSON,
  setTimeout: window.setTimeout,
  clearTimeout: window.clearTimeout,
  Math,
  fetch: async () => ({
    ok: true,
    json: async () => feedData
  })
};

context.globalThis = context;
context.window = context;

let feedData = {
  jobs: [
    { id: "job-1", title: "Software Intern", company: "Company A", profiles: ["cs"], posted_at: "2026-09-01T00:00:00Z", location: "NYC" }
  ],
  sources: {},
  generated_at: "2026-09-01T00:00:00Z",
};

const appCode = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const uxCode = fs.readFileSync(path.join(__dirname, "ux.js"), "utf8");

vm.runInNewContext(`
  // Mock missing DOM APIs
  document.createDocumentFragment = () => window.document.createDocumentFragment();
`, context);

vm.runInNewContext(appCode, context);
vm.runInNewContext("globalThis.state = state; globalThis.applyFilters = applyFilters; globalThis.feed = feed; globalThis.boot = boot;", context);

(async () => {
  await context.boot();

  // Set saved, applied, hidden state
  context.state.saved.add("job-1");
  context.state.applied.add("job-1");
  context.state.hidden.add("job-1");
  context.persist();

  console.log("Before refresh:");
  console.log("Saved:", context.state.saved.has("job-1"));
  console.log("Applied:", context.state.applied.has("job-1"));
  console.log("Hidden:", context.state.hidden.has("job-1"));

  // Simulate refresh with changed metadata but same ID
  feedData = {
    jobs: [
      { id: "job-1", title: "Software Engineer Intern", company: "Company A Inc.", profiles: ["cs"], posted_at: "2026-09-01T00:00:00Z", location: "New York, NY" }
    ],
    sources: {},
    generated_at: "2026-09-02T00:00:00Z",
  };

  // Reset state to simulate page reload
  context.state.saved = new Set();
  context.state.applied = new Set();
  context.state.hidden = new Set();

  await context.boot();

  console.log("After refresh:");
  console.log("Saved:", context.state.saved.has("job-1"));
  console.log("Applied:", context.state.applied.has("job-1"));
  console.log("Hidden:", context.state.hidden.has("job-1"));
})();
