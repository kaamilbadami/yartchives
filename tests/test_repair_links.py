import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repair_links.py"
spec = importlib.util.spec_from_file_location("repair_links", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VALIDATE_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_feed.py"
validate_spec = importlib.util.spec_from_file_location("validate_feed", VALIDATE_MODULE_PATH)
validate_mod = importlib.util.module_from_spec(validate_spec)
validate_spec.loader.exec_module(validate_mod)


class RepairLinksTests(unittest.TestCase):
    def test_applyguy_workday_job_page_becomes_employer_job(self):
        doc = {
            "jobs": [{
                "id": "1",
                "company": "Analog Devices",
                "title": "Embedded Software Engineer Intern",
                "location": "Boston, MA",
                "source_keys": ["applyguy"],
                "url": "",
            }]
        }
        payload = {
            "jobs": [{
                "company": "Analogdevices",
                "title": "Embedded Software Engineer Intern",
                "listingUrl": "https://analogdevices.wd1.myworkdayjobs.com/external/job/x/R266132",
            }]
        }
        stats = mod.repair_document(doc, payload)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "employer_job")

    def test_applyguy_workday_details_page_becomes_employer_job(self):
        doc = {
            "jobs": [{
                "id": "2",
                "company": "Boeing",
                "title": "Software Engineer",
                "location": "Seattle, WA",
                "source_keys": ["applyguy"],
                "url": "",
            }]
        }
        payload = {
            "jobs": [{
                "company": "Boeing",
                "title": "Software Engineer",
                "listingUrl": "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS/details/Software-Engineer_00000000",
            }]
        }
        stats = mod.repair_document(doc, payload)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "employer_job")
        self.assertEqual(job["link_origin"], "applyguy-feed")
        self.assertIn("myworkdayjobs.com", job["url"])
        self.assertEqual(stats["applyguy_repaired"], 1)

    def test_zapply_workday_job_page_becomes_employer_job_and_keeps_provenance(self):
        listing = "https://zapply.jobs/l/d/workday-caci-external-331393?s=gh-internships-2027"
        direct = "https://caci.wd1.myworkdayjobs.com/external/job/Danbury-CT/Embedded-Software_331393"
        doc = {
            "jobs": [{
                "id": "2",
                "company": "CACI",
                "title": "Embedded Software Engineering Co-op",
                "location": "Danbury, CT, US",
                "source_keys": ["zapply"],
                "url": listing,
            }]
        }
        mod.repair_document(doc, resolved_urls={mod.listing_cache_key(listing): direct})
        job = doc["jobs"][0]
        self.assertEqual(job["url"], direct)
        self.assertEqual(job["link_kind"], "employer_job")
        self.assertEqual(job["link_origin"], "redirect-resolved")
        self.assertEqual(job["resolved_from_url"], listing)
        self.assertNotIn("listing_url", job)

    def test_unresolved_zapply_stays_listing(self):
        listing = "https://zapply.jobs/l/d/workday-caci-external-331393"
        doc = {
            "jobs": [{
                "id": "3",
                "company": "CACI",
                "title": "Embedded Software Engineering Co-op",
                "location": "Danbury, CT, US",
                "source_keys": ["zapply"],
                "url": listing,
            }]
        }
        mod.repair_document(doc)
        job = doc["jobs"][0]
        self.assertEqual(job["url"], "")
        self.assertEqual(job["link_kind"], "listing")
        self.assertEqual(job["listing_url"], listing)

    def test_source_feed_can_repair_github_only_record(self):
        doc = {
            "jobs": [{
                "id": "4",
                "company": "Microsoft",
                "title": "Software Engineering Intern",
                "location": "Washington, DC",
                "source_keys": ["speedyapply"],
                "url": "https://github.com/speedyapply/2027-SWE-College-Jobs",
            }]
        }
        parsed = [{
            "company": "Microsoft",
            "title": "Software Engineering Intern",
            "location": "Washington, DC",
            "url": "https://apply.careers.microsoft.com/careers/job/123",
        }]
        exact, company_title = mod.source_direct_indexes(parsed)
        stats = mod.repair_document(doc, source_exact=exact, source_company_title=company_title)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "direct")
        self.assertEqual(job["link_origin"], "source-feed")
        self.assertIn("apply.careers.microsoft.com", job["url"])
        self.assertEqual(stats["source_repaired"], 1)

    def test_direct_employer_url_stays_direct(self):
        doc = {
            "jobs": [{
                "id": "5",
                "company": "Example",
                "title": "Software Engineering Intern",
                "location": "New York, NY",
                "source_keys": ["dreamwork-tech"],
                "url": "https://example.com/careers/jobs/123",
            }]
        }
        mod.repair_document(doc)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "direct")
        self.assertEqual(job["url"], "https://example.com/careers/jobs/123")

    def test_github_source_without_recovery_is_source_only(self):
        doc = {
            "jobs": [{
                "id": "6",
                "company": "Example",
                "title": "Software Engineering Intern",
                "location": "Remote",
                "source_keys": ["applyguy"],
                "url": "https://github.com/ApplyGuy/2027-Internships",
            }]
        }
        mod.repair_document(doc)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "source")
        self.assertEqual(job["url"], "")
        self.assertNotIn("listing_url", job)

    def test_dead_resolved_link_falls_back_to_listing(self):
        job = {
            "id": "7",
            "url": "https://employer.example/jobs/123",
            "link_kind": "direct",
            "resolved_from_url": "https://zapply.jobs/l/d/workday-example-careers-123",
        }
        mod.downgrade_dead_link(job)
        self.assertEqual(job["url"], "")
        self.assertEqual(job["link_kind"], "listing")
        self.assertEqual(job["listing_url"], "https://zapply.jobs/l/d/workday-example-careers-123")
        self.assertEqual(job["dead_url"], "https://employer.example/jobs/123")

    def test_zapply_greenhouse_slug_can_be_inferred(self):
        inferred = mod.candidate_from_zapply_slug(
            "https://zapply.jobs/l/d/greenhouse-singlestore-8205514?s=gh-internships-2027"
        )
        self.assertEqual(inferred, "https://job-boards.greenhouse.io/singlestore/jobs/8205514")

    def test_all_direct_cs_internships_are_eligible_for_validation(self):
        job = {
            "url": "https://employer.example/jobs/cs-intern",
            "link_kind": "direct",
            "opportunity_type": "internship",
            "profiles": ["cs"],
        }
        self.assertTrue(mod.should_validate_direct_link(job))

    def test_unrecovered_non_cs_link_is_not_added_to_validation_queue(self):
        job = {
            "url": "https://employer.example/jobs/finance-intern",
            "link_kind": "direct",
            "opportunity_type": "internship",
            "profiles": ["finance-econ"],
        }
        self.assertFalse(mod.should_validate_direct_link(job))

    def test_validation_checks_cs_link_without_a_recovery_origin(self):
        job = {
            "id": "cs-1",
            "url": "https://employer.example/jobs/cs-intern",
            "link_kind": "direct",
            "opportunity_type": "internship",
            "profiles": ["cs"],
        }
        checked_at = datetime(2026, 9, 17, tzinfo=timezone.utc)
        with (
            patch.object(mod, "now_utc", return_value=checked_at),
            patch.object(mod, "validate_direct_url", return_value=("ok", job["url"])) as validate,
        ):
            stats = mod.validate_repaired_links({"jobs": [job]}, {"jobs": []})

        validate.assert_called_once_with(job["url"])
        self.assertEqual(stats, {"checked": 1, "ok": 1, "dead": 0, "unknown": 0})
        self.assertEqual(job["link_status"], "ok")
        self.assertEqual(job["link_checked_at"], "2026-09-17T00:00:00Z")

    def test_old_validation_cache_version_does_not_skip_revalidation(self):
        url = "https://amgen.wd1.myworkdayjobs.com/Careers/job/Remote/old_R-255719"
        job = {
            "id": "amgen-1",
            "url": url,
            "link_kind": "direct",
            "opportunity_type": "internship",
            "profiles": ["cs"],
        }
        old = {
            "jobs": [{
                **job,
                "link_status": "ok",
                "link_checked_at": "2026-09-17T12:00:00Z",
                # No link_validation_version: this represents a legacy cached check.
            }]
        }
        checked_at = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)
        with (
            patch.object(mod, "now_utc", return_value=checked_at),
            patch.object(mod, "validate_direct_url", return_value=("dead", url)) as validate,
        ):
            stats = mod.validate_repaired_links({"jobs": [job]}, old)

        validate.assert_called_once_with(url)
        self.assertEqual(stats["checked"], 1)
        self.assertEqual(stats["dead"], 1)
        self.assertEqual(job["link_validation_version"], mod.LINK_VALIDATION_VERSION)

    def test_current_validation_cache_version_is_reused_within_ttl(self):
        url = "https://example.wd1.myworkdayjobs.com/Careers/job/Remote/live_R-123"
        job = {
            "id": "example-1",
            "url": url,
            "link_kind": "direct",
            "opportunity_type": "internship",
            "profiles": ["cs"],
        }
        old = {
            "jobs": [{
                **job,
                "link_status": "ok",
                "link_checked_at": "2026-09-17T12:00:00Z",
                "link_validation_version": mod.LINK_VALIDATION_VERSION,
            }]
        }
        checked_at = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)
        with (
            patch.object(mod, "now_utc", return_value=checked_at),
            patch.object(mod, "validate_direct_url") as validate,
        ):
            stats = mod.validate_repaired_links({"jobs": [job]}, old)

        validate.assert_not_called()
        self.assertEqual(stats["checked"], 0)
        self.assertEqual(job["link_status"], "ok")
        self.assertEqual(job["link_validation_version"], mod.LINK_VALIDATION_VERSION)

    def test_generic_page_does_not_exist_phrase_is_dead(self):
        class Response:
            status_code = 200
            url = "https://jobs.example.com/careers/123"
            headers = {"content-type": "text/html"}
            encoding = "utf-8"

            def iter_content(self, chunk_size=16384):
                yield b"<html><body>Page does not exist</body></html>"

            def close(self):
                pass

        with patch.object(mod.requests, "get", return_value=Response()):
            status, final = mod.validate_direct_url(
                "https://jobs.example.com/careers/123"
            )

        self.assertEqual(status, "dead")
        self.assertIn("jobs.example.com", final)

    def test_stale_workday_slug_uses_cxs_and_is_dead_on_404(self):
        class Response:
            status_code = 404
            url = "https://amgen.wd1.myworkdayjobs.com/wday/cxs/amgen/Careers/job/United-States---Remote/old_R-255719"

            def close(self):
                pass

        stale = (
            "https://amgen.wd1.myworkdayjobs.com/Careers/job/United-States---Remote/"
            "Undergrad-Intern-Software-Engineer-Technology-AI-Data-Summer-2027_R-255719"
        )
        with patch.object(mod.requests, "get", return_value=Response()) as get:
            status, final = mod.validate_direct_url(stale)

        self.assertEqual(status, "dead")
        self.assertEqual(final, stale)
        self.assertIn("/wday/cxs/amgen/Careers/job/", get.call_args.args[0])

    def test_live_workday_apply_route_is_ok(self):
        class Response:
            status_code = 200

            def json(self):
                return {"jobPostingInfo": {"canApply": True, "posted": True}}

            def close(self):
                pass

        live = "https://example.wd1.myworkdayjobs.com/Careers/job/Remote/live_R-123/apply"
        with patch.object(mod.requests, "get", return_value=Response()):
            status, final = mod.validate_direct_url(live)

        self.assertEqual(status, "ok")
        self.assertEqual(final, live)

    def test_unknown_workday_apply_is_downgraded_instead_of_blocking_publish(self):
        url = "https://jj.wd5.myworkdayjobs.com/jj/job/Cincinnati-Ohio-United-States-of-America/Software-Engineering-Co-Op-Summer-2027_R-096743/apply"
        job = {
            "id": "jj-r-096743",
            "company": "Johnson & Johnson",
            "title": "Software Engineering Co-Op Summer 2027",
            "location": "Cincinnati, OH",
            "source_names": ["Johnson & Johnson"],
            "source_keys": ["direct-workday-jj"],
            "source_urls": ["https://jj.wd5.myworkdayjobs.com/jj"],
            "profiles": ["cs"],
            "education_level": "undergrad",
            "opportunity_type": "internship",
            "link_kind": "direct",
            "url": url,
        }
        checked_at = datetime(2026, 9, 20, 13, 0, tzinfo=timezone.utc)
        with (
            patch.object(mod, "now_utc", return_value=checked_at),
            patch.object(mod, "validate_direct_url", return_value=("unknown", url)),
        ):
            stats = mod.validate_repaired_links({"jobs": [job]}, {"jobs": []})

        self.assertEqual(stats["unknown"], 1)
        self.assertEqual(job["link_status"], "unknown")
        self.assertEqual(job["link_kind"], "employer_job")
        self.assertEqual(
            job["url"],
            "https://jj.wd5.myworkdayjobs.com/jj/job/Cincinnati-Ohio-United-States-of-America/Software-Engineering-Co-Op-Summer-2027_R-096743",
        )
        self.assertEqual(job["unverified_apply_url"], url)
        self.assertEqual(
            validate_mod.workday_direct_contract_errors(job, "job jj-r-096743"),
            [],
        )

    def test_live_workday_job_page_is_recovery_target_not_final_apply_link(self):
        class Response:
            status_code = 200

            def json(self):
                return {"jobPostingInfo": {"canApply": True, "posted": True}}

            def close(self):
                pass

        bad = (
            "https://amgen.wd1.myworkdayjobs.com/Careers/job/United-States---Remote/"
            "Undergrad-Intern-Software-Engineer-Technology-AI-Data-Summer-2027_R-255719"
        )
        job = {
            "id": "amgen-r-255719",
            "company": "Amgen",
            "title": "Undergrad Intern - Software Engineer - Technology, AI & Data (Summer 2027)",
            "location": "Remote",
            "profiles": ["cs"],
            "opportunity_type": "internship",
            "link_kind": "direct",
            "url": bad,
        }

        with patch.object(mod.requests, "get", return_value=Response()):
            stats = mod.validate_repaired_links({"jobs": [job]}, {"jobs": []})

        self.assertEqual(stats["dead"], 1)
        self.assertEqual(job["url"], "")
        self.assertEqual(job["dead_url"], bad)
        self.assertEqual(job["link_kind"], "source")


class WorkdayEmployerJobSemanticsTests(unittest.TestCase):
    def _feed_job(self, url):
        return {
            "id": "medtronic-r73625",
            "company": "Medtronic",
            "title": "IT Intern - Summer 2027",
            "location": "Minneapolis, MN",
            "source_names": ["Medtronic"],
            "source_keys": ["direct-workday-medtronic"],
            "source_urls": ["https://medtronic.wd1.myworkdayjobs.com/"],
            "profiles": ["cs"],
            "education_level": "undergrad",
            "opportunity_type": "internship",
            "url": url,
        }

    def test_workday_job_page_is_employer_job_not_direct_apply(self):
        url = (
            "https://medtronic.wd1.myworkdayjobs.com/en-US/redeploymentmedtroniccareers/"
            "job/Minneapolis-Minnesota-United-States-of-America/IT-Intern---Summer-2027_R73625"
        )
        doc = {"jobs": [self._feed_job(url)]}
        mod.repair_document(doc)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "employer_job")
        self.assertEqual(job["url"], url)
        self.assertFalse(mod.should_validate_direct_link(job))
        self.assertEqual(
            validate_mod.workday_direct_contract_errors(job, "job medtronic-r73625"),
            [],
        )

    def test_workday_apply_url_remains_direct_apply(self):
        url = (
            "https://medtronic.wd1.myworkdayjobs.com/en-US/redeploymentmedtroniccareers/"
            "job/Minneapolis-Minnesota-United-States-of-America/IT-Intern---Summer-2027_R73625/apply"
        )
        doc = {"jobs": [self._feed_job(url)]}
        mod.repair_document(doc)
        self.assertEqual(doc["jobs"][0]["link_kind"], "direct")

    def test_validator_accepts_employer_job_kind(self):
        url = (
            "https://medtronic.wd1.myworkdayjobs.com/en-US/redeploymentmedtroniccareers/"
            "job/Minneapolis-Minnesota-United-States-of-America/IT-Intern---Summer-2027_R73625"
        )
        job = self._feed_job(url)
        job["link_kind"] = "employer_job"
        doc = {"jobs": [job], "sources": {"medtronic": {"status": "healthy"}}}
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile("w+", suffix=".json") as handle:
            json.dump(doc, handle)
            handle.flush()
            errors = validate_mod.validate(
                Path(handle.name),
                minimum_jobs=1,
                minimum_healthy_sources=1,
                strict_sources=False,
                enforce_link_contract=True,
            )
        self.assertEqual(errors, [])



class WorkdayPublishContractTests(unittest.TestCase):
    def _job(self, url, *, status="ok", checked_at="2026-09-18T14:00:00Z"):
        return {
            "id": "amgen-r-255719",
            "company": "Amgen",
            "title": "Undergrad Intern - Software Engineer",
            "location": "Remote",
            "source_names": ["Amgen"],
            "profiles": ["cs"],
            "education_level": "undergrad",
            "opportunity_type": "internship",
            "link_kind": "direct",
            "url": url,
            "link_status": status,
            "link_checked_at": checked_at,
        }

    def test_publish_contract_rejects_live_workday_job_page_as_direct_apply(self):
        job = self._job(
            "https://amgen.wd1.myworkdayjobs.com/Careers/job/United-States---Remote/"
            "Undergrad-Intern-Software-Engineer_R-255719"
        )
        errors = validate_mod.workday_direct_contract_errors(job, "job amgen-r-255719")
        self.assertTrue(any("not an /apply destination" in error for error in errors))
        self.assertTrue(all(error.startswith("link-quality:") for error in errors))

    def test_publish_contract_rejects_unvalidated_workday_apply_url(self):
        job = self._job(
            "https://amgen.wd1.myworkdayjobs.com/Careers/job/United-States---Remote/"
            "Undergrad-Intern-Software-Engineer_R-255719/apply",
            status="unknown",
            checked_at="",
        )
        errors = validate_mod.workday_direct_contract_errors(job, "job amgen-r-255719")
        self.assertTrue(any("not validated ok" in error for error in errors))
        self.assertTrue(any("no validation timestamp" in error for error in errors))

    def test_publish_contract_accepts_validated_workday_apply_url(self):
        job = self._job(
            "https://amgen.wd1.myworkdayjobs.com/Careers/job/United-States---Remote/"
            "Undergrad-Intern-Software-Engineer_R-255719/apply"
        )
        self.assertEqual(
            validate_mod.workday_direct_contract_errors(job, "job amgen-r-255719"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
