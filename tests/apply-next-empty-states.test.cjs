const assert = require("assert");
const fs = require("fs");
const path = require("path");

const uiSource = fs.readFileSync(path.join(__dirname, "..", "apply-next-ui.js"), "utf8");

(async () => {
  // Test states
  assert.match(uiSource, /Loading recommendations and validating current posting status\.\.\./, "Should support loading state");
  assert.match(uiSource, /Apply Next could not load the current feed/, "Should support error state");
  assert.match(uiSource, /You have saved, applied to, or hidden all eligible Apply Next candidates/, "Should support exhausted state");
  assert.match(uiSource, /No eligible Apply Next candidates are available yet/, "Should support no-recommendations state");
  assert.match(uiSource, /No strong matches were posted within the last/, "Should support fresh-empty state");

  assert.match(uiSource, /"apply-next-empty"/, "Should use apply-next-empty class for empty states");
  assert.match(uiSource, /"primary-btn apply-next-empty-action"/, "Should use apply-next-empty-action class for empty state buttons");

  assert.match(uiSource, /lastTotalEligibleCount\s*=\s*eligiblePoolCount/, "Should maintain a lastTotalEligibleCount separate from the current filtered pool");

  assert.match(uiSource, /catch\s*\(\s*error\s*\)/, "Should catch errors in renderQueue");
  assert.match(uiSource, /renderCurrentQueue\([^,]+,\s*[^,]+,\s*0,\s*"error"\)/, "Should pass error state to renderCurrentQueue");

  assert.match(uiSource, /lastTotalEligibleCount\s*>\s*0\s*&&\s*poolCount\s*===\s*0/, "Exhausted state should only be shown when total eligible is > 0 but pool is empty");

  console.log("apply-next empty states UI tests passed");
})().catch(error => {
  console.error(error);
  process.exit(1);
});
