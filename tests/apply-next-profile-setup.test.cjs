const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Setup = require("../apply-next-profile-setup.js");

const resume = `
University of Example
Bachelor of Science in Computer Science — Expected May 2028
Experience
Software Testing Intern — Linux, GitLab CI, Slurm, ReFrame, PMIx, PRRTE
Projects
Built Java and C software; used Git for version control.
Skills: Java, C, Git, Linux, Slurm
`;

const hints = Setup.extractResumeHints(resume);
assert.equal(hints.graduation, "May 2028");
assert.equal(hints.degree, "Bachelor of Science");
assert.equal(hints.major, "Computer Science");
assert.ok(hints.supportedSkills.includes("Java"));
assert.ok(hints.supportedSkills.includes("C"));
assert.ok(hints.supportedSkills.includes("Git"));
assert.ok(hints.supportedSkills.includes("Linux"));
assert.ok(hints.supportedSkills.includes("Slurm"));
assert.ok(hints.supportedSkills.includes("ReFrame"));
assert.ok(!hints.supportedSkills.includes("C++"), "C must not be promoted to C++");
assert.equal(hints.citizenship, "Unknown / not provided", "resume omission must remain unknown");
assert.equal(hints.workAuthorization, "Unknown / not provided", "resume omission must remain unknown");
assert.equal(hints.securityClearance, "Unknown / not provided", "resume omission must remain unknown");

const explicit = Setup.extractResumeHints(`U.S. Citizen\nActive Secret clearance\nExpected December 2027\nPython, C++`);
assert.equal(explicit.citizenship, "U.S. citizen");
assert.equal(explicit.workAuthorization, "Authorized to work in the U.S. without sponsorship");
assert.equal(explicit.securityClearance, "Active Secret clearance");
assert.ok(explicit.supportedSkills.includes("C++"));
assert.ok(!explicit.supportedSkills.includes("C"), "C++ must not be treated as C");

const highSchoolFirst = Setup.extractResumeHints(`
Education
Wilton High School
High School Diploma — Graduated May 2025
University of Maryland
Bachelor of Science in Computer Science — Expected May 2029
`);
assert.equal(highSchoolFirst.graduation, "May 2029", "college graduation must outrank an earlier high-school graduation date");

const highSchoolOnly = Setup.extractResumeHints(`
Education
Example High School
High School Diploma — Graduated May 2025
`);
assert.equal(highSchoolOnly.graduation, "", "high-school graduation must not be used as the college graduation date");

const collegeWithoutExpected = Setup.extractResumeHints(`
University of Example
B.S. Computer Science — May 2028
`);
assert.equal(collegeWithoutExpected.graduation, "May 2028", "higher-education context should support a graduation date even without the word expected");

const profile = Setup.buildProfile({
  targetTerm: "Summer 2027",
  graduation: hints.graduation,
  degree: hints.degree,
  major: hints.major,
  citizenship: "Unknown / not provided",
  workAuthorization: "Unknown / not provided",
  securityClearance: "Unknown / not provided",
  supportedSkills: hints.supportedSkills,
  cautiousSkills: "Python, Bash",
  roleFamilyIds: ["software", "testing-systems"],
  opportunityTypes: ["internship", "co-op"],
  baseZips: "20740, 06897",
  preferredStates: "MD, DC, VA, CT, NY, NJ",
  nearbyMiles: 50,
  remoteRelevant: true,
  relocationAllowed: true,
  excludeGraduateOnly: true,
}, {});

assert.equal(profile.facts.graduation, "May 2028");
assert.equal(profile.facts.degree, "Bachelor of Science");
assert.equal(profile.facts.citizenship, "Unknown / not provided");
assert.equal(profile.facts.workAuthorization, "Unknown / not provided");
assert.deepEqual(profile.baseZips, ["20740", "06897"]);
assert.ok(profile.supportedKeywords.includes("software engineer"));
assert.ok(profile.supportedKeywords.includes("Linux"));
assert.deepEqual(profile.facts.cautiousSkills, ["Python", "Bash"]);
assert.equal(profile.remoteRelevant, true);
assert.equal(profile.relocationAllowed, true);

const citizenProfile = Setup.buildProfile({
  targetTerm: "Summer 2027",
  citizenship: "U.S. citizen",
  workAuthorization: "Unknown / not provided",
  securityClearance: "Unknown / not provided",
  roleFamilyIds: ["software"],
  opportunityTypes: ["internship"],
}, {});
assert.equal(citizenProfile.facts.workAuthorization, "Authorized to work in the U.S. without sponsorship");

const defaultRoleProfile = Setup.buildProfile({
  targetTerm: "Summer 2027",
  citizenship: "Unknown / not provided",
  workAuthorization: "Unknown / not provided",
  securityClearance: "Unknown / not provided",
  opportunityTypes: ["internship"],
}, {});
assert.deepEqual(
  defaultRoleProfile.roleFamilies.map(family => family.id),
  Setup.ROLE_FAMILIES.map(family => family.id),
  "new profiles should default to all role families"
);

(async () => {
  const textFile = {
    name: "resume.txt",
    type: "text/plain",
    text: async () => "Expected May 2028 — Java",
  };
  assert.equal(await Setup.readResumeFile(textFile), "Expected May 2028 — Java");

  let importedUrl = null;
  const fakePdfFile = {
    name: "resume.pdf",
    type: "application/pdf",
    arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
  };
  const fakePdfJs = {
    GlobalWorkerOptions: {},
    getDocument() {
      return {
        promise: Promise.resolve({
          numPages: 2,
          async getPage(page) {
            return { getTextContent: async () => ({ items: [{ str: page === 1 ? "Computer Science" : "May 2028" }] }) };
          },
        }),
      };
    },
  };
  const pdfText = await Setup.readResumeFile(fakePdfFile, async url => {
    importedUrl = url;
    return fakePdfJs;
  });
  assert.equal(importedUrl, Setup.PDFJS_URL);
  assert.equal(fakePdfJs.GlobalWorkerOptions.workerSrc, Setup.PDFJS_WORKER_URL);
  assert.match(pdfText, /Computer Science/);
  assert.match(pdfText, /May 2028/);

  const index = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  assert.ok(index.includes('href="apply-next-profile-setup.css"'));
  assert.ok(index.includes('src="apply-next-profile-setup.js"'));
  assert.ok(index.indexOf('src="apply-next-ui.js"') < index.indexOf('src="apply-next-profile-setup.js"'), "profile setup should enhance the initialized Apply Next UI");
  assert.match(index, /cdnjs\.cloudflare\.com/);
  assert.match(index, /worker-src/);

  const source = fs.readFileSync(path.join(__dirname, "..", "apply-next-profile-setup.js"), "utf8");
  assert.match(source, /raw resume is never saved or uploaded/i);
  assert.match(source, /When are you looking\?/);
  assert.match(source, /When are you graduating \(month year\)/);
  assert.match(source, /input\("targetTerm", "Summer 2027", "radio"\)/);
  assert.match(source, /profile \? "Save profile" : "Create profile"/, "New users should see a clear Create profile action");
  assert.match(
    source,
    /panel\.classList\.add\("hidden"\);[\s\S]*panel\.dataset\.view = "";[\s\S]*button\.click\(\);/,
    "Saving an edited profile should force one clean Apply Next rerender instead of re-clicking an already-open panel"
  );
  assert.doesNotMatch(
    source,
    /button\.click\(\);\s*setTimeout\(\(\) => button\.click\(\), 0\);/,
    "Profile save refresh must not depend on the old toggle-button behavior"
  );
  assert.doesNotMatch(source, /field\("Degree"/);
  assert.doesNotMatch(source, /Kaamil|Badami|kaamil\.badami/i);

  const setupCss = fs.readFileSync(path.join(__dirname, "..", "apply-next-profile-setup.css"), "utf8");
  assert.match(setupCss, /main\.apply-next-profile-mode > :not\(#applyNextPanel\)/, "Focused profile mode should hide the ordinary feed");
  assert.match(setupCss, /display: none !important;/);

  const quality = fs.readFileSync(path.join(__dirname, "..", ".github", "workflows", "quality.yml"), "utf8");
  assert.match(quality, /node --check apply-next-profile-setup\.js/);
  assert.match(quality, /node tests\/apply-next-profile-setup\.test\.cjs/);

  console.log("apply-next resume profile setup tests passed");
})().catch(error => {
  console.error(error);
  process.exit(1);
});
