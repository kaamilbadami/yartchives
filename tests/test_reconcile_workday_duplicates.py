import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "reconcile_workday_duplicates.py"
spec = importlib.util.spec_from_file_location("reconcile_workday_duplicates", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


RTX_PATH = (
    "/job/US-CT-WINDSOR-LOCKS-B1--1-Hamilton-Rd--BLDG-1/"
    "Software-Engineering-Intern--Summer-2027-_01872775"
)
CACI_PATH = (
    "/job/Colorado-Springs-CO-US/"
    "Software-Test-Engineer-Intern---Summer-2027_332003"
)


def base_job(job_id, company, url, *, direct=False, source="Simplify", posted="2026-09-16T12:00:00Z"):
    job = {
        "id": job_id,
        "company": company,
        "title": "Software Engineering Intern (Summer 2027)",
        "location": "Windsor Locks, CT",
        "url": url,
        "posted_raw": "Today",
        "posted_at": posted,
        "states": ["CT"],
        "term": "Summer 2027",
        "profiles": ["cs"],
        "source_keys": [source.lower().replace(" ", "-")],
        "source_names": [source],
        "source_urls": ["https://example.test/source"],
        "first_seen": "2026-09-16T10:00:00Z",
        "last_seen": "2026-09-16T12:00:00Z",
        "link_kind": "direct",
    }
    if direct:
        job["direct_employer"] = True
    return job


class ReconcileWorkdayDuplicateTests(unittest.TestCase):
    def test_workday_identity_ignores_locale_and_tracking_query(self):
        with_locale = "https://globalhr.wd5.myworkdayjobs.com/en-US/rec_rtx_ext_gateway" + RTX_PATH
        tracked = (
            "https://globalhr.wd5.myworkdayjobs.com/rec_rtx_ext_gateway"
            + RTX_PATH
            + "?amp%3Bref=Simplify"
        )
        self.assertEqual(mod.workday_canonical_url(with_locale), mod.workday_canonical_url(tracked))
        self.assertEqual(mod.workday_identity_key(with_locale), mod.workday_identity_key(tracked))
        self.assertEqual(
            mod.workday_canonical_url(with_locale),
            "https://globalhr.wd5.myworkdayjobs.com/rec_rtx_ext_gateway" + RTX_PATH,
        )

    def test_workday_identity_treats_career_site_casing_as_cosmetic(self):
        lower = "https://caci.wd1.myworkdayjobs.com/external" + CACI_PATH
        upper = "https://caci.wd1.myworkdayjobs.com/en-US/External" + CACI_PATH

        self.assertNotEqual(mod.workday_canonical_url(lower), mod.workday_canonical_url(upper))
        self.assertEqual(mod.workday_identity_key(lower), mod.workday_identity_key(upper))

    def test_site_case_variants_collapse_to_one_posting_and_keep_winner_url(self):
        lower = base_job(
            "aggregator-copy",
            "CACI",
            "https://caci.wd1.myworkdayjobs.com/external" + CACI_PATH,
            source="Simplify",
            posted="2026-09-16T11:00:00Z",
        )
        lower["title"] = "Software Test Engineer Intern - Summer 2027"
        lower["location"] = "Colorado Springs, CO"
        lower["states"] = ["CO"]

        upper = base_job(
            "direct-copy",
            "CACI",
            "https://caci.wd1.myworkdayjobs.com/en-US/External" + CACI_PATH,
            direct=True,
            source="CACI direct",
            posted="2026-09-16T12:00:00Z",
        )
        upper["title"] = "Software Test Engineer Intern - Summer 2027"
        upper["location"] = "Colorado Springs, CO, US"
        upper["states"] = ["CO"]

        reconciled, stats = mod.reconcile_jobs([lower, upper])

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(stats["duplicate_groups"], 1)
        self.assertEqual(stats["records_removed"], 1)
        job = reconciled[0]
        self.assertEqual(job["id"], "direct-copy")
        self.assertEqual(
            job["url"],
            "https://caci.wd1.myworkdayjobs.com/External" + CACI_PATH,
        )
        self.assertEqual(set(job["source_names"]), {"Simplify", "CACI direct"})

    def test_duplicate_group_prefers_direct_employer_company_and_unions_sources(self):
        aggregator = base_job(
            "aggregator-id",
            "Wrong Employer",
            "https://globalhr.wd5.myworkdayjobs.com/rec_rtx_ext_gateway"
            + RTX_PATH
            + "?amp%3Bref=Simplify",
            source="Simplify",
            posted="2026-09-16T11:00:00Z",
        )
        direct = base_job(
            "direct-id",
            "RTX",
            "https://globalhr.wd5.myworkdayjobs.com/en-US/rec_rtx_ext_gateway" + RTX_PATH,
            direct=True,
            source="RTX direct",
            posted="2026-09-16T12:00:00Z",
        )
        direct["location"] = "US-CT-WINDSOR LOCKS-B1 ~ 1 Hamilton Rd ~ BLDG 1"

        reconciled, stats = mod.reconcile_jobs([aggregator, direct])

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(stats["duplicate_groups"], 1)
        self.assertEqual(stats["records_removed"], 1)
        job = reconciled[0]
        self.assertEqual(job["company"], "RTX")
        self.assertEqual(job["id"], "direct-id")
        self.assertTrue(job["direct_employer"])
        self.assertEqual(
            job["url"],
            "https://globalhr.wd5.myworkdayjobs.com/rec_rtx_ext_gateway" + RTX_PATH,
        )
        self.assertEqual(set(job["source_names"]), {"Simplify", "RTX direct"})
        self.assertEqual(job["location"], "US-CT-WINDSOR LOCKS-B1 ~ 1 Hamilton Rd ~ BLDG 1")

    def test_distinct_workday_postings_do_not_merge(self):
        first = base_job(
            "one",
            "RTX",
            "https://globalhr.wd5.myworkdayjobs.com/rec_rtx_ext_gateway" + RTX_PATH,
        )
        second = base_job(
            "two",
            "RTX",
            "https://globalhr.wd5.myworkdayjobs.com/rec_rtx_ext_gateway/job/US-CT-WINDSOR-LOCKS/Another-Intern_99999999",
        )
        reconciled, stats = mod.reconcile_jobs([first, second])
        self.assertEqual(len(reconciled), 2)
        self.assertEqual(stats["duplicate_groups"], 0)
        self.assertEqual(stats["records_removed"], 0)

    def test_non_workday_record_is_preserved(self):
        job = {
            "id": "greenhouse",
            "company": "Example",
            "title": "Software Intern",
            "location": "New York, NY",
            "url": "https://boards.greenhouse.io/example/jobs/123",
            "posted_at": "2026-09-16T12:00:00Z",
        }
        reconciled, stats = mod.reconcile_jobs([job])
        self.assertEqual(reconciled, [job])
        self.assertEqual(stats["workday_postings"], 0)


if __name__ == "__main__":
    unittest.main()
