const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Mock Minimal DOM Environment
class ElementMock {
  constructor(tagName = "div", id = "", className = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.style = {};
    this.listeners = {};
    this.value = "";
    this.textContent = "";
    this._innerHTML = "";
    this.disabled = false;
    this.content = null;
    this.classList = {
      _classes: new Set(),
      add: (...names) => names.forEach(n => this.classList._classes.add(n)),
      remove: (...names) => names.forEach(n => this.classList._classes.delete(n)),
      toggle: (name, force) => {
        const has = this.classList._classes.has(name);
        const shouldHave = force !== undefined ? Boolean(force) : !has;
        if (shouldHave) this.classList._classes.add(name);
        else this.classList._classes.delete(name);
        return shouldHave;
      },
      contains: name => this.classList._classes.has(name),
    };
    this.className = className;
  }

  get className() {
    return this._className || "";
  }

  set className(val) {
    this._className = String(val);
    this.classList._classes = new Set(val ? String(val).split(/\s+/).filter(Boolean) : []);
  }

  get innerHTML() {
    return this._innerHTML;
  }

  set innerHTML(val) {
    this._innerHTML = String(val);
    if (val === "") {
      this.children = [];
    }
  }

  getAttribute(name) { return this.attributes[name] || null; }
  setAttribute(name, val) { this.attributes[name] = String(val); }
  removeAttribute(name) { delete this.attributes[name]; }

  addEventListener(type, fn) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(fn);
  }

  dispatchEvent(event) {
    const handlers = this.listeners[event.type] || [];
    for (const handler of handlers) handler.call(this, event);
  }

  click() {
    this.dispatchEvent({ type: "click", preventDefault: () => {}, stopImmediatePropagation: () => {} });
  }

  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
    return child;
  }

  insertBefore(newNode, refNode) {
    const idx = this.children.indexOf(refNode);
    if (idx === -1) this.appendChild(newNode);
    else this.children.splice(idx, 0, newNode);
    newNode.parentNode = this;
    return newNode;
  }

  removeChild(child) {
    const idx = this.children.indexOf(child);
    if (idx !== -1) this.children.splice(idx, 1);
    return child;
  }

  replaceWith(newNode) {
    if (this.parentNode) {
      const idx = this.parentNode.children.indexOf(this);
      if (idx !== -1) this.parentNode.children[idx] = newNode;
    }
  }

  querySelector(selector) {
    return querySelectorImpl(this, selector);
  }

  querySelectorAll(selector) {
    return querySelectorAllImpl(this, selector);
  }

  closest(selector) {
    let cur = this;
    while (cur) {
      if (matchesSelector(cur, selector)) return cur;
      cur = cur.parentNode;
    }
    return null;
  }

  cloneNode(deep = true) {
    const clone = new ElementMock(this.tagName, this.id, this.className);
    clone.dataset = { ...this.dataset };
    clone.attributes = { ...this.attributes };
    clone.value = this.value;
    clone.textContent = this.textContent;
    clone.innerHTML = this.innerHTML;
    if (deep) {
      clone.children = this.children.map(c => {
        const childClone = c.cloneNode(true);
        childClone.parentNode = clone;
        return childClone;
      });
    }
    if (this.content) clone.content = this.content.cloneNode(true);
    return clone;
  }
}

function matchesSelector(el, selector) {
  if (!el || !selector) return false;
  if (selector.startsWith("#")) return el.id === selector.slice(1);
  if (selector.startsWith(".")) return el.classList.contains(selector.slice(1));
  if (selector.includes(".")) {
    const parts = selector.split(".");
    const tag = parts[0];
    const cls = parts[1];
    if (tag && el.tagName !== tag.toUpperCase()) return false;
    return el.classList.contains(cls);
  }
  return el.tagName === selector.toUpperCase();
}

function querySelectorAllImpl(root, selector) {
  const results = [];
  function walk(node) {
    for (const child of node.children || []) {
      if (matchesSelector(child, selector)) results.push(child);
      walk(child);
    }
  }
  walk(root);
  return results;
}

function querySelectorImpl(root, selector) {
  const all = querySelectorAllImpl(root, selector);
  return all.length ? all[0] : null;
}

function createDOMEnvironment() {
  const store = new Map();
  const localStorage = {
    getItem: key => store.get(key) || null,
    setItem: (key, val) => store.set(key, String(val)),
    removeItem: key => store.delete(key),
    clear: () => store.clear(),
  };

  const document = new ElementMock("document");
  const body = new ElementMock("body");
  document.body = body;
  document.appendChild(body);

  // Build UI skeleton matching index.html
  const statsSection = new ElementMock("section", "", "stats");
  const statMatches = new ElementMock("div", "", "stat");
  const shownCount = new ElementMock("span", "shownCount");
  const smallMatches = new ElementMock("small");
  smallMatches.textContent = "matches";
  statMatches.appendChild(shownCount);
  statMatches.appendChild(smallMatches);

  const statIndexed = new ElementMock("div", "", "stat");
  const totalCount = new ElementMock("span", "totalCount");
  const smallIndexed = new ElementMock("small");
  smallIndexed.textContent = "indexed";
  statIndexed.appendChild(totalCount);
  statIndexed.appendChild(smallIndexed);

  const statSaved = new ElementMock("div", "", "stat");
  const newCount = new ElementMock("span", "newCount");
  const smallSaved = new ElementMock("small");
  smallSaved.textContent = "saved";
  statSaved.appendChild(newCount);
  statSaved.appendChild(smallSaved);

  const statApplied = new ElementMock("div", "", "stat");
  const savedCount = new ElementMock("span", "savedCount");
  const smallApplied = new ElementMock("small");
  smallApplied.textContent = "applied";
  statApplied.appendChild(savedCount);
  statApplied.appendChild(smallApplied);

  statsSection.appendChild(statMatches);
  statsSection.appendChild(statIndexed);
  statsSection.appendChild(statSaved);
  statsSection.appendChild(statApplied);
  body.appendChild(statsSection);

  const controls = new ElementMock("section", "", "controls panel");
  const profileChips = new ElementMock("div", "profileChips", "chips");
  const filterGrid = new ElementMock("div", "", "filter-grid");
  const searchInput = new ElementMock("input", "searchInput");
  const locationInput = new ElementMock("input", "locationInput");
  const radiusInput = new ElementMock("input", "radiusInput");
  const freshnessSelect = new ElementMock("select", "freshnessSelect");
  const statusSelect = new ElementMock("select", "statusSelect");

  filterGrid.appendChild(searchInput);
  filterGrid.appendChild(locationInput);
  filterGrid.appendChild(radiusInput);
  filterGrid.appendChild(freshnessSelect);
  filterGrid.appendChild(statusSelect);
  controls.appendChild(profileChips);
  controls.appendChild(filterGrid);
  body.appendChild(controls);

  const resultsHeader = new ElementMock("section", "", "results-header");
  const titleDiv = new ElementMock("div");
  const resultsTitle = new ElementMock("h2", "resultsTitle");
  const resultsNote = new ElementMock("p", "resultsNote", "results-note");
  const feedMeta = new ElementMock("p", "feedMeta", "muted");
  titleDiv.appendChild(resultsTitle);
  titleDiv.appendChild(feedMeta);
  titleDiv.appendChild(resultsNote);
  resultsHeader.appendChild(titleDiv);

  const resultsTools = new ElementMock("div", "", "results-tools");
  const clearFiltersBtn = new ElementMock("button", "clearFiltersBtn", "text-btn");
  resultsTools.appendChild(clearFiltersBtn);
  resultsHeader.appendChild(resultsTools);
  body.appendChild(resultsHeader);

  const jobsContainer = new ElementMock("section", "jobs", "jobs");
  body.appendChild(jobsContainer);

  const loadMoreBtn = new ElementMock("button", "loadMoreBtn", "primary-btn hidden");
  body.appendChild(loadMoreBtn);

  const sourceHealth = new ElementMock("div", "sourceHealth");
  body.appendChild(sourceHealth);
  const errorBox = new ElementMock("section", "errorBox", "error-box hidden");
  body.appendChild(errorBox);

  const shareBtn = new ElementMock("button", "shareBtn", "ghost-btn");
  body.appendChild(shareBtn);

  // Template for job card
  const template = new ElementMock("template", "jobCardTemplate");
  const cardFragment = new ElementMock("article", "", "job-card");
  const company = new ElementMock("p", "", "company");
  const title = new ElementMock("h3", "", "title");
  const location = new ElementMock("p", "", "location");
  const age = new ElementMock("span", "", "age badge");
  const tags = new ElementMock("div", "", "tags");
  const sources = new ElementMock("div", "", "sources");
  const saveBtn = new ElementMock("button", "", "save-btn secondary-btn");
  const appliedBtn = new ElementMock("button", "", "applied-btn secondary-btn");
  const applyBtn = new ElementMock("a", "", "apply-btn primary-btn");
  const hideBtn = new ElementMock("button", "", "hide-btn icon-btn");

  cardFragment.appendChild(company);
  cardFragment.appendChild(title);
  cardFragment.appendChild(location);
  cardFragment.appendChild(age);
  cardFragment.appendChild(tags);
  cardFragment.appendChild(sources);
  cardFragment.appendChild(saveBtn);
  cardFragment.appendChild(appliedBtn);
  cardFragment.appendChild(applyBtn);
  cardFragment.appendChild(hideBtn);

  template.content = {
    firstElementChild: cardFragment,
  };
  body.appendChild(template);

  document.querySelector = selector => querySelectorImpl(body, selector);
  document.querySelectorAll = selector => querySelectorAllImpl(body, selector);
  document.createElement = tagName => new ElementMock(tagName);
  document.createDocumentFragment = () => new ElementMock("fragment");

  return { document, localStorage, body, store };
}

async function runTests() {
  // 1. Test Stat Navigation and State Syncing
  {
    const { document, localStorage } = createDOMEnvironment();
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
      setTimeout,
      clearTimeout,
      fetch: async () => ({
        ok: true,
        json: async () => ({
          jobs: [
            { id: "job-1", title: "Software Intern", company: "Company A", profiles: ["cs"], posted_at: "2026-09-01T00:00:00Z" },
            { id: "job-2", title: "Product Intern", company: "Company B", profiles: ["tech-business"], posted_at: "2026-09-02T00:00:00Z" },
          ],
          sources: {},
          generated_at: "2026-09-01T00:00:00Z",
        }),
      }),
    };
    context.globalThis = context;
    context.window = context;

    const appCode = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
    const uxCode = fs.readFileSync(path.join(__dirname, "..", "ux.js"), "utf8");

    vm.runInNewContext(appCode, context);
    vm.runInNewContext("globalThis.state = state; globalThis.applyFilters = applyFilters; globalThis.feed = feed;", context);
    vm.runInNewContext(uxCode, context);

    // Wait microtask tick for boot fetch
    await new Promise(r => setTimeout(r, 10));

    // Check stat navigation setup
    const savedTile = document.querySelector("#newCount").closest(".stat");
    const matchesTile = document.querySelector("#shownCount").closest(".stat");
    const appliedTile = document.querySelector("#savedCount").closest(".stat");

    assert.ok(savedTile, "Saved stat tile should be found");
    assert.equal(savedTile.getAttribute("role"), "button");
    assert.equal(savedTile.getAttribute("tabindex"), "0");
    assert.equal(savedTile.classList.contains("stat-nav"), true);

    // Click Saved tile to toggle state.status to "saved"
    savedTile.click();
    await new Promise(r => setTimeout(r, 10));

    assert.equal(context.state.status, "saved");
    assert.equal(document.querySelector("#statusSelect").value, "saved");
    assert.equal(savedTile.classList.contains("is-active"), true);
    assert.equal(savedTile.getAttribute("aria-pressed"), "true");

    // Clicking Saved tile again toggles back to "all"
    savedTile.click();
    await new Promise(r => setTimeout(r, 10));
    assert.equal(context.state.status, "all");
    assert.equal(document.querySelector("#statusSelect").value, "all");
    assert.equal(savedTile.classList.contains("is-active"), false);
    assert.equal(savedTile.getAttribute("aria-pressed"), "false");

    // Clicking Applied tile toggles state.status to "applied"
    appliedTile.click();
    await new Promise(r => setTimeout(r, 10));
    assert.equal(context.state.status, "applied");
    assert.equal(appliedTile.classList.contains("is-active"), true);

    // Clicking Matches tile resets state.status to "all"
    matchesTile.click();
    await new Promise(r => setTimeout(r, 10));
    assert.equal(context.state.status, "all");
    assert.equal(matchesTile.classList.contains("is-active"), true);
  }

  // 2. Test Empty State Messages for Saved Internships
  {
    const { document, localStorage } = createDOMEnvironment();
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
      setTimeout,
      clearTimeout,
      fetch: async () => ({
        ok: true,
        json: async () => ({
          jobs: [
            { id: "job-1", title: "Software Intern", company: "Company A", profiles: ["cs"], posted_at: "2026-09-01T00:00:00Z" },
          ],
          sources: {},
          generated_at: "2026-09-01T00:00:00Z",
        }),
      }),
    };
    context.globalThis = context;
    context.window = context;

    const appCode = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
    const uxCode = fs.readFileSync(path.join(__dirname, "..", "ux.js"), "utf8");

    vm.runInNewContext(appCode, context);
    vm.runInNewContext("globalThis.state = state; globalThis.applyFilters = applyFilters; globalThis.feed = feed;", context);
    vm.runInNewContext(uxCode, context);

    await new Promise(r => setTimeout(r, 10));

    const savedTile = document.querySelector("#newCount").closest(".stat");
    savedTile.click(); // Filter to saved internships with 0 saved items
    await new Promise(r => setTimeout(r, 10));

    const jobs = document.querySelector("#jobs");
    assert.ok(jobs.children.length > 0, "Empty state element should be rendered in jobs list");
    const emptyState = jobs.children[0];
    assert.equal(emptyState.className, "empty-state");
    assert.match(emptyState.innerHTML, /No saved internships yet/i);
    assert.match(emptyState.innerHTML, /Click the Save button/i);

    // Save job-1, but set search query to non-matching term "xyz"
    context.state.saved.add("job-1");
    context.state.search = "xyz";
    await context.applyFilters();

    const filteredEmptyState = jobs.children[0];
    assert.match(filteredEmptyState.innerHTML, /No saved internships match your current filters/i);
    const resetBtn = filteredEmptyState.querySelector(".empty-reset-btn");
    assert.ok(resetBtn, "Reset filters button should be present in filtered empty state");
  }

  // 3. Test HTML and script references contract
  {
    const indexHtml = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
    assert.ok(indexHtml.includes('src="app.js"'));
    assert.ok(indexHtml.includes('src="ux.js"'));
  }

  console.log("saved navigation regression tests passed");
}

runTests().catch(err => {
  console.error(err);
  process.exit(1);
});
