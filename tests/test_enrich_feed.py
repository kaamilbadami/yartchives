import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "enrich_feed.py"
spec = importlib.util.spec_from_file_location("enrich_feed", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EnrichFeedTests(unittest.TestCase):
    def test_graduate_only_titles(self):
        cases = [
            "Data Scientist (Master's Degree) Internship",
            "Business Data Scientist Intern, PhD, Summer 2027",
            "Software Engineering Intern, MS, Summer 2027",
            "MBA Strategy Intern",
        ]
        for title in cases:
            with self.subTest(title=title):
                self.assertEqual(mod.classify_education(title), "graduate-only")

    def test_undergrad_titles(self):
        cases = [
            "Software Engineering Intern, BS, Summer 2027",
            "Security Engineering Intern, BS/MS, Summer 2027",
            "Undergraduate Finance Internship",
            "Bachelor's Data Analyst Intern",
        ]
        for title in cases:
            with self.subTest(title=title):
                self.assertEqual(mod.classify_education(title), "undergrad")

    def test_unspecified_title_is_not_claimed_undergrad(self):
        self.assertEqual(mod.classify_education("Software Engineer Intern"), "unspecified")

    def test_opportunity_types(self):
        self.assertEqual(mod.classify_opportunity_type("Software Engineer Intern"), "internship")
        self.assertEqual(mod.classify_opportunity_type("Embedded Software Engineering Co-op"), "co-op")
        self.assertEqual(mod.classify_opportunity_type("Policy Fellowship"), "fellowship")
        self.assertEqual(mod.classify_opportunity_type("Research Assistant Program"), "research")
        self.assertEqual(mod.classify_opportunity_type("Entry Level Analyst"), "other")


if __name__ == "__main__":
    unittest.main()
