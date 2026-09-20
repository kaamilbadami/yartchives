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
        self.assertEqual(len(auto), 3)
        self.assertTrue(all(source.get("scope") == "us" for source in auto))
        self.assertTrue(any(source["company"] == "Other Employer" for source in auto))
        multi = [source for source in auto if source["company"] == "Multi State Employer"]
        self.assertEqual(len(multi), 1)
        self.assertTrue(multi[0]["key"].startswith("us-feed-workday-"))

    def test_feed_evidence_collapses_same_site_across_states_to_one_national_source(self):
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
        self.assertEqual(sum(source.get("state") == "CT" for source in sources), 1)
        national = [source for source in sources if source.get("scope") == "us"]
        self.assertEqual(len(national), 1)
        self.assertNotIn("state", national[0])

    def test_same_feed_workday_site_is_only_discovered_once_across_many_states(self):
        feed = {"jobs": [
            {
                "company": "Example",
                "states": ["CA"],
                "profiles": ["cs"],
                "url": "https://example.wd1.myworkdayjobs.com/en-US/Careers/job/California/Software-Intern_R1",
            },
            {
                "company": "Example",
                "states": ["NY"],
                "profiles": ["cs"],
                "url": "https://example.wd1.myworkdayjobs.com/en-US/Careers/job/New-York/Software-Intern_R2",
            },
            {
                "company": "Example",
                "states": ["TX"],
                "profiles": ["cs"],
                "url": "https://example.wd1.myworkdayjobs.com/en-US/Careers/job/Texas/Software-Intern_R3",
            },
        ]}

        sources = mod.discover_sources(feed, [])
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["scope"], "us")
        self.assertEqual(
            sources[0]["api_url"],
            "https://example.wd1.myworkdayjobs.com/wday/cxs/example/Careers/jobs",
        )

    def test_resolved_universe_workday_site_becomes_national_source(self):
        universe = {
            "employers": [{
                "id": "amgen",
                "name": "Amgen",
                "careers_url": "https://amgen.wd1.myworkdayjobs.com/careers",
                "provider": {"status": "resolved", "family": "workday"},
                "careers_resolution": {"status": "resolved"},
            }]
        }
        sources = mod.discover_sources({"jobs": []}, [], universe)
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source["scope"], "us")
        self.assertEqual(source["company"], "Amgen")
        self.assertEqual(
            source["api_url"],
            "https://amgen.wd1.myworkdayjobs.com/wday/cxs/amgen/careers/jobs",
        )
        self.assertEqual(source["public_base"], "https://amgen.wd1.myworkdayjobs.com/en-US/careers")

    def test_national_universe_site_suppresses_feed_state_duplicate(self):
        universe = {
            "employers": [{
                "id": "example",
                "name": "Example",
                "careers_url": "https://example.wd1.myworkdayjobs.com/en-US/Careers",
                "provider": {"status": "resolved", "family": "workday"},
                "careers_resolution": {"status": "resolved"},
            }]
        }
        feed = {"jobs": [{
            "company": "Example",
            "states": ["MD"],
            "profiles": ["cs"],
            "url": "https://example.wd1.myworkdayjobs.com/en-US/Careers/job/Bethesda-MD/Software-Intern_R1",
        }]}
        sources = mod.discover_sources(feed, [], universe)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["scope"], "us")
        self.assertNotIn("state", sources[0])


    def test_quarantined_feed_source_is_not_rediscovered(self):
        job = {
            "company": "Example",
            "states": ["CT"],
            "profiles": ["cs"],
            "url": "https://example.wd1.myworkdayjobs.com/en-US/Careers/job/Connecticut/Software-Intern_R1",
        }
        source = mod.source_from_job_national(job)
        feed = {
            "jobs": [job],
            "sources": {
                source["key"]: {
                    "status": "quarantined",
                    "quarantined": True,
                    "error": "StructuralSourceError: HTTP 422",
                }
            },
        }
        self.assertEqual(mod.discover_sources(feed, []), [])


    def test_ignores_non_workday_and_non_cs_jobs(self):
        feed = {"jobs": [
            {"company": "Example", "states": ["MD"], "profiles": ["cs"], "url": "https://jobs.example.com/intern/123"},
            {"company": "Example", "states": ["MD"], "profiles": ["mechanical"], "url": "https://example.wd1.myworkdayjobs.com/en-US/Careers/job/Baltimore-MD/Test_R1"},
        ]}
        self.assertEqual(mod.discover_sources(feed, []), [])


if __name__ == "__main__":
    unittest.main()
