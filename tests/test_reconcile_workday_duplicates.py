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
DOORDASH_URL = "https://job-boards.greenhouse.io/doordashusa/jobs/8171041"
ICIMS_URL = "https://careers-gdeb.icims.com/jobs/20341/job"
POINT72_URL = "https://careers.point72.com/CSJobDetail?jobName=quantitative-developer-intern&jobCode=CSS-0013064"


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


    def test_verified_workday_apply_survives_reconciliation(self):
        job_url = "https://globalhr.wd5.myworkdayjobs.com/rec_rtx_ext_gateway" + RTX_PATH
        employer_page = base_job(
            "employer-page",
            "RTX",
            job_url,
            direct=True,
            source="RTX direct",
            posted="2026-09-16T11:00:00Z",
        )
        employer_page["link_kind"] = "employer_job"

        verified_apply = base_job(
            "verified-apply",
            "RTX",
            job_url + "/apply",
            direct=True,
            source="Provider recovery",
            posted="2026-09-16T12:00:00Z",
        )
        verified_apply["link_status"] = "ok"
        verified_apply["link_checked_at"] = "2026-09-16T12:05:00Z"
        verified_apply["link_origin"] = "workday-employer-job"

        reconciled, stats = mod.reconcile_jobs([employer_page, verified_apply])

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(stats["duplicate_groups"], 1)
        job = reconciled[0]
        self.assertEqual(job["url"], job_url + "/apply")
        self.assertEqual(job["link_kind"], "direct")
        self.assertEqual(job["link_status"], "ok")
        self.assertEqual(job["link_checked_at"], "2026-09-16T12:05:00Z")

    def test_workday_job_page_is_not_left_labeled_direct(self):
        job_url = "https://globalhr.wd5.myworkdayjobs.com/rec_rtx_ext_gateway" + RTX_PATH
        mislabeled = base_job(
            "mislabeled-direct",
            "RTX",
            job_url,
            direct=True,
            source="Simplify",
            posted="2026-09-16T12:00:00Z",
        )
        duplicate = base_job(
            "employer-page",
            "RTX",
            job_url + "?source=other",
            source="Other",
            posted="2026-09-16T11:00:00Z",
        )
        duplicate["link_kind"] = "employer_job"

        reconciled, stats = mod.reconcile_jobs([mislabeled, duplicate])

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(stats["duplicate_groups"], 1)
        self.assertEqual(reconciled[0]["url"], job_url)
        self.assertEqual(reconciled[0]["link_kind"], "employer_job")


    def test_oracle_hcm_identity_key(self):
        url = "https://ehzq.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/115806"
        self.assertEqual(
            mod.posting_identity_key(url),
            ("oracle_hcm", "ehzq.fa.us2.oraclecloud.com", "115806"),
        )
        self.assertEqual(
            mod.canonical_posting_url(url),
            "https://ehzq.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/115806",
        )

    def test_greenhouse_identity_ignores_legacy_host_and_tracking(self):
        tracked = DOORDASH_URL + "?amp%3Bref=Simplify"
        legacy = "https://boards.greenhouse.io/doordashusa/jobs/8171041?gh_src=test"

        self.assertEqual(mod.greenhouse_canonical_url(tracked), DOORDASH_URL)
        self.assertEqual(mod.greenhouse_canonical_url(legacy), DOORDASH_URL)
        self.assertEqual(mod.posting_identity_key(tracked), mod.posting_identity_key(legacy))

    def test_greenhouse_company_name_variants_collapse_by_authoritative_posting_identity(self):
        older = base_job(
            "older-copy",
            "DoorDash USA",
            DOORDASH_URL,
            source="Zapply",
            posted="2026-09-14T00:00:00Z",
        )
        older["title"] = "Software Engineer, Intern (Summer 2027) - US"
        older["location"] = "New York City, NY"
        older["states"] = ["NY"]
        older["posted_raw"] = "2d"

        newer = base_job(
            "newer-copy",
            "DoorDash",
            DOORDASH_URL + "?amp%3Bref=Simplify",
            source="Simplify",
            posted="2026-09-15T00:00:00Z",
        )
        newer["title"] = "Software Engineer, Intern (Summer 2027) - US"
        newer["location"] = "New York, NY"
        newer["states"] = ["NY"]
        newer["posted_raw"] = "1d"

        reconciled, stats = mod.reconcile_jobs([older, newer])

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(stats["greenhouse_postings"], 1)
        self.assertEqual(stats["duplicate_groups"], 1)
        self.assertEqual(stats["records_removed"], 1)
        job = reconciled[0]
        self.assertEqual(job["company"], "DoorDash")
        self.assertEqual(job["id"], "newer-copy")
        self.assertEqual(job["url"], DOORDASH_URL)
        self.assertEqual(job["posted_at"], "2026-09-15T00:00:00Z")
        self.assertEqual(job["posted_raw"], "1d")
        self.assertEqual(set(job["source_names"]), {"Simplify", "Zapply"})

    def test_icims_job_and_login_variants_share_identity(self):
        job_url = ICIMS_URL + "?mobile=true&amp%3BneedsRedirect=false"
        login_url = "https://careers-gdeb.icims.com/jobs/20341/login?mobile=true"

        self.assertEqual(mod.icims_canonical_url(job_url), ICIMS_URL)
        self.assertEqual(mod.icims_canonical_url(login_url), ICIMS_URL)
        self.assertEqual(mod.posting_identity_key(job_url), mod.posting_identity_key(login_url))

    def test_exact_unsupported_direct_copies_collapse_after_link_recovery(self):
        first = base_job("point72-one", "Point72", POINT72_URL, source="Simplify", posted="2026-09-16T11:00:00Z")
        second = base_job(
            "point72-two",
            "Point72",
            POINT72_URL + "&utm_source=another-feed",
            source="SpeedyApply",
            posted="2026-09-16T12:00:00Z",
        )
        for job in (first, second):
            job["title"] = "Quantitative Developer Intern"
            job["location"] = "New York, NY"
            job["states"] = ["NY"]

        reconciled, stats = mod.reconcile_jobs([first, second])

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(stats["direct_url_postings"], 1)
        self.assertEqual(stats["duplicate_groups"], 1)
        self.assertEqual(stats["records_removed"], 1)
        self.assertEqual(set(reconciled[0]["source_names"]), {"Simplify", "SpeedyApply"})

    def test_shared_unsupported_direct_url_does_not_merge_distinct_roles(self):
        first = base_job("one", "Example", "https://careers.example.com/apply", source="Simplify")
        second = base_job("two", "Example", "https://careers.example.com/apply", source="SpeedyApply")
        first["title"] = "Software Engineering Intern"
        second["title"] = "Data Engineering Intern"

        reconciled, stats = mod.reconcile_jobs([first, second])

        self.assertEqual(len(reconciled), 2)
        self.assertEqual(stats["duplicate_groups"], 0)
        self.assertEqual(stats["records_removed"], 0)

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

    def test_non_supported_ats_record_is_preserved(self):
        job = {
            "id": "lever",
            "company": "Example",
            "title": "Software Intern",
            "location": "New York, NY",
            "url": "https://jobs.lever.co/example/123",
            "posted_at": "2026-09-16T12:00:00Z",
        }
        reconciled, stats = mod.reconcile_jobs([job])
        self.assertEqual(reconciled, [job])
        self.assertEqual(stats["ats_postings"], 0)
        self.assertEqual(stats["workday_postings"], 0)
        self.assertEqual(stats["greenhouse_postings"], 0)
        self.assertEqual(stats["icims_postings"], 0)
        self.assertEqual(stats["direct_url_postings"], 0)


if __name__ == "__main__":
    unittest.main()
