const assert = require("node:assert/strict");
const D = require("../apply-next-dimensions.js");
const R = require("../apply-next-readiness.js");

const now = new Date("2026-09-17T12:00:00Z");

function job(overrides = {}) {
  return {
    id: "job-" + Math.random().toString(36).slice(2, 9),
    company: "ExampleCo",
    title: "Software Engineer Intern",
    profiles: ["cs"],
    states: ["MD"],
    location: "Maryland",
    term: "Summer 2027",
    opportunity_type: "internship",
    posted_at: "2026-09-16T12:00:00Z",
    link_kind: "direct",
    url: "https://example.com/job",
    _inspection: {
      status: "inspected",
      posting: { application_status: "available" },
      requirements: {
        skills: {
          required: [], preferred: [], unspecified: [], not_required: []
        },
        education: {
          required: [], preferred: [], unspecified: [], not_required: []
        },
        graduation: {
          required: [], preferred: [], unspecified: [], not_required: []
        },
        major_fields: {
          required: [], preferred: [], unspecified: [], not_required: []
        }
      }
    },
    ...overrides,
  };
}

function inspection(required = [], preferred = [], graduation = [], education = [], unspecified = []) {
  return {
    status: "inspected",
    posting: { application_status: "available" },
    requirements: {
      skills: {
        required: required.map(([statement, technologies]) => ({ statement, technologies: technologies || [] })),
        preferred: preferred.map(([statement, technologies]) => ({ statement, technologies: technologies || [] })),
        unspecified: unspecified.map(([statement, technologies]) => ({ statement, technologies: technologies || [] })),
        not_required: [],
      },
      education: {
        required: education.map(e => ({ statement: e })), preferred: [], unspecified: [], not_required: [],
      },
      graduation: {
        required: graduation.map(g => ({ statement: g })), preferred: [], unspecified: [], not_required: [],
      },
      major_fields: {
        required: [], preferred: [], unspecified: [], not_required: [],
      },
    },
  };
}

// 1. KB Persona (CS/ORNL testing evidence with data science preference)
const kbProfile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship"],
  preferredProfiles: ["cs"],
  supportedKeywords: ["testing", "java", "c", "hpc", "ci/cd", "regression testing", "machine learning"],
  cautiousKeywords: ["python", "data science"],
  facts: {
    degree: "Bachelor of Science",
    major: "Computer Science",
    supportedSkills: ["Java", "C", "Testing", "HPC", "CI/CD", "Machine Learning"],
    cautiousSkills: ["Python"],
    workExperienceEvidence: ["prior technical internship", "HPC/software testing", "CI/regression testing"],
    graduation: "May 2029",
  },
  roleFamilies: [
    { id: "data", label: "Data Science", priority: 1, keywords: ["data science", "data analytics"] },
    { id: "systems", label: "Systems", priority: 2, keywords: ["testing", "systems"] }
  ],
  preferredStates: ["MD"],
};

const kbDataScienceJob = job({
  id: "job-ds",
  title: "Data Science Intern",
  profiles: ["data-science", "cs"],
  url: "https://example.com/job-ds",
  _inspection: inspection(
    [["Required Python, Pandas, and ML experience", ["Python", "Pandas", "Machine Learning"]]],
    []
  )
});

const kbTestingJob = job({
  id: "job-test",
  title: "Software Test Engineering Intern",
  profiles: ["cs"],
  url: "https://example.com/job-test",
  _inspection: inspection(
    [["Required Java, CI/CD, and regression testing experience", ["Java", "CI/CD", "Testing"]]],
    []
  )
});

const kbRanked = D.rankJobs([kbDataScienceJob, kbTestingJob], kbProfile, now);
assert.equal(kbRanked[0].job.title, "Software Test Engineering Intern", "KB should rank the Testing job higher due to exact qualification evidence, despite a higher priority role family for Data Science");
assert.ok(kbRanked[1].components.fit.score < kbRanked[0].components.fit.score, "Data Science job should have lower fit score due to missing/cautious required skills");

// 2. FR Persona (Freshman, May 2030)
const frProfile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship"],
  preferredProfiles: ["cs"],
  supportedKeywords: ["python"],
  cautiousKeywords: [],
  facts: {
    studentStage: "Freshman",
    graduation: "May 2030",
    supportedSkills: ["Python"],
    cautiousSkills: [],
    workExperienceEvidence: ["no prior technical internship"],
  },
  roleFamilies: [{ id: "software", label: "Software Engineering", priority: 1, keywords: ["software"] }],
};

const juniorJob = job({
  title: "SWE Intern",
  url: "https://example.com/junior",
  _inspection: inspection([], [], ["Graduating between Dec 2027 and June 2028."]) // Junior
});

const freshmanJob = job({
  title: "Early Career SWE Intern",
  url: "https://example.com/freshman",
  _inspection: inspection([], [], ["Graduating between Dec 2029 and June 2031."]) // Freshman/Sophomore
});

const frRanked = D.rankJobs([juniorJob, freshmanJob], frProfile, now);
assert.equal(frRanked.length, 1, "FR should only be eligible for the freshman-friendly job");
assert.equal(frRanked[0].job.title, "Early Career SWE Intern", "FR should be eligible for the May 2030 job");


// 3. AM Persona (Finance sophomore, limited experience)
const amProfile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship"],
  preferredProfiles: ["finance-econ"],
  supportedKeywords: ["excel", "business"],
  cautiousKeywords: [],
  facts: {
    major: "Economics",
    graduation: "May 2029",
    studentStage: "Sophomore",
    supportedSkills: ["Excel"],
    cautiousSkills: [],
    workExperienceEvidence: ["Excel Skills for Business certification", "no prior finance internship", "customer-facing retail work"],
  },
  roleFamilies: [{ id: "finance", label: "Finance", priority: 1, keywords: ["finance", "economics"] }],
};

const financeExpRequired = job({
  title: "Corporate Finance Intern",
  profiles: ["finance-econ"],
  url: "https://example.com/finance-exp",
  _inspection: inspection(
    [["1 prior finance internship required", ["Finance Internship"]]]
  )
});

const financeNoExpRequired = job({
  title: "Financial Analyst Intern",
  profiles: ["finance-econ"],
  url: "https://example.com/finance-no-exp",
  _inspection: inspection(
    [["No prior experience required. Excel proficiency required.", ["Excel"]]]
  )
});

const amRanked = D.rankJobs([financeExpRequired, financeNoExpRequired], amProfile, now);
if (amRanked.length === 2) {
  assert.equal(amRanked[0].job.title, "Financial Analyst Intern", "AM should rank the job requiring no experience higher");
} else {
  assert.equal(amRanked.length, 1);
  assert.equal(amRanked[0].job.title, "Financial Analyst Intern");
}

// 4. DD Persona (SWE-oriented student with quant/finance exposure)
const ddProfile = {
  targetTerm: "Summer 2027",
  opportunityTypes: ["internship"],
  preferredProfiles: ["cs"],
  supportedKeywords: ["c++", "python", "quantitative", "finance", "ml", "data"],
  cautiousKeywords: [],
  facts: {
    major: "Computer Science",
    graduation: "May 2028",
    supportedSkills: ["C++", "Python", "Quantitative", "Finance", "ML", "Data"],
    cautiousSkills: [],
    workExperienceEvidence: ["prior software internship", "quantitative/finance exposure"],
  },
  roleFamilies: [
    { id: "software", label: "Software Engineering", priority: 1, keywords: ["software engineer", "quant dev"] }
  ],
};

const quantDevJob = job({
  title: "Quantitative Developer Intern",
  profiles: ["cs", "finance-econ"],
  url: "https://example.com/quant-dev",
  _inspection: inspection(
    [["C++ and Python experience required. Quantitative finance exposure preferred.", ["C++", "Python", "Quantitative", "Finance"]]]
  )
});

const ddRanked = D.rankJobs([quantDevJob], ddProfile, now);
assert.equal(ddRanked.length, 1);
assert.ok(ddRanked[0].components.fit.score > 25, "DD should have a very strong fit for Quant Dev due to prior quant/finance and SWE exposure");

// Required vs preferred vs unknown qualifications mock
const unknownQualificationsJob = job({
  title: "Unknown Skills Job Intern",
  opportunity_type: "internship",
  url: "https://example.com/unknown",
  _inspection: inspection(
    [], [], [], [], [["Some unspecified skill", ["Unspecified"]]]
  )
});

const ddRankedUnknown = D.rankJobs([unknownQualificationsJob], ddProfile, now);
assert.equal(ddRankedUnknown.length, 1);
assert.ok(ddRankedUnknown[0].components.fit.score < ddRanked[0].components.fit.score, "Known exact fit should outrank unspecified qualifications");

console.log("apply-next career validation regression tests passed");
