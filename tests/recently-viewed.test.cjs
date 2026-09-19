const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appSource = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");

let localStore = {};

const sandbox = {
  localStorage: {
    getItem: (k) => localStore[k] || null,
    setItem: (k, v) => { localStore[k] = v; },
  },
  location: { search: "" },
  URLSearchParams: class {
    constructor() {}
    has() { return false; }
  },
  fetch: async () => ({ ok: true, json: async () => ({ jobs: [], sources: {} }) }),
  document: {
    querySelector: (sel) => ({ classList: { toggle: () => {}, add: () => {}, remove: () => {} }, addEventListener: () => {}, appendChild: () => {}, textContent: "" }),
    querySelectorAll: () => [],
    createElement: () => ({ style: {}, classList: { toggle: () => {}, add: () => {}, remove: () => {} }, addEventListener: () => {}, appendChild: () => {} }),
    createDocumentFragment: () => ({ appendChild: () => {} }),
  },
  window: {},
  console: console,
};

vm.createContext(sandbox);
vm.runInContext(appSource + "\nwindow.state = state;\nwindow.trackView = trackView;", sandbox);

const state = sandbox.window.state;
const trackView = sandbox.window.trackView;

assert.equal(state.viewed.length, 0);

// Check trackView
trackView("job-1");
trackView("job-2");
trackView("job-3");
assert.equal(state.viewed[0], "job-3");
assert.equal(state.viewed[1], "job-2");
assert.equal(state.viewed[2], "job-1");
assert.equal(state.viewed.length, 3);

// Check deduplication / bumping to front
trackView("job-2");
assert.equal(state.viewed[0], "job-2");
assert.equal(state.viewed[1], "job-3");
assert.equal(state.viewed[2], "job-1");
assert.equal(state.viewed.length, 3);

// Check bounded to 100
for (let i = 0; i < 150; i++) {
  trackView(`bulk-${i}`);
}
assert.equal(state.viewed.length, 100);
assert.equal(state.viewed[0], "bulk-149");

// Check persistence
const parsedState = JSON.parse(localStore["yartchives-state-v1"]);
assert.equal(parsedState.viewed.length, 100);
assert.equal(parsedState.viewed[0], "bulk-149");

console.log("recently-viewed tests passed");
