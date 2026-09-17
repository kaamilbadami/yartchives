from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from posting_requirements import extract_requirements


class ExperienceYouBringRequirementTests(unittest.TestCase):
    def test_experience_youll_bring_is_required_qualification_context(self):
        lines = [
            "Experience you'll bring:",
            "Currently pursuing a Bachelor's degree in Computer Science, Machine Learning, Software Engineering, or a related field.",
            "Strong proficiency in Go (Golang) or general backend languages (Java, C, PHP) with solid software engineering fundamentals.",
            "Practical exposure to AWS cloud infrastructure and core cloud services.",
            "Experience with software testing best practices (unit testing, basic UI testing).",
        ]

        requirements = extract_requirements(lines)

        self.assertEqual(requirements["skills"]["classification"], "required")
        statements = requirements["skills"]["required"]
        self.assertEqual(len(statements), 3)
        technologies = {tech for item in statements for tech in item.get("technologies", [])}
        self.assertTrue({"Java", "C", "AWS"}.issubset(technologies))
        self.assertEqual(requirements["education"]["classification"], "required")
        self.assertEqual(requirements["major_fields"]["classification"], "required")


if __name__ == "__main__":
    unittest.main()
