const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

function createDOMEnvironment() {
  const store = {};
  const localStorage = {
    getItem: key => store[key] || null,
    setItem: (key, val) => (store[key] = String(val)),
    removeItem: key => delete store[key],
    clear: () => { for (const key in store) delete store[key]; }
  };

  class ElementMock {
    constructor(tagName) {
      this.tagName = tagName;
      this.children = [];
      this.classList = {
        add: () => {},
        remove: () => {},
        contains: () => false,
        toggle: () => false,
      };
      this.style = {};
      this.dataset = {};
    }
    appendChild(child) { this.children.push(child); }
    addEventListener() {}
    querySelector() { return new ElementMock("div"); }
    querySelectorAll() { return []; }
    closest() { return new ElementMock("div"); }
    getAttribute() { return null; }
    setAttribute() {}
    click() {}
  }

  const document = {
    createElement: tagName => new ElementMock(tagName),
    createDocumentFragment: () => new ElementMock("fragment"),
    querySelector: () => new ElementMock("div"),
    querySelectorAll: () => [],
    body: new ElementMock("body"),
  };

  return { document, localStorage, store };
}

async function testStateSurvival() {
  const { document, localStorage, store } = createDOMEnvironment();
  let currentFeed = {
    jobs: [
      { id: "job-1", title: "Software Intern", company: "Company A", profiles: ["cs"], posted_at: "2026-09-01T00:00:00Z" }
    ],
    sources: {},
    generated_at: "2026-09-01T00:00:00Z",
  };

  const context = {
    console,
    document,
    localStorage,
    location: { search: "", href: "http://localhost/" },
    URLSearchParams,
    Set,
    Map,
    Array,
    Object,
    Number,
    Date,
    JSON,
    setTimeout: (fn) => fn(),
    clearTimeout: () => {},
    Math,
    fetch: async () => ({
      ok: true,
      json: async () => currentFeed
    })
  };
  context.globalThis = context;
  context.window = context;

  const appCode = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
  vm.runInNewContext(appCode, context);
  vm.runInNewContext("globalThis.state = state; globalThis.applyFilters = applyFilters; globalThis.boot = boot;", context);

  // Initial boot
  await context.boot();

  // Save/Apply/Hide
  context.state.saved.add("job-1");
  context.state.applied.add("job-1");
  context.state.hidden.add("job-1");

  // Need to persist
  vm.runInNewContext("persist();", context);

  // Update feed - simulate feed refresh with mutable metadata
  currentFeed = {
    jobs: [
      { id: "job-1", title: "Software Engineer Intern", company: "Company A Inc.", profiles: ["cs"], posted_at: "2026-09-01T00:00:00Z" }
    ],
    sources: {},
    generated_at: "2026-09-02T00:00:00Z",
  };

  // Reset state variable to simulate reload
  vm.runInNewContext(`
    state.saved = new Set();
    state.applied = new Set();
    state.hidden = new Set();
  `, context);

  // Boot again
  await context.boot();

  assert.ok(context.state.saved.has("job-1"), "Saved state should survive refresh");
  assert.ok(context.state.applied.has("job-1"), "Applied state should survive refresh");
  assert.ok(context.state.hidden.has("job-1"), "Hidden state should survive refresh");

  console.log("Success");
}

testStateSurvival().catch(console.error);
