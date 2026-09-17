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

    def test_source_formatting_is_removed_from_display(self):
        self.assertEqual(mod.clean_display_text("**Avis Budget Group**"), "Avis Budget Group")
        self.assertEqual(mod.clean_display_text("🔥 Intel"), "Intel")
        self.assertEqual(
            mod.extract_source_markers("🔥 Intel", "Silicon Hardware Intern 🎓"),
            ["advanced_degree", "source_featured"],
        )

    def test_hardware_section_alone_does_not_make_role_electrical(self):
        job = {
            "title": "Program Management Intern",
            "section": "Hardware Engineering",
            "function_primary": "",
            "source_keys": ["simplify"],
        }
        self.assertNotIn("electrical", mod.classify_profiles(job))

    def test_actual_electrical_and_hardware_roles_are_electrical(self):
        for title in (
            "Electrical Engineering Intern",
            "Hardware Engineering Co-Op",
            "FPGA Design Intern",
        ):
            with self.subTest(title=title):
                self.assertIn("electrical", mod.classify_profiles({"title": title}))

    def test_embedded_software_can_be_both_cs_and_electrical(self):
        profiles = mod.classify_profiles({"title": "Embedded Software Engineering Co-op"})
        self.assertIn("cs", profiles)
        self.assertIn("electrical", profiles)

    def test_generic_software_test_role_is_not_mechanical(self):
        profiles = mod.classify_profiles({"title": "Software Test Engineering Intern"})
        self.assertIn("cs", profiles)
        self.assertNotIn("mechanical", profiles)

    def test_mechanical_test_role_is_mechanical(self):
        profiles = mod.classify_profiles({"title": "Mechanical Test Engineering Intern"})
        self.assertIn("mechanical", profiles)

    def test_public_sector_source_does_not_force_policy(self):
        profiles = mod.classify_profiles({
            "title": "Software Engineering Intern",
            "source_keys": ["public-sector"],
        })
        self.assertIn("cs", profiles)
        self.assertNotIn("policy", profiles)

    def test_narrow_sections_can_supply_unambiguous_context(self):
        self.assertIn("finance-econ", mod.classify_profiles({
            "title": "Summer Analyst",
            "section": "Quantitative Finance",
        }))
        self.assertIn("tech-business", mod.classify_profiles({
            "title": "Summer Intern",
            "section": "Product Management",
        }))

    def test_direct_ct_source_retains_cs_after_strict_adapter(self):
        profiles = mod.classify_profiles({
            "title": "Digital Technology Intern",
            "source_keys": ["ct-avangrid-workday"],
        })
        self.assertIn("cs", profiles)

    def test_auto_greenhouse_source_retains_cs_after_strict_adapter(self):
        for title in (
            "IT Operations Co-Op",
            "Winter 2027 Test Automation Engineer Co-op",
        ):
            with self.subTest(title=title):
                profiles = mod.classify_profiles({
                    "title": title,
                    "source_keys": ["auto-greenhouse-example"],
                })
                self.assertIn("cs", profiles)

    def test_broad_source_profile_tags_are_still_recomputed(self):
        profiles = mod.classify_profiles({
            "title": "Marketing Intern",
            "profiles": ["cs"],
            "source_keys": ["simplify"],
        })
        self.assertEqual(profiles, ["general"])

    def test_enrichment_cleans_display_and_uses_degree_marker(self):
        doc = {
            "jobs": [{
                "company": "🔥 **Intel**",
                "title": "Silicon Hardware Engineering Intern - Graduate 🎓",
                "profiles": ["electrical", "mechanical"],
                "source_keys": ["simplify"],
            }]
        }
        self.assertTrue(mod.enrich_document(doc))
        job = doc["jobs"][0]
        self.assertEqual(job["company"], "Intel")
        self.assertEqual(job["title"], "Silicon Hardware Engineering Intern - Graduate")
        self.assertEqual(job["education_level"], "graduate-only")
        self.assertEqual(job["profiles"], ["electrical"])
        self.assertEqual(job["source_markers"], ["advanced_degree", "source_featured"])


if __name__ == "__main__":
    unittest.main()
