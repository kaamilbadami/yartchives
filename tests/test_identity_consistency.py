import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reconcile = load_module("reconcile_workday_duplicates")
repair = load_module("repair_links")


class IdentityConsistencyTests(unittest.TestCase):
    def test_workday_identity_collapses_location_aliases_for_same_requisition(self):
        sterling = (
            "https://caci.wd1.myworkdayjobs.com/external/job/437-DENVER-CO/"
            "Cleared-Software-Engineer-Intern---Summer-2027_331999"
        )
        denver = (
            "https://caci.wd1.myworkdayjobs.com/External/job/Denver-CO-US/"
            "Cleared-Software-Engineer-Intern---Summer-2027_331999"
        )

        self.assertEqual(reconcile.workday_requisition_token("/job/x/role_331999"), "331999")
        self.assertEqual(reconcile.workday_identity_key(sterling), reconcile.workday_identity_key(denver))

        jobs = [
            {
                "id": "aggregator-copy",
                "company": "CACI",
                "title": "Cleared Software Engineer Intern - Summer 2027",
                "location": "Remote - Sterling, VA",
                "url": sterling,
                "link_kind": "direct",
                "source_keys": ["applyguy"],
                "source_names": ["ApplyGuy"],
                "source_urls": ["https://example.test/applyguy"],
                "profiles": ["cs"],
                "states": ["Remote", "VA"],
                "posted_at": "2026-09-15T00:00:00Z",
            },
            {
                "id": "direct-copy",
                "company": "CACI",
                "title": "Cleared Software Engineer Intern - Summer 2027",
                "location": "Denver, CO, US",
                "url": denver,
                "link_kind": "direct",
                "direct_employer": True,
                "source_keys": ["caci-direct"],
                "source_names": ["CACI direct"],
                "source_urls": ["https://example.test/caci"],
                "profiles": ["cs"],
                "states": ["CO"],
                "posted_at": "2026-09-16T00:00:00Z",
            },
        ]

        merged, stats = reconcile.reconcile_jobs(jobs)
        self.assertEqual(len(merged), 1)
        self.assertEqual(stats["duplicate_groups"], 1)
        self.assertEqual(stats["records_removed"], 1)
        self.assertEqual(merged[0]["id"], "direct-copy")
        self.assertEqual(merged[0]["location"], "Denver, CO, US")
        self.assertEqual(set(merged[0]["source_names"]), {"ApplyGuy", "CACI direct"})

    def test_workday_identity_treats_title_slug_as_non_authoritative(self):
        backend_slug = (
            "https://wexinc.wd5.myworkdayjobs.com/WEXInc/job/US---Remote/"
            "Backend-Software-Engineer-Intern--Undergraduate-_R22593"
        )
        fullstack_slug = (
            "https://wexinc.wd5.myworkdayjobs.com/WEXInc/job/US---Remote/"
            "Fullstack-Software-Engineer-Intern--Undergraduate-_R22593"
        )

        self.assertEqual(reconcile.workday_requisition_token("/job/x/role_R22593"), "r22593")
        self.assertEqual(reconcile.workday_identity_key(backend_slug), reconcile.workday_identity_key(fullstack_slug))

    def test_applyguy_company_title_match_must_be_unique(self):
        payload = {
            "jobs": [
                {
                    "company": "CACI",
                    "title": "Cleared Software Engineer Intern - Summer 2027",
                    "location": "Sterling, VA",
                    "listingUrl": "https://caci.wd1.myworkdayjobs.com/external/job/Sterling-VA/Role_331998",
                },
                {
                    "company": "CACI",
                    "title": "Cleared Software Engineer Intern - Summer 2027",
                    "location": "Denver, CO",
                    "listingUrl": "https://caci.wd1.myworkdayjobs.com/external/job/Denver-CO/Role_331999",
                },
            ]
        }
        exact, by_title = repair.applyguy_indexes(payload)
        job = {
            "company": "CACI",
            "title": "Cleared Software Engineer Intern - Summer 2027",
            "location": "Remote - Sterling, VA",
        }

        self.assertNotIn(repair.company_title_key(job), exact)
        self.assertIsNone(repair.choose_applyguy_direct(job, exact, by_title))

    def test_applyguy_duplicate_rows_for_same_url_remain_safe(self):
        direct = "https://example.wd1.myworkdayjobs.com/external/job/Remote/Role_123456"
        payload = {
            "jobs": [
                {"company": "Example", "title": "Software Intern", "listingUrl": direct},
                {"company": "Example", "title": "Software Intern", "listingUrl": direct},
            ]
        }
        exact, by_title = repair.applyguy_indexes(payload)
        job = {"company": "Example", "title": "Software Intern", "location": "Remote"}

        self.assertEqual(repair.choose_applyguy_direct(job, exact, by_title), direct)


    def test_workday_identity_preserves_stable_id_when_title_and_slug_change(self):
        old_job_1 = {
            "source_key": "x", "source_name": "x", "source_url": "x",
            "company": "Company A",
            "title": "Software Engineer",
            "location": "Sterling, VA",
            "url": "https://caci.wd1.myworkdayjobs.com/external/job/437-DENVER-CO/Role_331999",
        }
        old_job_2 = {
            "source_key": "y", "source_name": "y", "source_url": "y",
            "company": "Company A",
            "title": "Software Eng", # Title changes to lose the tie-breaker
            "location": "Denver, CO",
            "url": "https://caci.wd1.myworkdayjobs.com/External/job/Denver-CO-US/Updated-Role_331999",
        }

        import build_feed as bf
        import stabilize_job_ids as st
        import datetime
        import copy

        # Day 1 Feed: Both jobs present
        old_dict = {}
        ref1 = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
        merged1 = bf.dedupe(copy.deepcopy([old_job_1, old_job_2]), old_dict, ref1)
        reconciled1, _ = reconcile.reconcile_jobs(merged1)
        feed1, _ = st.stabilize_jobs(reconciled1, [])
        self.assertEqual(len(feed1), 1)
        persisted_id = feed1[0]["id"]

        # Day 2 Feed: Both jobs present, but metadata changed to swap their string tie-breaker precedence
        new_job_1 = {
            "source_key": "x", "source_name": "x", "source_url": "x",
            "company": "Company A",
            "title": "Software Engineer Intern", # Metadata change
            "location": "Sterling, VA",
            "url": "https://caci.wd1.myworkdayjobs.com/external/job/437-DENVER-CO/Role_331999",
        }
        new_job_2 = {
            "source_key": "y", "source_name": "y", "source_url": "y",
            "company": "Company A",
            "title": "Software Eng Intern", # Metadata change
            "location": "Denver, CO",
            "url": "https://caci.wd1.myworkdayjobs.com/External/job/Denver-CO-US/Updated-Role_331999",
        }

        old_dict_2 = {j["id"]: j for j in feed1}
        ref2 = datetime.datetime(2026, 9, 2, tzinfo=datetime.timezone.utc)
        merged2 = bf.dedupe(copy.deepcopy([new_job_1, new_job_2]), old_dict_2, ref2)
        reconciled2, _ = reconcile.reconcile_jobs(merged2)
        feed2, _ = st.stabilize_jobs(reconciled2, feed1)
        self.assertEqual(len(feed2), 1)

        # ID must survive!
        self.assertEqual(feed2[0]["id"], persisted_id)


if __name__ == "__main__":
    unittest.main()
