from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import posting_requirements as shared
import workday_inspector as workday
import icims_inspector as icims
import greenhouse_inspector as greenhouse


class PostingRequirementTests(unittest.TestCase):
    def test_provider_adapters_share_one_extractor(self):
        self.assertIs(workday.extract_requirements, shared.extract_requirements)
        self.assertIs(icims.extract_requirements, shared.extract_requirements)
        self.assertIs(workday.normalize_description, shared.normalize_description)
        self.assertIs(icims.normalize_description, shared.normalize_description)
        self.assertIs(greenhouse.posting_requirements, shared)

    def test_required_preferred_negated_and_unknown_semantics(self):
        result = shared.extract_requirements([
            "Required Qualifications:",
            "C++ development experience is required.",
            "U.S. citizenship is not required.",
            "Visa sponsorship is not required.",
            "Preferred Qualifications:",
            "Linux experience preferred.",
        ])
        self.assertEqual(result["skills"]["classification"], "mixed")
        self.assertEqual(result["skills"]["required"][0]["technologies"], ["C++"])
        self.assertEqual(result["skills"]["preferred"][0]["technologies"], ["Linux"])
        self.assertNotIn("C", result["skills"]["required"][0]["technologies"])
        self.assertEqual(result["citizenship"]["classification"], "not_required")
        self.assertEqual(result["work_authorization"]["classification"], "not_required")
        self.assertEqual(result["graduation"]["classification"], "unknown")

    def test_generic_what_were_looking_for_section_is_required_context(self):
        result = shared.extract_requirements([
            "What we're looking for:",
            "Dynamic self-starter with a strong curiosity for problem-solving and innovation.",
            "Foundational knowledge of Python, SQL/PLSQL, Tableau, and Oracle (coursework or project experience acceptable).",
            "Interest in data engineering, analytics, and applying AI/ML to practical business challenges.",
            "Strong communication skills and the ability to collaborate across technical and business teams.",
            "What you'll do:",
            "Build Python data pipelines.",
        ])
        skills = result["skills"]
        self.assertEqual(skills["classification"], "required")
        technology_fact = next(fact for fact in skills["required"] if fact.get("technologies"))
        self.assertEqual(
            technology_fact["technologies"],
            ["Python", "SQL", "Tableau", "Oracle"],
        )
        self.assertTrue(any("communication skills" in fact["statement"].lower() for fact in skills["required"]))
        self.assertFalse(any("Build Python data pipelines" in fact["statement"] for fact in skills["required"]))

    def test_quantified_preference_remains_preferred(self):
        result = shared.extract_requirements([
            "Preferred but not required:",
            "At least one prior project using Linux and Git.",
        ])
        self.assertEqual(result["skills"]["classification"], "preferred")
        self.assertEqual(result["skills"]["required"], [])
        self.assertEqual(result["skills"]["preferred"][0]["technologies"], ["Git", "Linux"])

    def test_normalization_preserves_stable_block_lines(self):
        text, lines = shared.normalize_description(
            "<h2>Required Qualifications</h2><p>C++ required.<br>Linux preferred.</p>"
        )
        self.assertEqual(lines, ["Required Qualifications", "C++ required.", "Linux preferred."])
        self.assertEqual(text, "Required Qualifications\nC++ required.\nLinux preferred.")


if __name__ == "__main__":
    unittest.main()
