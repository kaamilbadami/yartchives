const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM } = require('jsdom');

const dom = new JSDOM(`<!DOCTYPE html>
<html>
<body>
  <div id="applyNextPanel"></div>
  <template id="applyNextJobTemplate">
    <div class="apply-next-job">
      <button class="save-btn"></button>
      <button class="applied-btn"></button>
      <button class="hide-btn"></button>
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
    setItem(key, val) { this.data[key] = String(val); },
    removeItem(key) { delete this.data[key]; }
  },
  location: window.location,
  URLSearchParams: window.URLSearchParams,
  Set, Map, Array, Object, Number, Date, JSON, String,
  setTimeout: window.setTimeout,
  clearTimeout: window.clearTimeout,
  Math,
  fetch: async () => ({
    ok: true,
    json: async () => ({ jobs: [] })
  })
};

context.globalThis = context;
context.window = context;

const uxCode = fs.readFileSync(path.join(__dirname, "ux.js"), "utf8");
const applyNextUiCode = fs.readFileSync(path.join(__dirname, "apply-next-ui.js"), "utf8");
const applyNextCode = fs.readFileSync(path.join(__dirname, "apply-next.js"), "utf8");
const appCode = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");

vm.runInNewContext(appCode, context);
vm.runInNewContext("globalThis.state = state; globalThis.applyFilters = applyFilters;", context);
vm.runInNewContext(applyNextCode, context);
vm.runInNewContext(uxCode, context);
vm.runInNewContext(applyNextUiCode, context);
