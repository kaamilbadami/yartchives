import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("discover_ct_workday_sources", SCRIPT_DIR / "discover_ct_workday_sources.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DiscoverCtWorkdaySourcesTests(unittest.TestCase):
    def test_discovers_existing_ct_cs_workday_sites_without_employer_config(self):
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
                    "title": "Full-Stack Software Engineer Intern",
                    "location": "Stamford, CT",
                    "states": ["CT"],
                    "profiles": ["cs"],
                    "url": "https://osv-cci.wd1.myworkdayjobs.com/en-US/CCICareers/job/Stamford-CT/Full-Stack-Software-Engineer-Internship--Summer-2027-_R1350",
                },
                {
                    "company": "Castleton Commodities International",
                    "title": "Data Science Machine Learning Intern",
                    "location": "Stamford, CT",
                    "states": ["CT", "TX"],
                    "profiles": ["cs"],
                    "url": "https://osv-cci.wd1.myworkdayjobs.com/CCICareers/job/Stamford-CT/Data-Science-Machine-Learning-Internship--Summer-2027-_R1344",
                },
                {
                    "company": "The Hartford",
                    "title": "Software Engineer Intern",
                    "location": "Hartford, CT",
                    "states": ["CT"],
                    "profiles": ["cs"],
                    "url": "https://thehartford.wd5.myworkdayjobs.com/en-US/Careers_External/job/Hartford-CT/Software-Engineer-Intern_R1",
                },
                {
                    "company": "Other Employer",
                    "title": "Software Engineer Intern",
                    "location": "New York, NY",
                    "states": ["NY"],
                    "profiles": ["cs"],
                    "url": "https://other.wd1.myworkdayjobs.com/en-US/Careers/job/New-York-NY/Software-Engineer-Intern_R2",
                },
                {
                    "company": "Mechanical Employer",
                    "title": "Mechanical Engineering Intern",
                    "location": "Stamford, CT",
                    "states": ["CT"],
                    "profiles": ["mechanical"],
                    "url": "https://mech.wd1.myworkdayjobs.com/en-US/Careers/job/Stamford-CT/Mechanical-Intern_R3",
                },
            ]
        }

        sources = mod.discover_sources(feed, configured)
        self.assertEqual(len(sources), 2)
        auto = next(source for source in sources if source.get("auto_discovered"))
        self.assertEqual(auto["company"], "Castleton Commodities International")
        self.assertEqual(auto["api_url"], "https://osv-cci.wd1.myworkdayjobs.com/wday/cxs/osv-cci/CCICareers/jobs")
        self.assertEqual(auto["public_base"], "https://osv-cci.wd1.myworkdayjobs.com/en-US/CCICareers")
        self.assertEqual(auto["search_terms"], ["intern", "co-op", "student"])

    def test_source_from_job_ignores_non_workday_urls(self):
        job = {
            "company": "Example",
            "states": ["CT"],
            "profiles": ["cs"],
            "url": "https://jobs.example.com/intern/123",
        }
        self.assertIsNone(mod.source_from_job(job))


if __name__ == "__main__":
    unittest.main()
