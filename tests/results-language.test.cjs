const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const script = fs.readFileSync(require.resolve("../share.js"), "utf8");
const education = { value: "undergrad-friendly" };
const opportunityType = { value: "internships" };
const shareButton = { addEventListener() {}, textContent: "Share view" };
const hiddenToggle = { classList: { contains: () => false } };
let activeAreas = [];

const document = {
  querySelector(selector) {
    if (selector === "#educationSelect") return education;
    if (selector === "#opportunityTypeSelect") return opportunityType;
    if (selector === "#shareBtn") return shareButton;
    if (selector === "#hiddenToggleBtn") return hiddenToggle;
    if (selector === "#sortSelect") return { value: "newest" };
    return null;
  },
  querySelectorAll(selector) {
    if (selector === "#profileChips button.active") {
      return activeAreas.map(label => ({ textContent: label }));
    }
    if (selector === "#profileChips button") return [];
    return [];
  },
};

const state = {
  search: "",
  location: "",
  radius: "50",
  freshness: "7",
  status: "all",
};
const els = {
  resultsTitle: { textContent: "All opportunities" },
  resultsNote: { textContent: "" },
};
const context = {
  document,
  state,
  els,
  location: { search: "", href: "https://example.test/yartchives/" },
  URLSearchParams,
  localStorage: { getItem: () => "{}" },
  currentZip: () => null,
  updateResultsNote: () => {},
  renderJobs: () => {},
};
vm.createContext(context);
vm.runInContext(script, context);

assert.equal(
  els.resultsTitle.textContent,
  "Undergrad-friendly internships + co-ops · Past 7 days"
);
activeAreas = ["Computer Science"];
education.value = "all";
opportunityType.value = "all";
state.freshness = "30";
state.location = "CT";
state.search = "software";
state.status = "saved";
hiddenToggle.classList.contains = () => true;
context.renderJobs();
assert.equal(
  els.resultsTitle.textContent,
  "Computer Science · All opportunities · Past 30 days · CT · Search: “software” · Saved · Hidden"
);

console.log("results-language tests passed");
