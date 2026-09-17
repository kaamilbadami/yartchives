import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("discover_workday_sources", SCRIPT_DIR / "discover_workday_sources.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DiscoverWorkdaySourcesTests(unittest.TestCase):
    def test_discovers_cs_workday_sites_across_multiple_states(self):
        configured = [
            {
                "key": "ct-hartford-workday",
                "name": "The Hartford (direct)",
                "company": "The Hartford",
                "kind": "workday",
                "api_url": "https://thehartford.wd5.myworkdayjobs.com/wday/cxs/thehartford/Careers_External/jobs",
                "public_base": "https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External",
                "homepage": "https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External",
                "state": "CT",
                "profile_hint": ["cs"],
                "search_terms": ["intern"],
            }
        ]
        feed = {
            "jobs": [
                {
                    "company": "Castleton Commodities International",
                    "states": ["CT"],
                    "profiles": ["cs"],
                    "url": "https://osv-cci.wd1.myworkdayjobs.com/en-US/CCICareers/job/Stamford-CT/Software-Engineer-Intern_R1350",
                },
                {
                    "company": "Other Employer",
                    "states": ["NY"],
                    "profiles": ["cs"],
                    "url": "https://other.wd1.myworkdayjobs.com/en-US/Careers/job/New-York-NY/Software-Engineer-Intern_R2",
                },
                {
                    "company": "Multi State Employer",
                    "states": ["MD", "VA"],
                    "profiles": ["cs"],
                    "url": "https://multi.wd1.myworkdayjobs.com/en-US/External/job/Bethesda-MD/Software-Intern_R3",
                },
                {
                    "company": "Mechanical Employer",
                    "states": ["PA"],
                    "profiles": ["mechanical"],
                    "url": "https://mech.wd1.myworkdayjobs.com/en-US/Careers/job/Pittsburgh-PA/Mechanical-Intern_R4",
                },
            ]
        }

        sources = mod.discover_sources(feed, configured)
        auto = [source for source in sources if source.get("auto_discovered")]
        self.assertEqual(len(auto), 4)
        self.assertEqual({source["state"] for source in auto}, {"CT", "NY", "MD", "VA"})
        self.assertTrue(any(source["company"] == "Other Employer" and source["state"] == "NY" for source in auto))
        self.assertTrue(any(source["key"].startswith("md-auto-workday-") for source in auto))
        self.assertTrue(any(source["key"].startswith("va-auto-workday-") for source in auto))

    def test_configured_source_dedupes_same_site_and_state_only(self):
        configured = [{
            "key": "ct-example-workday",
            "name": "Example",
            "company": "Example",
            "kind": "workday",
            "api_url": "https://example.wd1.myworkdayjobs.com/wday/cxs/example/Careers/jobs",
            "public_base": "https://example.wd1.myworkdayjobs.com/en-US/Careers",
            "homepage": "https://example.wd1.myworkdayjobs.com/en-US/Careers",
            "state": "CT",
        }]
        feed = {"jobs": [
            {"company": "Example", "states": ["CT", "NY"], "profiles": ["cs"], "url": "https://example.wd1.myworkdayjobs.com/en-US/Careers/job/New-York-NY/Test_R1"}
        ]}
        sources = mod.discover_sources(feed, configured)
        self.assertEqual(len(sources), 2)
        self.assertEqual(sorted(source["state"] for source in sources), ["CT", "NY"])

    def test_ignores_non_workday_and_non_cs_jobs(self):
        feed = {"jobs": [
            {"company": "Example", "states": ["MD"], "profiles": ["cs"], "url": "https://jobs.example.com/intern/123"},
            {"company": "Example", "states": ["MD"], "profiles": ["mechanical"], "url": "https://example.wd1.myworkdayjobs.com/en-US/Careers/job/Baltimore-MD/Test_R1"},
        ]}
        self.assertEqual(mod.discover_sources(feed, []), [])


if __name__ == "__main__":
    unittest.main()
