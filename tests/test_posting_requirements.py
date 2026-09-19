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

    def test_typographic_apostrophes_share_heading_semantics(self):
        result = shared.extract_requirements([
            "What we’re looking for:",
            "Foundational knowledge of Python, SQL/PLSQL, Tableau, and Oracle (coursework or project experience acceptable).",
            "Strong communication skills and the ability to collaborate across technical and business teams.",
            "What you’ll do:",
            "Build Python data pipelines.",
        ])
        skills = result["skills"]
        self.assertEqual(skills["classification"], "required")
        technology_fact = next(fact for fact in skills["required"] if fact.get("technologies"))
        self.assertEqual(
            technology_fact["technologies"],
            ["Python", "SQL", "Tableau", "Oracle"],
        )
        self.assertFalse(any("Build Python data pipelines" in fact["statement"] for fact in skills["required"]))

    def test_common_internship_stack_annotations_include_modern_web_and_cloud_tools(self):
        result = shared.extract_requirements([
            "What we're looking for:",
            "Academic or project experience with React, C#/.NET, PostgreSQL, Node.js, GCP, and Jenkins.",
        ])
        fact = result["skills"]["required"][0]
        self.assertEqual(
            fact["technologies"],
            ["C#", "React", "Node.js", ".NET", "PostgreSQL", "GCP", "Jenkins"],
        )

    def test_quantified_preference_remains_preferred(self):
        result = shared.extract_requirements([
            "Preferred but not required:",
            "At least one prior project using Linux and Git.",
        ])
        self.assertEqual(result["skills"]["classification"], "preferred")
        self.assertEqual(result["skills"]["required"], [])
        self.assertEqual(result["skills"]["preferred"][0]["technologies"], ["Git", "Linux"])

    def test_generic_what_you_bring_heading_is_required_context(self):
        result = shared.extract_requirements([
            "What you'll bring:",
            "Strong foundation in data structures and algorithms.",
            "What it takes to be successful:",
            "Experience with Python and C++.",
        ])
        skills = result["skills"]
        self.assertEqual(skills["classification"], "required")
        self.assertEqual(
            skills["required"][0]["technologies"],
            ["C++", "Python"],
        )

    def test_novel_heading_does_not_drop_candidate_skill_evidence(self):
        result = shared.extract_requirements([
            "What makes you successful here:",
            "Hands-on experience with Python, AWS, and Docker in academic or personal projects.",
        ])
        skills = result["skills"]
        self.assertEqual(skills["classification"], "unspecified")
        self.assertEqual(skills["required"], [])
        self.assertEqual(skills["preferred"], [])
        self.assertEqual(
            skills["unspecified"][0]["technologies"],
            ["Python", "AWS", "Docker"],
        )

    def test_unheaded_domain_experience_is_preserved_without_becoming_required(self):
        result = shared.extract_requirements([
            "Your superpowers:",
            "Previous experience in distributed systems and backend services.",
        ])
        skills = result["skills"]
        self.assertEqual(skills["classification"], "unspecified")
        self.assertEqual(skills["required"], [])
        self.assertIn("distributed systems", skills["unspecified"][0]["statement"].lower())

    def test_responsibility_language_does_not_become_unheaded_qualification(self):
        result = shared.extract_requirements([
            "A day in the life:",
            "Build Python services on AWS.",
            "Gain experience using Docker and Kubernetes.",
        ])
        self.assertEqual(result["skills"]["classification"], "unknown")
        self.assertEqual(result["skills"]["unspecified"], [])

    def test_extracts_authoritative_term_duration_and_date_range(self):
        schedule = shared.extract_posting_schedule([
            "Our site is seeking a Portfolio Analytics Analyst Co-Op for the Spring 2027 season.",
            "This assignment is intended to be 6 months in duration.",
            "Available to work 40 hours a week beginning in January through June.",
        ])
        self.assertEqual(schedule["status"], "authoritative")
        self.assertEqual(schedule["terms"], ["Spring 2027"])
        self.assertEqual(schedule["duration_evidence"], [
            "This assignment is intended to be 6 months in duration."
        ])
        self.assertEqual(schedule["date_range_evidence"], [
            "Available to work 40 hours a week beginning in January through June."
        ])

    def test_extracts_explicit_application_deadline_evidence(self):
        schedule = shared.extract_posting_schedule([
            "Application Deadline: August 14, 2026",
            "Applications will close on September 1st.",
            "Please apply by May 1.",
            "The deadline to apply is January 15, 2027.",
            "Submit by Nov 5, 2026.",
            "This position does not have a deadline."
        ])
        self.assertEqual(schedule["status"], "authoritative")
        self.assertEqual(schedule["application_deadline_evidence"], [
            "Application Deadline: August 14, 2026",
            "Applications will close on September 1st.",
            "Please apply by May 1.",
            "The deadline to apply is January 15, 2027.",
            "Submit by Nov 5, 2026."
        ])

    def test_normalization_preserves_stable_block_lines(self):
        text, lines = shared.normalize_description(
            "<h2>Required Qualifications</h2><p>C++ required.<br>Linux preferred.</p>"
        )
        self.assertEqual(lines, ["Required Qualifications", "C++ required.", "Linux preferred."])
        self.assertEqual(text, "Required Qualifications\nC++ required.\nLinux preferred.")


if __name__ == "__main__":
    unittest.main()
