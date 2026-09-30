(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.YartchivesApplyNextProfileSetup = api;
    if (typeof document !== "undefined") api.init();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const PDFJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs";
  const PDFJS_WORKER_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";

  const CAREER_AREAS = [
    { id: "cs", label: "Computer Science" },
    { id: "engineering", label: "Engineering" },
    { id: "finance-econ", label: "Finance" },
  ];

  const ROLE_FAMILIES = [
    { id: "software", label: "Software engineering", careerAreas: ["cs"], priority: 1, keywords: ["software engineer", "software developer"] },
    { id: "testing-systems", label: "Software testing / systems", careerAreas: ["cs"], priority: 1, keywords: ["software test", "quality assurance", "qa", "systems software"] },
    { id: "analytics", label: "Data / analytics", careerAreas: ["cs"], priority: 1, keywords: ["data analyst", "data engineer", "analytics"] },
    { id: "infrastructure", label: "Infrastructure / technical ops", careerAreas: ["cs"], priority: 1, keywords: ["infrastructure", "technical ops", "IT", "cloud engineer", "devops"] },
    { id: "ai-ml", label: "AI / machine learning", careerAreas: ["cs"], priority: 1, keywords: ["machine learning", "artificial intelligence", "AI/ML", "AI engineer"] },
    { id: "cybersecurity", label: "Cybersecurity", careerAreas: ["cs"], priority: 1, keywords: ["cybersecurity", "information security", "security engineer"] },
    { id: "hpc", label: "HPC / scientific computing", careerAreas: ["cs", "engineering"], priority: 1, keywords: ["HPC", "scientific computing"] },
    { id: "mechanical-manufacturing", label: "Mechanical / manufacturing", careerAreas: ["engineering"], priority: 1, keywords: ["mechanical engineer", "manufacturing engineer", "mechanical design", "industrial engineer", "materials engineer", "thermal engineer", "product design", "mechanical systems", "stress analysis"] },
    { id: "electrical-hardware", label: "Electrical / electronics / hardware", careerAreas: ["engineering"], priority: 1, keywords: ["electrical engineer", "electronics engineer", "hardware engineer", "computer engineer", "embedded systems", "firmware", "FPGA", "RF engineer"] },
    { id: "aerospace", label: "Aerospace / astronautical / flight / space systems", careerAreas: ["engineering"], priority: 1, keywords: ["aerospace", "aeronautical", "astronautical", "propulsion", "aerodynamics", "flight dynamics", "flight test", "space systems", "spacecraft", "satellite", "orbital mechanics", "astrodynamics", "GNC", "avionics"] },
    { id: "engineering-systems", label: "Systems / integration / validation", careerAreas: ["engineering"], priority: 1, keywords: ["systems engineer", "systems integration", "validation engineer", "verification engineer", "reliability engineer"] },
    { id: "robotics-controls", label: "Robotics / controls / automation", careerAreas: ["engineering"], priority: 1, keywords: ["robotics", "controls engineer", "automation engineer", "mechatronics", "autonomy"] },
    { id: "civil-structural", label: "Civil / structural / transportation", careerAreas: ["engineering"], priority: 1, keywords: ["civil engineer", "structural engineer", "transportation engineer", "roadway", "construction engineer"] },
    { id: "product-design-test", label: "Product / design / test engineering", careerAreas: ["engineering"], priority: 1, keywords: ["product engineer", "design engineer", "test engineer", "quality engineer", "process engineer", "development engineer"] },
    { id: "finance-broad", label: "Broad finance / economics", careerAreas: ["finance-econ"], priority: 1, keywords: ["finance", "financial analyst", "accounting", "audit", "tax", "actuarial", "banking", "investment", "capital markets", "asset management", "wealth management", "risk", "underwriting", "economics", "economist", "treasury", "credit"] },
  ];

  const BASE_SKILLS = [
    "Java", "C++", "C", "C#", "Python", "Bash", "JavaScript", "TypeScript", "React", "Node.js",
    "Git", "GitHub", "GitLab CI", "Linux", "Unix", "Slurm", "SQL", "PostgreSQL", "MySQL", "Docker",
    "Kubernetes", "AWS", "Azure", "GCP", "CMake", "gdb", "GoogleTest", "Jenkins", "Jira", "MATLAB", "Simulink",
    "LabVIEW", "Verilog", "VHDL", "FPGA", "PCB", "Altium", "PLC", "ROS", "R", "Excel", "PowerPoint",
    "Tableau", "Power BI", "ReFrame", "PMIx", "PRRTE", "HPC"
  ];

  const ENGINEERING_SKILLS = [
    // Mechanical / manufacturing / product design.
    { name: "SolidWorks", disciplines: ["mechanical"], aliases: ["SolidWorks"] },
    { name: "AutoCAD", disciplines: ["mechanical", "civil"], aliases: ["AutoCAD"] },
    { name: "CAD", disciplines: ["mechanical", "aero", "civil"], aliases: ["CAD", "computer-aided design", "computer aided design"] },
    { name: "Siemens NX", disciplines: ["mechanical", "aero"], aliases: ["Siemens NX", "NX CAD", "Unigraphics"] },
    { name: "Creo", disciplines: ["mechanical", "aero"], aliases: ["Creo", "Pro/ENGINEER", "ProE"] },
    { name: "CATIA", disciplines: ["mechanical", "aero"], aliases: ["CATIA"] },
    { name: "Fusion 360", disciplines: ["mechanical"], aliases: ["Fusion 360", "Autodesk Fusion"] },
    { name: "ANSYS", disciplines: ["mechanical", "aero"], aliases: ["ANSYS", "Ansys Mechanical", "Ansys Fluent"] },
    { name: "Abaqus", disciplines: ["mechanical", "aero"], aliases: ["Abaqus"] },
    { name: "FEA", disciplines: ["mechanical", "aero"], aliases: ["FEA", "finite element analysis", "finite-element analysis"] },
    { name: "CFD", disciplines: ["mechanical", "aero"], aliases: ["CFD", "computational fluid dynamics"] },
    { name: "GD&T", disciplines: ["mechanical", "manufacturing"], aliases: ["GD&T", "geometric dimensioning and tolerancing", "geometric dimensioning & tolerancing"] },
    { name: "DFM", disciplines: ["mechanical", "manufacturing"], aliases: ["DFM", "design for manufacturability", "design for manufacturing"] },
    { name: "DFA", disciplines: ["mechanical", "manufacturing"], aliases: ["DFA", "design for assembly"] },
    { name: "DFMA", disciplines: ["mechanical", "manufacturing"], aliases: ["DFMA", "design for manufacturing and assembly", "design for manufacture and assembly"] },
    { name: "FMEA", disciplines: ["mechanical", "manufacturing", "systems"], aliases: ["FMEA", "failure mode and effects analysis", "failure modes and effects analysis"] },
    { name: "CNC", disciplines: ["mechanical", "manufacturing"], aliases: ["CNC", "computer numerical control"] },
    { name: "Additive manufacturing", disciplines: ["mechanical", "manufacturing"], aliases: ["additive manufacturing", "3D printing", "3-D printing"] },
    { name: "Injection molding", disciplines: ["mechanical", "manufacturing"], aliases: ["injection molding", "injection moulding"] },
    { name: "Sheet metal", disciplines: ["mechanical", "manufacturing"], aliases: ["sheet metal", "sheet-metal"] },
    { name: "Composites", disciplines: ["mechanical", "aero"], aliases: ["composites", "composite materials"] },
    { name: "Tolerance analysis", disciplines: ["mechanical", "manufacturing"], aliases: ["tolerance analysis", "tolerance stack-up", "tolerance stackup"] },
    { name: "Thermodynamics", disciplines: ["mechanical", "aero"], aliases: ["thermodynamics"] },
    { name: "Heat transfer", disciplines: ["mechanical", "aero"], aliases: ["heat transfer"] },
    { name: "Fluid mechanics", disciplines: ["mechanical", "aero"], aliases: ["fluid mechanics", "fluid dynamics"] },
    { name: "Mechanics of materials", disciplines: ["mechanical", "aero"], aliases: ["mechanics of materials", "strength of materials"] },
    { name: "Vibrations", disciplines: ["mechanical", "aero"], aliases: ["vibrations", "vibration analysis", "modal analysis"] },

    // Aerospace / astronautical.
    { name: "Aerodynamics", disciplines: ["aero"], aliases: ["aerodynamics", "aerodynamic analysis"] },
    { name: "Propulsion", disciplines: ["aero"], aliases: ["propulsion", "rocket propulsion", "air-breathing propulsion"] },
    { name: "Orbital mechanics", disciplines: ["aero"], aliases: ["orbital mechanics", "astrodynamics"] },
    { name: "Flight dynamics", disciplines: ["aero"], aliases: ["flight dynamics", "flight mechanics"] },
    { name: "GNC", disciplines: ["aero", "controls"], aliases: ["GNC", "guidance navigation and control", "guidance, navigation, and control", "guidance, navigation & control"] },
    { name: "Avionics", disciplines: ["aero", "electrical"], aliases: ["avionics"] },
    { name: "Spacecraft systems", disciplines: ["aero", "systems"], aliases: ["spacecraft systems", "space systems"] },
    { name: "Satellite systems", disciplines: ["aero", "systems"], aliases: ["satellite systems", "satellite engineering"] },
    { name: "Flight test", disciplines: ["aero", "test"], aliases: ["flight test", "flight testing"] },
    { name: "Wind tunnel testing", disciplines: ["aero"], aliases: ["wind tunnel", "wind-tunnel testing", "wind tunnel testing"] },
    { name: "Structural analysis", disciplines: ["mechanical", "aero", "civil"], aliases: ["structural analysis"] },

    // Controls / mechatronics / hardware that commonly overlap mechanical and aerospace.
    { name: "Controls", disciplines: ["controls", "mechanical", "aero"], aliases: ["control systems", "controls engineering", "feedback control"] },
    { name: "PID", disciplines: ["controls", "mechanical", "aero"], aliases: ["PID", "PID control", "proportional-integral-derivative"] },
    { name: "State-space", disciplines: ["controls", "aero"], aliases: ["state-space", "state space"] },
    { name: "Kalman filter", disciplines: ["controls", "aero", "robotics"], aliases: ["Kalman filter", "Kalman filtering"] },
    { name: "Sensor fusion", disciplines: ["controls", "aero", "robotics"], aliases: ["sensor fusion"] },
    { name: "ROS 2", disciplines: ["robotics", "controls"], aliases: ["ROS 2", "ROS2"] },
    { name: "Embedded systems", disciplines: ["electrical", "aero", "robotics"], aliases: ["embedded systems", "embedded system"] },
    { name: "RTOS", disciplines: ["electrical", "aero", "robotics"], aliases: ["RTOS", "real-time operating system", "real time operating system", "FreeRTOS"] },
    { name: "CAN", disciplines: ["electrical", "aero", "automotive"], aliases: ["CAN bus", "Controller Area Network"] },
    { name: "I2C", disciplines: ["electrical", "embedded"], aliases: ["I2C", "I²C"] },
    { name: "SPI", disciplines: ["electrical", "embedded"], aliases: ["SPI bus", "Serial Peripheral Interface"] },
    { name: "UART", disciplines: ["electrical", "embedded"], aliases: ["UART"] },
  ];

  const SKILL_VOCABULARY = [...BASE_SKILLS, ...ENGINEERING_SKILLS.map(skill => skill.name)];

  const MAJORS = [
    "Computer Science", "Computer Engineering", "Electrical Engineering", "Data Science", "Information Systems",
    "Information Technology", "Statistics", "Mathematics", "Business Analytics", "Finance", "Economics",
    "Mechanical Engineering", "Software Engineering", "Aerospace Engineering", "Astronautical Engineering", "Civil Engineering",
    "Chemical Engineering", "Biomedical Engineering", "Industrial Engineering", "Materials Engineering",
    "Mechatronics Engineering", "Robotics Engineering"
  ];

  function normalize(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function unique(values) {
    return [...new Set((values || []).map(normalize).filter(Boolean))];
  }

  function splitList(value) {
    if (Array.isArray(value)) return unique(value);
    return unique(String(value || "").split(/[\n,;]+/));
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function containsSkill(text, skill) {
    const source = String(text || "");
    const escaped = escapeRegExp(skill)
      .replace(/\\ /g, "\\s+")
      .replace(/Node\\\.js/i, "Node(?:\\.js|js)");
    const prefix = /^[A-Za-z0-9]/.test(skill) ? "(?:^|[^A-Za-z0-9+#])" : "";
    const suffix = /[A-Za-z0-9]$/.test(skill) ? "(?=$|[^A-Za-z0-9+#])" : "";
    return new RegExp(`${prefix}${escaped}${suffix}`, "i").test(source);
  }

  function extractGraduation(text) {
    const source = String(text || "");
    const datePattern = /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b/gi;
    const candidates = [];
    for (const match of source.matchAll(datePattern)) {
      const start = Math.max(0, match.index - 140);
      const prefix = source.slice(start, match.index);
      const localPrefix = prefix.split(/[\n\r]/).pop() || prefix;
      const explicit = /(?:expected|anticipated|graduat(?:ion|ing)|degree\s+expected|class\s+of)[^\n\r]{0,50}$/i.test(prefix);
      const higherEducationPattern = /\b(?:university|college|bachelor(?:'s)?|master(?:'s)?|associate(?:'s)?|B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?)\b/i;
      const majorPattern = new RegExp(MAJORS.map(escapeRegExp).join("|"), "i");
      const higherEducation = higherEducationPattern.test(localPrefix)
        || majorPattern.test(localPrefix)
        || higherEducationPattern.test(prefix.slice(-90))
        || majorPattern.test(prefix.slice(-90));
      const highSchool = /\b(?:high school|secondary school|GED|high school diploma)\b/i.test(localPrefix)
        || /\b(?:high school|secondary school|GED|high school diploma)\b/i.test(prefix.slice(-70));
      let score = 0;
      if (explicit) score += 4;
      if (higherEducation) score += 6;
      if (highSchool) score -= 12;
      candidates.push({
        value: `${match[1][0].toUpperCase()}${match[1].slice(1).toLowerCase()} ${match[2]}`,
        score,
        year: Number(match[2]),
        index: match.index,
      });
    }
    const eligible = candidates.filter(candidate => candidate.score > 0);
    if (!eligible.length) return "";
    eligible.sort((a, b) => b.score - a.score || b.year - a.year || a.index - b.index);
    return eligible[0].value;
  }

  function extractDegree(text) {
    const source = String(text || "");
    if (/\b(?:B\.?S\.?|Bachelor(?:'s)? of Science)\b/i.test(source)) return "Bachelor of Science";
    if (/\b(?:B\.?A\.?|Bachelor(?:'s)? of Arts)\b/i.test(source)) return "Bachelor of Arts";
    if (/\bBachelor(?:'s)?\b/i.test(source)) return "Bachelor's degree";
    if (/\bMaster(?:'s)?\b|\bM\.?S\.?\b/i.test(source)) return "Master's degree";
    return "";
  }

  function extractMajor(text) {
    return MAJORS.find(major => new RegExp(`\\b${escapeRegExp(major)}\\b`, "i").test(String(text || ""))) || "";
  }

  function extractAuthorization(text) {
    const source = String(text || "");
    const citizen = /\b(?:U\.?S\.?|United States) citizen(?:ship)?\b/i.test(source) ? "U.S. citizen" : "Unknown / not provided";
    let workAuthorization = "Unknown / not provided";
    if (/\bauthori[sz]ed to work\b[^\n]{0,60}\bwithout sponsorship\b|\bno sponsorship (?:is )?required\b/i.test(source)) {
      workAuthorization = "Authorized to work in the U.S. without sponsorship";
    } else if (/\b(?:need|require)s? (?:visa )?sponsorship\b|\bsponsorship required\b/i.test(source)) {
      workAuthorization = "Needs visa sponsorship";
    }
    if (citizen === "U.S. citizen" && workAuthorization === "Unknown / not provided") {
      workAuthorization = "Authorized to work in the U.S. without sponsorship";
    }
    return { citizenship: citizen, workAuthorization };
  }

  function extractClearance(text) {
    const source = String(text || "");
    if (/\bactive\b[^\n]{0,30}\b(?:top secret|TS\/SCI)\b|\b(?:top secret|TS\/SCI)\b[^\n]{0,30}\bactive\b/i.test(source)) return "Active Top Secret clearance";
    if (/\bactive\b[^\n]{0,30}\bsecret clearance\b|\bsecret clearance\b[^\n]{0,30}\bactive\b/i.test(source)) return "Active Secret clearance";
    if (/\b(?:eligible|ability) to obtain\b[^\n]{0,40}\bclearance\b/i.test(source)) return "Eligible / able to obtain a clearance";
    if (/\b(?:no|without) (?:active )?(?:security )?clearance\b/i.test(source)) return "No active security clearance";
    return "Unknown / not provided";
  }

  function extractSupportedSkills(text) {
    const source = String(text || "");
    const base = BASE_SKILLS.filter(skill => containsSkill(source, skill));
    const engineering = ENGINEERING_SKILLS
      .filter(skill => skill.aliases.some(alias => containsSkill(source, alias)))
      .map(skill => skill.name);
    return unique([...base, ...engineering]);
  }

  function extractExperienceEvidence(text) {
    const source = String(text || "").replace(/\r/g, "");
    const evidence = [];
    const sectionPattern = /(?:^|\n)\s*(?:(?:professional|work)\s+experience|experience|employment)\s*:?\s*\n([\s\S]*?)(?=(?:\n\s*(?:education|projects?|skills?|leadership|activities|awards?|certifications?|coursework|research)\s*:?\s*(?:\n|$))|$)/gi;
    for (const match of source.matchAll(sectionPattern)) {
      for (const rawLine of String(match[1] || "").split(/\n+/)) {
        const line = rawLine.replace(/^\s*[•*\-–—]+\s*/, "").replace(/\s+/g, " ").trim();
        if (line.length >= 4) evidence.push(line.slice(0, 240));
      }
    }
    return unique(evidence).slice(0, 16);
  }

  function extractResumeHints(text) {
    const source = String(text || "");
    const authorization = extractAuthorization(source);
    return {
      graduation: extractGraduation(source),
      degree: extractDegree(source),
      major: extractMajor(source),
      supportedSkills: extractSupportedSkills(source),
      experienceEvidence: extractExperienceEvidence(source),
      citizenship: authorization.citizenship,
      workAuthorization: authorization.workAuthorization,
      securityClearance: extractClearance(source),
    };
  }

  async function loadPdfJs(importer) {
    const load = importer || (url => import(url));
    const pdfjs = await load(PDFJS_URL);
    if (pdfjs?.GlobalWorkerOptions) pdfjs.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
    return pdfjs;
  }

  async function readResumeFile(file, importer) {
    if (!file) throw new Error("Choose a resume file first.");
    const name = String(file.name || "").toLowerCase();
    const type = String(file.type || "").toLowerCase();
    if (type === "application/pdf" || name.endsWith(".pdf")) {
      const pdfjs = await loadPdfJs(importer);
      const bytes = new Uint8Array(await file.arrayBuffer());
      const pdf = await pdfjs.getDocument({ data: bytes }).promise;
      const pages = [];
      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
        const page = await pdf.getPage(pageNumber);
        const content = await page.getTextContent();
        const pageText = content.items
          .map(item => `${item.str || ""}${item.hasEOL ? "\n" : " "}`)
          .join("")
          .trim();
        pages.push(pageText);
      }
      return pages.join("\n");
    }
    if (type.startsWith("text/") || /\.(txt|md|markdown)$/i.test(name)) return file.text();
    throw new Error("Use a PDF, TXT, or Markdown resume for local parsing.");
  }

  function selectedCareerAreas(ids) {
    const wanted = new Set(ids || []);
    return CAREER_AREAS.filter(area => wanted.has(area.id)).map(area => area.id);
  }

  function defaultRoleFamilyIdsForAreas(areaIds) {
    const wanted = new Set(areaIds || []);
    return ROLE_FAMILIES
      .filter(family => (family.careerAreas || []).some(area => wanted.has(area)))
      .map(family => family.id);
  }

  function selectedRoleFamilies(ids, areaIds) {
    const wanted = new Set(ids || []);
    const areas = new Set(areaIds || []);
    return ROLE_FAMILIES
      .filter(family => wanted.has(family.id) && (family.careerAreas || []).some(area => areas.has(area)))
      .map(family => ({ ...family }));
  }

  function buildProfile(values, existing) {
    const base = existing && typeof existing === "object" ? existing : {};
    const careerAreas = selectedCareerAreas(values.careerAreaIds?.length ? values.careerAreaIds : ["cs"]);
    const effectiveCareerAreas = careerAreas.length ? careerAreas : ["cs"];
    const requestedRoleIds = values.roleFamilyIds?.length
      ? values.roleFamilyIds
      : defaultRoleFamilyIdsForAreas(effectiveCareerAreas);
    const roleFamilies = selectedRoleFamilies(requestedRoleIds, effectiveCareerAreas);
    const supportedSkills = splitList(values.supportedSkills);
    const cautiousSkills = splitList(values.cautiousSkills);
    const experienceEvidence = unique(
      (Array.isArray(values.experienceEvidence) ? values.experienceEvidence : String(values.experienceEvidence || "").split(/\n+/))
        .map(value => String(value || "").replace(/\s+/g, " ").trim().slice(0, 240))
        .filter(value => value.length >= 4)
    ).slice(0, 16);
    const roleKeywords = roleFamilies.flatMap(family => family.keywords || []);
    const baseZips = splitList(values.baseZips).filter(zip => /^\d{5}$/.test(zip));
    const preferredStates = splitList(values.preferredStates).map(value => value.toUpperCase()).filter(value => /^[A-Z]{2}$/.test(value));
    const citizenship = normalize(values.citizenship) || "Unknown / not provided";
    let workAuthorization = normalize(values.workAuthorization) || "Unknown / not provided";
    if (citizenship === "U.S. citizen" && workAuthorization === "Unknown / not provided") {
      workAuthorization = "Authorized to work in the U.S. without sponsorship";
    }
    const preferredProfiles = unique([
      ...effectiveCareerAreas,
      ...(roleFamilies.some(family => family.id === "analytics") ? ["tech-business"] : []),
    ]);
    return {
      ...base,
      version: 1,
      careerAreas: effectiveCareerAreas,
      targetTerm: normalize(values.targetTerm) || "Summer 2027",
      opportunityTypes: values.opportunityTypes?.length ? unique(values.opportunityTypes) : ["internship", "co-op"],
      excludeGraduateOnly: values.excludeGraduateOnly !== false,
      facts: {
        ...(base.facts || {}),
        graduation: normalize(values.graduation),
        degree: normalize(values.degree),
        major: normalize(values.major),
        citizenship,
        workAuthorization,
        securityClearance: normalize(values.securityClearance) || "Unknown / not provided",
        supportedSkills,
        cautiousSkills,
        experienceEvidence,
      },
      preferredProfiles,
      supportedKeywords: unique([...supportedSkills, ...roleKeywords]),
      cautiousKeywords: cautiousSkills,
      roleFamilies,
      baseZips,
      baseLabels: baseZips,
      preferredStates,
      nearbyMiles: Math.max(5, Math.min(500, Number(values.nearbyMiles || 50))),
      remoteRelevant: Boolean(values.remoteRelevant),
      relocationAllowed: Boolean(values.relocationAllowed),
    };
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function field(label, input) {
    const wrapper = element("label", "apply-next-profile-field");
    wrapper.append(element("span", "", label), input);
    return wrapper;
  }

  function input(name, value, type) {
    const node = document.createElement("input");
    node.name = name;
    node.type = type || "text";
    node.value = value || "";
    node.autocomplete = "off";
    return node;
  }

  function select(name, options, value) {
    const node = document.createElement("select");
    node.name = name;
    for (const option of options) {
      const item = document.createElement("option");
      item.value = option;
      item.textContent = option;
      item.selected = option === value;
      node.append(item);
    }
    return node;
  }

  function textarea(name, value, rows) {
    const node = document.createElement("textarea");
    node.name = name;
    node.rows = rows || 3;
    node.value = value || "";
    node.autocomplete = "off";
    node.spellcheck = false;
    return node;
  }

  function existingValues(profile) {
    const facts = profile?.facts || {};
    return {
      targetTerm: profile?.targetTerm || "Summer 2027",
      graduation: facts.graduation || "",
      degree: facts.degree || "",
      major: facts.major || "",
      citizenship: facts.citizenship || "Unknown / not provided",
      workAuthorization: facts.workAuthorization || "Unknown / not provided",
      securityClearance: facts.securityClearance || "Unknown / not provided",
      supportedSkills: (facts.supportedSkills || []).join(", "),
      cautiousSkills: (facts.cautiousSkills || []).join(", "),
      experienceEvidence: (facts.experienceEvidence || []).join("\n"),
      careerAreaIds: (() => {
        const explicit = selectedCareerAreas(profile?.careerAreas || []);
        if (explicit.length) return explicit;
        const inferred = selectedCareerAreas(profile?.preferredProfiles || []);
        return inferred.length ? inferred : ["cs"];
      })(),
      roleFamilyIds: (profile?.roleFamilies || []).map(family => family.id),
      baseZips: (profile?.baseZips || []).join(", "),
      preferredStates: (profile?.preferredStates || []).join(", "),
      nearbyMiles: profile?.nearbyMiles || 50,
      remoteRelevant: profile?.remoteRelevant !== false,
      relocationAllowed: profile?.relocationAllowed !== false,
      opportunityTypes: profile?.opportunityTypes || ["internship", "co-op"],
    };
  }

  function readForm(form) {
    const get = name => form.querySelector(`[name="${name}"]`);
    return {
      targetTerm: get("targetTerm")?.value,
      graduation: get("graduation")?.value,
      degree: get("degree")?.value,
      major: get("major")?.value,
      citizenship: get("citizenship")?.value,
      workAuthorization: get("workAuthorization")?.value,
      securityClearance: get("securityClearance")?.value,
      supportedSkills: get("supportedSkills")?.value,
      cautiousSkills: get("cautiousSkills")?.value,
      experienceEvidence: get("experienceEvidence")?.value,
      baseZips: get("baseZips")?.value,
      preferredStates: get("preferredStates")?.value,
      nearbyMiles: get("nearbyMiles")?.value,
      remoteRelevant: Boolean(get("remoteRelevant")?.checked),
      relocationAllowed: Boolean(get("relocationAllowed")?.checked),
      excludeGraduateOnly: true,
      careerAreaIds: [...form.querySelectorAll('[name="careerArea"]:checked')].map(node => node.value),
      roleFamilyIds: [...form.querySelectorAll('[name="roleFamily"]:checked')].map(node => node.value),
      opportunityTypes: [...form.querySelectorAll('[name="opportunityType"]:checked')].map(node => node.value),
    };
  }

  function applyHints(form, hints) {
    const setIf = (name, value) => {
      const node = form.querySelector(`[name="${name}"]`);
      if (node && value) node.value = value;
    };
    setIf("graduation", hints.graduation);
    setIf("degree", hints.degree);
    setIf("major", hints.major);
    if (hints.citizenship !== "Unknown / not provided") setIf("citizenship", hints.citizenship);
    if (hints.workAuthorization !== "Unknown / not provided") setIf("workAuthorization", hints.workAuthorization);
    if (hints.securityClearance !== "Unknown / not provided") setIf("securityClearance", hints.securityClearance);
    if (hints.supportedSkills?.length) {
      const node = form.querySelector('[name="supportedSkills"]');
      if (node) node.value = unique([...splitList(node.value), ...hints.supportedSkills]).join(", ");
    }
    if (hints.experienceEvidence?.length) {
      const node = form.querySelector('[name="experienceEvidence"]');
      if (node) {
        const existing = String(node.value || "").split(/\n+/).map(value => value.trim()).filter(Boolean);
        node.value = unique([...existing, ...hints.experienceEvidence]).join("\n");
      }
    }
  }

  function refreshApplyNextPanel(doc = document) {
    const button = doc.querySelector("#applyNextBtn");
    const panel = doc.querySelector("#applyNextPanel");
    if (!button || !panel || panel.classList.contains("hidden")) return;
    panel.classList.add("hidden");
    panel.dataset.view = "";
    button.setAttribute("aria-expanded", "false");
    button.click();
  }

  function renderEditor(panel, profile) {
    const ui = window.YartchivesApplyNextUI;
    if (!ui) return;
    const values = existingValues(profile);
    panel.innerHTML = "";

    const header = element("div", "apply-next-heading");
    const copy = element("div");
    copy.append(
      element("p", "eyebrow", "private browser profile"),
      element("h2", "", "Set up Apply Next"),
      element("p", "muted", "Upload a resume to prefill what it actually says, then confirm the few eligibility and strategy facts resumes often leave out. The raw resume is never saved or uploaded; only the profile you confirm is stored in this browser.")
    );
    const back = element("button", "ghost-btn apply-next-back", "← Back to Yartchives");
    back.type = "button";
    back.addEventListener("click", () => {
      if (typeof ui.returnToEntryChoice === "function") ui.returnToEntryChoice();
    });
    header.append(copy, back);
    panel.append(header);

    const form = element("form", "apply-next-profile-wizard");
    form.noValidate = true;

    const resumeCard = element("section", "apply-next-profile-section");
    resumeCard.append(element("h3", "", "1. Prefill from your resume"));
    resumeCard.append(element("p", "muted", "PDF, TXT, or Markdown. PDF parsing runs in your browser; the parser library is downloaded only when needed."));
    const file = input("resumeFile", "", "file");
    file.accept = ".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown";
    const paste = textarea("resumeText", "", 6);
    paste.placeholder = "Or paste resume text here…";
    const status = element("p", "apply-next-profile-status muted", "Nothing imported yet.");
    const parsePaste = element("button", "secondary-btn", "Use pasted resume");
    parsePaste.type = "button";
    resumeCard.append(field("Resume file", file), field("Or paste resume text", paste), parsePaste, status);
    form.append(resumeCard);

    const basics = element("section", "apply-next-profile-section");
    basics.append(element("h3", "", "2. Review the basics"));
    const basicsGrid = element("div", "apply-next-profile-grid");
    const targetTermField = element("div", "apply-next-profile-field");
    const targetTermOption = element("label", "apply-next-profile-check");
    const targetTerm = input("targetTerm", "Summer 2027", "radio");
    targetTerm.checked = true;
    targetTermOption.append(targetTerm, document.createTextNode("Summer 2027"));
    targetTermField.append(element("span", "", "When are you looking?"), targetTermOption);
    const degree = input("degree", values.degree, "hidden");
    basicsGrid.append(
      targetTermField,
      field("When are you graduating (month year)", input("graduation", values.graduation)),
      field("Major", input("major", values.major))
    );
    basics.append(basicsGrid, degree);
    form.append(basics);

    const eligibility = element("section", "apply-next-profile-section");
    eligibility.append(element("h3", "", "3. Confirm eligibility facts"));
    eligibility.append(element("p", "muted", "These are not guessed when a resume omits them. Unknown stays unknown."));
    const eligibilityGrid = element("div", "apply-next-profile-grid");
    eligibilityGrid.append(
      field("Citizenship", select("citizenship", ["Unknown / not provided", "U.S. citizen", "Not a U.S. citizen"], values.citizenship)),
      field("U.S. work authorization", select("workAuthorization", ["Unknown / not provided", "Authorized to work in the U.S. without sponsorship", "Needs visa sponsorship"], values.workAuthorization)),
      field("Security clearance", select("securityClearance", ["Unknown / not provided", "No active security clearance", "Eligible / able to obtain a clearance", "Active Secret clearance", "Active Top Secret clearance"], values.securityClearance))
    );
    eligibility.append(eligibilityGrid);
    form.append(eligibility);

    const skills = element("section", "apply-next-profile-section");
    skills.append(element("h3", "", "4. Confirm skills"));
    skills.append(element("p", "muted", "Keep skills you can defend in an interview under Supported. Put light exposure under Cautious. Resume-backed work evidence is kept separately so explicit experience requirements can use stronger evidence than a skills list alone."));
    const skillsGrid = element("div", "apply-next-profile-grid");
    skillsGrid.append(
      field("Supported skills", textarea("supportedSkills", values.supportedSkills, 4)),
      field("Cautious / light exposure", textarea("cautiousSkills", values.cautiousSkills, 4)),
      field("Work experience evidence (one resume-backed line per entry)", textarea("experienceEvidence", values.experienceEvidence, 5))
    );
    skills.append(skillsGrid);
    form.append(skills);

    const strategy = element("section", "apply-next-profile-section");
    strategy.append(element("h3", "", "5. What are you looking for?"));
    strategy.append(element("p", "muted", "Choose Computer Science, Engineering, Finance, or any combination. Role families below are scoped to the career areas you select."));

    const careerWrap = element("div", "apply-next-profile-checks");
    const selectedAreas = new Set(values.careerAreaIds?.length ? values.careerAreaIds : ["cs"]);
    for (const area of CAREER_AREAS) {
      const label = element("label", "apply-next-profile-check");
      const checkbox = input("careerArea", area.id, "checkbox");
      checkbox.value = area.id;
      checkbox.checked = selectedAreas.has(area.id);
      label.append(checkbox, document.createTextNode(area.label));
      careerWrap.append(label);
    }

    const roleWrap = element("div", "apply-next-profile-role-groups");
    const defaultRoleIds = defaultRoleFamilyIdsForAreas([...selectedAreas]);
    const selectedRoles = new Set(values.roleFamilyIds.length ? values.roleFamilyIds : defaultRoleIds);

    function renderRoleFamilies() {
      roleWrap.innerHTML = "";
      const activeAreas = new Set([...form.querySelectorAll('[name="careerArea"]:checked')].map(node => node.value));
      const renderedFamilies = new Set();
      for (const area of CAREER_AREAS) {
        if (!activeAreas.has(area.id)) continue;
        const families = ROLE_FAMILIES.filter(item =>
          (item.careerAreas || []).includes(area.id) && !renderedFamilies.has(item.id)
        );
        if (!families.length) continue;
        const group = element("div", "apply-next-profile-role-group");
        group.append(element("p", "apply-next-profile-subhead", area.label));
        const checks = element("div", "apply-next-profile-checks");
        for (const family of families) {
          renderedFamilies.add(family.id);
          const label = element("label", "apply-next-profile-check");
          const checkbox = input("roleFamily", family.id, "checkbox");
          checkbox.value = family.id;
          checkbox.checked = selectedRoles.has(family.id);
          label.append(checkbox, document.createTextNode(family.label));
          checks.append(label);
        }
        group.append(checks);
        roleWrap.append(group);
      }
    }

    roleWrap.addEventListener("change", event => {
      const target = event?.target;
      if (!target || target.name !== "roleFamily") return;
      if (target.checked) selectedRoles.add(target.value);
      else selectedRoles.delete(target.value);
    });

    careerWrap.addEventListener("change", event => {
      const target = event?.target;
      if (!target || target.name !== "careerArea") return;
      const checkedAreas = [...careerWrap.querySelectorAll('[name="careerArea"]:checked')].map(node => node.value);
      if (!checkedAreas.length) {
        target.checked = true;
        return;
      }
      if (target.checked) {
        for (const id of defaultRoleFamilyIdsForAreas([target.value])) selectedRoles.add(id);
      }
      renderRoleFamilies();
    });
    renderRoleFamilies();
    const typeWrap = element("div", "apply-next-profile-checks");
    const selectedTypes = new Set(values.opportunityTypes);
    for (const type of ["internship", "co-op"]) {
      const label = element("label", "apply-next-profile-check");
      const checkbox = input("opportunityType", type, "checkbox");
      checkbox.value = type;
      checkbox.checked = selectedTypes.has(type);
      label.append(checkbox, document.createTextNode(type === "co-op" ? "Co-op" : "Internship"));
      typeWrap.append(label);
    }
    strategy.append(element("p", "apply-next-profile-subhead", "Career areas"), careerWrap, roleWrap, element("p", "apply-next-profile-subhead", "Opportunity types"), typeWrap);
    form.append(strategy);

    const location = element("section", "apply-next-profile-section");
    location.append(element("h3", "", "6. Location preferences"));
    const locationGrid = element("div", "apply-next-profile-grid");
    locationGrid.append(
      field("Base ZIPs", input("baseZips", values.baseZips)),
      field("Nearby miles", input("nearbyMiles", values.nearbyMiles, "number"))
    );
    location.append(locationGrid);
    const locationChecks = element("div", "apply-next-profile-checks");
    for (const [name, labelText, checked] of [
      ["remoteRelevant", "Remote roles are relevant", values.remoteRelevant],
      ["relocationAllowed", "Open to relocating for a worthwhile role", values.relocationAllowed],
    ]) {
      const label = element("label", "apply-next-profile-check");
      const checkbox = input(name, "", "checkbox");
      checkbox.checked = checked;
      label.append(checkbox, document.createTextNode(labelText));
      locationChecks.append(label);
    }
    location.append(locationChecks);
    form.append(location);

    const error = element("p", "error-box hidden");
    const actions = element("div", "apply-next-profile-actions");
    const save = element("button", "primary-btn", profile ? "Save profile" : "Create profile");
    save.type = "submit";
    actions.append(save);
    if (profile) {
      const clear = element("button", "text-btn", "Clear saved profile");
      clear.type = "button";
      clear.addEventListener("click", () => {
        localStorage.removeItem(ui.STORAGE_KEY);
        renderEditor(panel, null);
      });
      actions.append(clear);
    }
    form.append(error, actions);

    async function parseResumeText(text, sourceLabel) {
      const hints = extractResumeHints(text);
      applyHints(form, hints);
      const found = [hints.graduation, hints.degree, hints.major, ...(hints.supportedSkills || []), ...(hints.experienceEvidence || [])].filter(Boolean).length;
      status.textContent = found
        ? `Prefilled ${found} resume-backed facts from ${sourceLabel}. Review them before saving.`
        : `No reliable structured facts found in ${sourceLabel}; you can still fill the profile manually.`;
    }

    file.addEventListener("change", async () => {
      if (!file.files?.[0]) return;
      status.textContent = "Reading resume locally…";
      try {
        const text = await readResumeFile(file.files[0]);
        await parseResumeText(text, file.files[0].name || "resume");
      } catch (err) {
        status.textContent = err.message || "Could not read this resume.";
      }
    });

    parsePaste.addEventListener("click", async () => {
      const text = paste.value.trim();
      if (!text) {
        status.textContent = "Paste resume text first.";
        return;
      }
      await parseResumeText(text, "pasted text");
    });

    form.addEventListener("submit", event => {
      event.preventDefault();
      try {
        const profileToSave = buildProfile(readForm(form), profile || {});
        const checked = ui.validateProfile(profileToSave);
        if (!checked.ok) throw new Error(checked.error);
        ui.saveProfile(localStorage, profileToSave);
        error.textContent = "";
        error.classList.add("hidden");
        refreshApplyNextPanel();
      } catch (err) {
        error.textContent = err.message || "Could not save this profile.";
        error.classList.remove("hidden");
      }
    });

    panel.append(form);
  }

  function parseLegacyProfile(textarea) {
    try {
      return textarea?.value ? JSON.parse(textarea.value) : null;
    } catch (_) {
      return null;
    }
  }

  function enhancePanel(panel) {
    if (!panel || panel.querySelector(".apply-next-profile-wizard")) return;
    const legacy = panel.querySelector("#applyNextProfileInput");
    if (!legacy) return;
    const ui = window.YartchivesApplyNextUI;
    const profile = parseLegacyProfile(legacy) || ui?.loadProfile?.(localStorage) || null;
    renderEditor(panel, profile);
  }

  function init() {
    const start = () => {
      const panel = document.querySelector("#applyNextPanel");
      if (!panel) return;
      enhancePanel(panel);
      const observer = new MutationObserver(() => enhancePanel(panel));
      observer.observe(panel, { childList: true, subtree: true });
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
    else start();
  }

  return {
    PDFJS_URL,
    PDFJS_WORKER_URL,
    CAREER_AREAS,
    ROLE_FAMILIES,
    SKILL_VOCABULARY,
    ENGINEERING_SKILLS,
    defaultRoleFamilyIdsForAreas,
    splitList,
    containsSkill,
    extractSupportedSkills,
    extractExperienceEvidence,
    extractResumeHints,
    readResumeFile,
    buildProfile,
    refreshApplyNextPanel,
    init,
  };
});
