const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Setup = require("../apply-next-profile-setup.js");

assert.ok(
  Setup.ROLE_FAMILIES.every(family => family.priority === 1),
  "all selected role families should have equal default priority"
);
assert.deepEqual(
  Setup.CAREER_AREAS.map(area => [area.id, area.label]),
  [["cs", "Computer Science"], ["engineering", "Engineering"], ["finance-econ", "Finance"]],
  "profile setup should expose Finance as a broad top-level career area"
);
assert.ok(
  Setup.defaultRoleFamilyIdsForAreas(["finance-econ"]).includes("finance-broad"),
  "Finance should have one broad default role family instead of premature sub-specialization"
);

const resume = `
University of Example
Bachelor of Science in Computer Science — Expected May 2028
Experience
Software Testing Intern — Linux, GitLab CI, Slurm, ReFrame, PMIx, PRRTE
Projects
Built Java and C software; used Git for version control.
Skills
Java, C, Git, Linux, Slurm
`;

const firstTimeIntern = Setup.extractResumeHints(`
University of Finance
Bachelor of Science in Finance — Expected May 2028
Relevant Coursework
Corporate Finance, Excel Modeling, Macroeconomics
Leadership
Treasurer for Student Finance Association
`);
assert.deepEqual(firstTimeIntern.courseworkEvidence, ["Corporate Finance, Excel Modeling, Macroeconomics"]);
assert.deepEqual(firstTimeIntern.leadershipEvidence, ["Treasurer for Student Finance Association"]);
assert.deepEqual(firstTimeIntern.workExperienceEvidence, []);

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
assert.deepEqual(hints.workExperienceEvidence, ["Software Testing Intern — Linux, GitLab CI, Slurm, ReFrame, PMIx, PRRTE"]);
assert.deepEqual(hints.projectEvidence, ["Built Java and C software; used Git for version control."]);
assert.deepEqual(hints.skillsEvidence, ["Java, C, Git, Linux, Slurm"]);
assert.ok(!hints.workExperienceEvidence.some(line => /Built Java and C software/i.test(line)), "project evidence must not be promoted to work experience");
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
  studentStage: "Sophomore",
  degree: hints.degree,
  major: hints.major,
  citizenship: "Unknown / not provided",
  workAuthorization: "Unknown / not provided",
  securityClearance: "Unknown / not provided",
  supportedSkills: hints.supportedSkills,
  cautiousSkills: "Python, Bash",
  experienceEvidence: (hints.workExperienceEvidence || []).join("\n"),
  workExperienceEvidence: (hints.workExperienceEvidence || []).join("\n"),
  careerAreaIds: ["cs"],
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
assert.equal(profile.facts.studentStage, "Sophomore");
assert.equal(profile.facts.degree, "Bachelor of Science");
assert.equal(profile.facts.citizenship, "Unknown / not provided");
assert.equal(profile.facts.workAuthorization, "Unknown / not provided");
assert.deepEqual(profile.baseZips, ["20740", "06897"]);
assert.ok(profile.supportedKeywords.includes("software engineer"));
assert.ok(profile.supportedKeywords.includes("Linux"));
assert.deepEqual(profile.facts.cautiousSkills, ["Python", "Bash"]);
assert.deepEqual(profile.facts.experienceEvidence, ["Software Testing Intern — Linux, GitLab CI, Slurm, ReFrame, PMIx, PRRTE"]);
assert.deepEqual(profile.facts.workExperienceEvidence, ["Software Testing Intern — Linux, GitLab CI, Slurm, ReFrame, PMIx, PRRTE"]);
assert.equal(profile.remoteRelevant, true);
assert.equal(profile.relocationAllowed, true);

const citizenProfile = Setup.buildProfile({
  targetTerm: "Summer 2027",
  citizenship: "U.S. citizen",
  workAuthorization: "Unknown / not provided",
  securityClearance: "Unknown / not provided",
  careerAreaIds: ["cs"],
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
assert.deepEqual(defaultRoleProfile.careerAreas, ["cs"], "new profiles should remain CS-first by default");
assert.deepEqual(
  defaultRoleProfile.roleFamilies.map(family => family.id),
  Setup.defaultRoleFamilyIdsForAreas(["cs"]),
  "new profiles should default only to role families compatible with the CS-first career area"
);

const engineeringHints = Setup.extractResumeHints(`
Bachelor of Science in Mechanical Engineering — Expected May 2028
Skills: SolidWorks, MATLAB, Simulink, CAD, ANSYS, finite element analysis, computational fluid dynamics,
geometric dimensioning and tolerancing, Siemens NX, Abaqus, DFMA, FMEA, CNC, composite materials
`);
assert.equal(engineeringHints.major, "Mechanical Engineering");
for (const skill of [
  "SolidWorks", "MATLAB", "Simulink", "CAD", "ANSYS", "FEA", "CFD", "GD&T", "Siemens NX",
  "Abaqus", "DFMA", "FMEA", "CNC", "Composites",
]) {
  assert.ok(engineeringHints.supportedSkills.includes(skill), `mechanical resume parser should recognize ${skill}`);
}

const aeroHints = Setup.extractResumeHints(`
Bachelor of Science in Astronautical Engineering — Expected May 2028
Coursework and projects: aerodynamics, propulsion, astrodynamics, flight dynamics,
guidance navigation and control, avionics, flight testing, wind tunnel testing,
computational fluid dynamics, Kalman filtering, sensor fusion, MATLAB
`);
assert.equal(aeroHints.major, "Astronautical Engineering");
for (const skill of [
  "Aerodynamics", "Propulsion", "Orbital mechanics", "Flight dynamics", "GNC", "Avionics",
  "Flight test", "Wind tunnel testing", "CFD", "Kalman filter", "Sensor fusion", "MATLAB",
]) {
  assert.ok(aeroHints.supportedSkills.includes(skill), `aero/astro resume parser should recognize ${skill}`);
}
assert.ok(
  Setup.ENGINEERING_SKILLS.some(skill => skill.disciplines.includes("mechanical"))
    && Setup.ENGINEERING_SKILLS.some(skill => skill.disciplines.includes("aero")),
  "engineering taxonomy should explicitly cover mechanical and aero disciplines"
);

const engineeringProfile = Setup.buildProfile({
  targetTerm: "Summer 2027",
  graduation: "May 2028",
  degree: "Bachelor of Science",
  major: "Mechanical Engineering",
  citizenship: "Unknown / not provided",
  workAuthorization: "Unknown / not provided",
  securityClearance: "Unknown / not provided",
  supportedSkills: engineeringHints.supportedSkills,
  cautiousSkills: "",
  careerAreaIds: ["engineering"],
  roleFamilyIds: ["mechanical-manufacturing", "robotics-controls"],
  opportunityTypes: ["internship", "co-op"],
  baseZips: "20740",
  nearbyMiles: 50,
  remoteRelevant: true,
  relocationAllowed: true,
}, {});
assert.deepEqual(engineeringProfile.careerAreas, ["engineering"]);
assert.ok(engineeringProfile.preferredProfiles.includes("engineering"));
assert.ok(!engineeringProfile.preferredProfiles.includes("cs"));
assert.deepEqual(engineeringProfile.roleFamilies.map(family => family.id), ["mechanical-manufacturing", "robotics-controls"]);
assert.ok(engineeringProfile.supportedKeywords.includes("mechanical engineer"));
assert.ok(engineeringProfile.supportedKeywords.includes("SolidWorks"));

const financeProfile = Setup.buildProfile({
  targetTerm: "Summer 2027",
  citizenship: "Unknown / not provided",
  workAuthorization: "Unknown / not provided",
  securityClearance: "Unknown / not provided",
  careerAreaIds: ["finance-econ"],
  opportunityTypes: ["internship"],
}, {});
assert.deepEqual(financeProfile.careerAreas, ["finance-econ"]);
assert.deepEqual(financeProfile.preferredProfiles, ["finance-econ", "tech-business"]);
assert.deepEqual(
  financeProfile.roleFamilies.map(family => family.id),
  ["analytics", "business-operations", "technology-business", "finance-broad"]
);
assert.ok(financeProfile.supportedKeywords.includes("finance"));
assert.ok(financeProfile.supportedKeywords.includes("banking"));
assert.ok(financeProfile.supportedKeywords.includes("economics"));
assert.ok(financeProfile.supportedKeywords.includes("business analyst"));
assert.ok(financeProfile.supportedKeywords.includes("operations analyst"));
assert.ok(financeProfile.supportedKeywords.includes("IT analyst"));
assert.ok(financeProfile.supportedKeywords.includes("FP&A"));

const businessDataProfile = Setup.buildProfile({
  targetTerm: "Summer 2027",
  major: "Computer Science",
  citizenship: "U.S. citizen",
  workAuthorization: "Authorized to work in the U.S. without sponsorship",
  supportedSkills: "Java, C, Python, Linux, Git, GitLab CI, Excel",
  cautiousSkills: "Python",
  careerAreaIds: ["cs"],
  roleFamilyIds: ["analytics", "business-operations", "technology-business"],
  opportunityTypes: ["internship"],
  preferredStates: "CT, NY",
  remoteRelevant: true,
}, {});
assert.deepEqual(businessDataProfile.careerAreas, ["cs"]);
assert.ok(businessDataProfile.preferredProfiles.includes("tech-business"));
assert.ok(businessDataProfile.supportedKeywords.includes("decision science"));
assert.ok(businessDataProfile.supportedKeywords.includes("strategy & operations"));
assert.ok(businessDataProfile.supportedKeywords.includes("digital business analyst"));

const combinedProfile = Setup.buildProfile({
  targetTerm: "Summer 2027",
  citizenship: "Unknown / not provided",
  workAuthorization: "Unknown / not provided",
  securityClearance: "Unknown / not provided",
  careerAreaIds: ["cs", "engineering"],
  roleFamilyIds: ["software", "electrical-hardware", "hpc"],
  opportunityTypes: ["internship"],
}, {});
assert.deepEqual(combinedProfile.careerAreas, ["cs", "engineering"]);
assert.ok(combinedProfile.preferredProfiles.includes("cs"));
assert.ok(combinedProfile.preferredProfiles.includes("engineering"));

{
  let clicks = 0;
  const attrs = {};
  const panel = {
    dataset: { view: "apply-next" },
    classList: {
      hidden: false,
      contains(name) { return name === "hidden" ? this.hidden : false; },
      add(name) { if (name === "hidden") this.hidden = true; },
    },
  };
  const button = {
    click() { clicks += 1; },
    setAttribute(name, value) { attrs[name] = value; },
  };
  const fakeDocument = {
    querySelector(selector) {
      if (selector === "#applyNextBtn") return button;
      if (selector === "#applyNextPanel") return panel;
      return null;
    },
  };

  Setup.refreshApplyNextPanel(fakeDocument);

  assert.equal(panel.classList.hidden, true, "save refresh should reset the open panel before reopening");
  assert.equal(panel.dataset.view, "", "save refresh should clear the stale open-view guard");
  assert.equal(attrs["aria-expanded"], "false");
  assert.equal(clicks, 1, "save refresh should perform exactly one reopen click");
}

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
  assert.match(source, /Choose Computer Science, Engineering, Finance, or any combination/);
  assert.match(source, /careerArea/);
  assert.match(source, /Mechanical \/ manufacturing/);
  assert.match(source, /Electrical \/ electronics \/ hardware/);
  assert.match(source, /Robotics \/ controls \/ automation/);
  assert.match(source, /Broad finance \/ economics/);
  assert.match(source, /When are you graduating \(month year\)/);
  assert.match(source, /input\("targetTerm", "Summer 2027", "radio"\)/);
  assert.match(source, /profile \? "Save profile" : "Create profile"/, "New users should see a clear Create profile action");
  assert.match(source, /"← Back to Yartchives"/, "Profile setup should expose a clear route back to the landing choices");
  assert.match(source, /ui\.returnToEntryChoice\(\)/, "Back navigation should return through the shared Apply Next landing helper");
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
  const qualityRunner = fs.readFileSync(path.join(__dirname, "..", "scripts", "run_quality_checks.sh"), "utf8");
  assert.match(quality, /bash scripts\/run_quality_checks\.sh frontend/);
  assert.match(qualityRunner, /node --check apply-next-profile-setup\.js/);
  assert.match(qualityRunner, /node tests\/apply-next-profile-setup\.test\.cjs/);

  console.log("apply-next resume profile setup tests passed");
})().catch(error => {
  console.error(error);
  process.exit(1);
});
