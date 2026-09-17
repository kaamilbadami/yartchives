import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "update_workday_inspections.py"
spec = importlib.util.spec_from_file_location("update_workday_inspections", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = datetime(2026, 9, 16, 17, 30, tzinfo=timezone.utc)


def workday_job(
    job_id,
    req="REQ-1",
    posted_at="2026-09-16T12:00:00Z",
    link_kind="direct",
    *,
    title="Software Intern",
    term="Summer 2027",
    opportunity_type="internship",
    education_level="undergrad",
):
    return {
        "id": job_id,
        "company": "Example",
        "title": title,
        "url": f"https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/Role_{req}",
        "posted_at": posted_at,
        "link_kind": link_kind,
        "term": term,
        "opportunity_type": opportunity_type,
        "education_level": education_level,
    }


def icims_job(
    job_id,
    posting_id="1001",
    posted_at="2026-09-16T12:00:00Z",
    link_kind="direct",
    *,
    title="Data Intern",
    term="Summer 2027",
):
    return {
        "id": job_id,
        "company": "Example iCIMS",
        "title": title,
        "url": f"https://careers-example.icims.com/jobs/{posting_id}/role/job?mobile=true&utm_source=Simplify&ref=Simplify",
        "posted_at": posted_at,
        "link_kind": link_kind,
        "term": term,
        "opportunity_type": "internship",
        "education_level": "undergrad",
    }


def greenhouse_job(
    job_id,
    posting_id="8171041",
    posted_at="2026-09-16T12:00:00Z",
    link_kind="direct",
    *,
    board="doordashusa",
    title="Software Engineer Intern",
    term="Summer 2027",
    legacy_host=False,
):
    host = "boards.greenhouse.io" if legacy_host else "job-boards.greenhouse.io"
    return {
        "id": job_id,
        "company": "Example Greenhouse",
        "title": title,
        "url": f"https://{host}/{board}/jobs/{posting_id}?gh_src=feed&utm_source=Simplify",
        "posted_at": posted_at,
        "link_kind": link_kind,
        "term": term,
        "opportunity_type": "internship",
        "education_level": "undergrad",
    }


def inspection(url, status="inspected", at="2026-09-16T17:30:00Z"):
    posting = {"application_status": "available"} if status == "inspected" else None
    return {
        "status": status,
        "retrieval_confidence": "high" if status == "inspected" else "none",
        "error": None if status in {"inspected", "unavailable"} else "temporary",
        "posting": posting,
        "requirements": {},
        "provenance": {"source_url": url, "inspected_at": at},
    }


class UpdateWorkdayInspectionTests(unittest.TestCase):
    def test_applies_explicit_independent_provider_request_caps(self):
        jobs = [
            workday_job("wd-new", "REQ-1", "2026-09-16T15:00:00Z"),
            workday_job("wd-old", "REQ-2", "2026-09-15T15:00:00Z"),
            icims_job("icims-new", "1001", "2026-09-16T16:00:00Z"),
            icims_job("icims-old", "1002", "2026-09-14T16:00:00Z"),
            greenhouse_job("gh-new", "8171041", "2026-09-16T16:30:00Z"),
            greenhouse_job("gh-old", "8171042", "2026-09-13T16:00:00Z"),
        ]
        calls = []
        updated, stats = mod.refresh_cache(
            {"jobs": jobs},
            mod.empty_cache(),
            max_workday_requests=1,
            max_icims_requests=1,
            max_greenhouse_requests=1,
            max_ashby_requests=0,
            now=lambda: NOW,
            inspector=lambda url: calls.append(url) or inspection(url),
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(sum("myworkdayjobs.com" in url for url in calls), 1)
        self.assertEqual(sum("icims.com" in url for url in calls), 1)
        self.assertEqual(sum("greenhouse.io" in url for url in calls), 1)
        self.assertEqual(
            stats["provider_requests"],
            {"workday": 1, "icims": 1, "greenhouse": 1, "ashby": 0},
        )
        self.assertEqual(
            stats["provider_caps"],
            {"workday": 1, "icims": 1, "greenhouse": 1, "ashby": 0},
        )
        self.assertEqual(stats["workday_listings"], 2)
        self.assertEqual(stats["icims_listings"], 2)
        self.assertEqual(stats["greenhouse_listings"], 2)
        for entry in updated["entries"].values():
            self.assertIn(entry["provider"], {"workday", "icims", "greenhouse"})

    def test_greenhouse_tracking_variants_share_one_cache_identity(self):
        current = greenhouse_job("current", "8171041")
        legacy = greenhouse_job("legacy", "8171041", legacy_host=True)
        listing_index, by_url = mod.build_listing_index([current, legacy])
        canonical = "https://job-boards.greenhouse.io/doordashusa/jobs/8171041"
        self.assertEqual(listing_index, {"current": canonical, "legacy": canonical})
        self.assertEqual(list(by_url), [canonical])

    def test_greenhouse_transient_failure_preserves_last_good_inspection(self):
        job = greenhouse_job("greenhouse-one")
        canonical = mod.greenhouse_identity(job)["canonical_url"]
        good = inspection(canonical, at="2026-09-01T00:00:00Z")
        good["provider"] = "greenhouse"
        cache = mod.empty_cache()
        cache["entries"][canonical] = {
            "provider": "greenhouse",
            "inspection": good,
            "last_attempted_at": "2026-09-01T00:00:00Z",
            "last_success_at": "2026-09-01T00:00:00Z",
            "last_error": None,
        }
        failed = inspection(canonical, status="failed")
        updated, stats = mod.refresh_cache(
            {"jobs": [job]},
            cache,
            max_workday_requests=0,
            max_icims_requests=0,
            max_greenhouse_requests=1,
            now=lambda: NOW,
            inspector=lambda url: failed,
        )
        self.assertEqual(stats["preserved_last_good"], 1)
        self.assertEqual(updated["entries"][canonical]["inspection"], good)
        self.assertTrue(updated["entries"][canonical]["last_error"])

    def test_greenhouse_queue_failure_and_unsupported_states_are_materialized(self):
        queued = greenhouse_job("queued", "8171041")
        failed = greenhouse_job("failed", "8171042")
        unsupported = {
            **greenhouse_job("unsupported", "8171043"),
            "url": "https://job-boards.greenhouse.io/doordashusa?gh_src=feed",
        }
        failed_canonical = mod.greenhouse_identity(failed)["canonical_url"]
        cache = mod.empty_cache()
        cache["entries"][failed_canonical] = {
            "provider": "greenhouse",
            "inspection": inspection(failed_canonical, status="failed"),
            "last_attempted_at": "2026-09-16T16:30:00Z",
            "last_success_at": None,
            "last_error": "temporary",
        }
        updated, stats = mod.refresh_cache(
            {"jobs": [queued, failed, unsupported]},
            cache,
            max_workday_requests=0,
            max_icims_requests=0,
            max_greenhouse_requests=0,
            now=lambda: NOW,
        )
        queued_canonical = mod.greenhouse_identity(queued)["canonical_url"]
        unsupported_canonical = mod.greenhouse_identity(unsupported)["canonical_url"]
        self.assertEqual(updated["entries"][queued_canonical]["inspection"]["status"], "queued")
        self.assertEqual(updated["queue"][queued_canonical]["state"], "queued")
        self.assertEqual(updated["queue"][failed_canonical]["state"], "retry_cooldown")
        self.assertEqual(
            updated["entries"][failed_canonical]["inspection"]["queue"]["state"],
            "retry_cooldown",
        )
        self.assertEqual(updated["queue"][unsupported_canonical]["state"], "unsupported_url")
        self.assertEqual(
            updated["entries"][unsupported_canonical]["inspection"]["status"], "unsupported_url",
        )
        self.assertEqual(stats["requested"], 0)

    def test_icims_transient_failure_preserves_last_good_inspection(self):
        job = icims_job("icims-one", "2001")
        canonical = mod.icims_identity(job)["canonical_url"]
        good = inspection(canonical, at="2026-09-01T00:00:00Z")
        good["provider"] = "icims"
        cache = mod.empty_cache()
        cache["entries"][canonical] = {
            "provider": "icims",
            "inspection": good,
            "last_attempted_at": "2026-09-01T00:00:00Z",
            "last_success_at": "2026-09-01T00:00:00Z",
            "last_error": None,
        }
        failed = inspection(canonical, status="failed")
        updated, stats = mod.refresh_cache(
            {"jobs": [job]},
            cache,
            max_workday_requests=0,
            max_icims_requests=1,
            now=lambda: NOW,
            inspector=lambda url: failed,
        )
        self.assertEqual(stats["preserved_last_good"], 1)
        self.assertEqual(updated["entries"][canonical]["inspection"], good)
        self.assertTrue(updated["entries"][canonical]["last_error"])

    def test_cached_icims_description_is_renormalized_without_a_request(self):
        job = icims_job("cached", "2002")
        canonical = mod.icims_identity(job)["canonical_url"]
        good = inspection(canonical, at="2026-09-15T17:30:00Z")
        good["provider"] = "icims"
        good["posting"]["description"] = (
            "Required Qualifications\nPython experience is required.\n"
            "Preferred Qualifications\nLinux experience preferred."
        )
        cache = mod.empty_cache()
        cache["entries"][canonical] = {
            "provider": "icims",
            "inspection": good,
            "last_attempted_at": "2026-09-15T17:30:00Z",
            "last_success_at": "2026-09-15T17:30:00Z",
            "last_error": None,
        }
        calls = []
        updated, stats = mod.refresh_cache(
            {"jobs": [job]},
            cache,
            max_workday_requests=0,
            max_icims_requests=1,
            now=lambda: NOW,
            inspector=lambda url: calls.append(url),
        )
        skills = updated["entries"][canonical]["inspection"]["requirements"]["skills"]
        self.assertEqual(calls, [])
        self.assertEqual(stats["requested"], 0)
        self.assertEqual(skills["required"][0]["technologies"], ["Python"])
        self.assertEqual(skills["preferred"][0]["technologies"], ["Linux"])

    def test_icims_queue_retry_and_unsupported_statuses_are_materialized(self):
        queued = icims_job("queued", "3001")
        failed = icims_job("failed", "3002")
        unsupported = {
            **icims_job("unsupported", "3003"),
            "url": "https://careers-example.icims.com/jobs/search?ref=feed",
        }
        failed_canonical = mod.icims_identity(failed)["canonical_url"]
        cache = mod.empty_cache()
        cache["entries"][failed_canonical] = {
            "provider": "icims",
            "inspection": inspection(failed_canonical, status="failed"),
            "last_attempted_at": "2026-09-16T16:30:00Z",
            "last_success_at": None,
            "last_error": "temporary",
        }
        updated, stats = mod.refresh_cache(
            {"jobs": [queued, failed, unsupported]},
            cache,
            max_workday_requests=0,
            max_icims_requests=0,
            now=lambda: NOW,
        )
        queued_canonical = mod.icims_identity(queued)["canonical_url"]
        unsupported_canonical = mod.icims_identity(unsupported)["canonical_url"]
        self.assertEqual(updated["entries"][queued_canonical]["inspection"]["status"], "queued")
        self.assertEqual(updated["queue"][queued_canonical]["state"], "queued")
        self.assertEqual(updated["queue"][failed_canonical]["state"], "retry_cooldown")
        self.assertEqual(updated["entries"][failed_canonical]["inspection"]["queue"]["state"], "retry_cooldown")
        self.assertEqual(updated["queue"][unsupported_canonical]["state"], "unsupported_url")
        self.assertEqual(updated["entries"][unsupported_canonical]["inspection"]["status"], "unsupported_url")
        self.assertEqual(stats["requested"], 0)

    def test_bounds_requests_and_ignores_non_direct_or_other_provider(self):
        jobs = [
            workday_job("newest", "REQ-1", "2026-09-16T15:00:00Z"),
            workday_job("older", "REQ-2", "2026-09-15T15:00:00Z"),
            workday_job("listing", "REQ-3", link_kind="listing"),
            {"id": "lever", "url": "https://jobs.lever.co/x/1", "link_kind": "direct"},
        ]
        feed = {"jobs": copy.deepcopy(jobs)}
        original_feed = copy.deepcopy(feed)
        calls = []

        def fake(url):
            calls.append(url)
            return inspection(url)

        updated, stats = mod.refresh_cache(
            feed, mod.empty_cache(), max_requests=1, now=lambda: NOW, inspector=fake
        )

        self.assertEqual(feed, original_feed)
        self.assertEqual(stats["workday_listings"], 2)
        self.assertEqual(stats["requested"], 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("REQ-1", calls[0])
        self.assertEqual(len(updated["listing_index"]), 2)
        older = mod.workday_identity(jobs[1])["canonical_url"]
        self.assertEqual(updated["queue"][older]["state"], "queued")
        self.assertEqual(updated["queue"][older]["rank"], 1)
        self.assertEqual(updated["entries"][older]["inspection"]["status"], "queued")
        self.assertEqual(updated["entries"][older]["inspection"]["queue"]["rank"], 1)

    def test_prioritizes_upcoming_summer_internship_over_newer_wrong_term(self):
        high_value = workday_job(
            "summer",
            "REQ-SUMMER",
            "2026-09-13T12:00:00Z",
            term="Summer 2027",
            opportunity_type="internship",
            education_level="undergrad",
        )
        newer_wrong_term = workday_job(
            "wrong",
            "REQ-WRONG",
            "2026-09-16T16:00:00Z",
            title="Graduate Research Role",
            term="Summer 2026",
            opportunity_type="research",
            education_level="graduate-only",
        )
        calls = []
        updated, stats = mod.refresh_cache(
            {"jobs": [newer_wrong_term, high_value]},
            mod.empty_cache(),
            max_requests=1,
            now=lambda: NOW,
            inspector=lambda url: calls.append(url) or inspection(url),
        )
        self.assertEqual(stats["priority_term"], "Summer 2027")
        self.assertEqual(len(calls), 1)
        self.assertIn("REQ-SUMMER", calls[0])
        wrong = mod.workday_identity(newer_wrong_term)["canonical_url"]
        self.assertEqual(updated["queue"][wrong]["state"], "queued")
        self.assertIn("other term: Summer 2026", updated["queue"][wrong]["reasons"])
        self.assertIn("graduate-only", updated["queue"][wrong]["reasons"])

    def test_failed_inspection_enters_retry_cooldown_with_visible_queue_state(self):
        job = workday_job("one")
        canonical = mod.workday_identity(job)["canonical_url"]
        failed = inspection(canonical, status="failed")
        updated, stats = mod.refresh_cache(
            {"jobs": [job]},
            mod.empty_cache(),
            max_requests=1,
            now=lambda: NOW,
            inspector=lambda url: failed,
        )
        self.assertEqual(stats["requested"], 1)
        self.assertEqual(updated["queue"][canonical]["state"], "retry_cooldown")
        self.assertEqual(updated["entries"][canonical]["inspection"]["queue"]["state"], "retry_cooldown")
        self.assertEqual(
            mod.candidate_urls({canonical: [job]}, updated["entries"], NOW, 7),
            [],
        )

    def test_fresh_success_is_reused_without_network_call(self):
        job = workday_job("one")
        canonical = mod.workday_identity(job)["canonical_url"]
        cache = mod.empty_cache()
        cache["entries"][canonical] = {
            "inspection": inspection(canonical),
            "last_attempted_at": "2026-09-15T17:30:00Z",
            "last_success_at": "2026-09-15T17:30:00Z",
            "last_error": None,
        }
        calls = []
        updated, stats = mod.refresh_cache(
            {"jobs": [job]}, cache, max_requests=25, ttl_days=7, now=lambda: NOW,
            inspector=lambda url: calls.append(url),
        )
        self.assertEqual(calls, [])
        self.assertEqual(stats["requested"], 0)
        self.assertEqual(updated["entries"][canonical]["last_success_at"], "2026-09-15T17:30:00Z")
        self.assertEqual(updated["queue"][canonical]["state"], "cached")

    def test_stale_success_is_refreshed(self):
        job = workday_job("one")
        canonical = mod.workday_identity(job)["canonical_url"]
        cache = mod.empty_cache()
        cache["entries"][canonical] = {
            "inspection": inspection(canonical, at="2026-09-01T00:00:00Z"),
            "last_attempted_at": "2026-09-01T00:00:00Z",
            "last_success_at": "2026-09-01T00:00:00Z",
            "last_error": None,
        }
        calls = []
        updated, stats = mod.refresh_cache(
            {"jobs": [job]}, cache, max_requests=25, ttl_days=7, now=lambda: NOW,
            inspector=lambda url: calls.append(url) or inspection(url),
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(stats["succeeded"], 1)
        self.assertEqual(updated["entries"][canonical]["last_success_at"], "2026-09-16T17:30:00Z")

    def test_transient_failure_preserves_last_good_inspection(self):
        job = workday_job("one")
        canonical = mod.workday_identity(job)["canonical_url"]
        good = inspection(canonical, at="2026-09-01T00:00:00Z")
        cache = mod.empty_cache()
        cache["entries"][canonical] = {
            "inspection": good,
            "last_attempted_at": "2026-09-01T00:00:00Z",
            "last_success_at": "2026-09-01T00:00:00Z",
            "last_error": None,
        }
        failed = inspection(canonical, status="failed")
        updated, stats = mod.refresh_cache(
            {"jobs": [job]}, cache, max_requests=25, ttl_days=7, now=lambda: NOW,
            inspector=lambda url: failed,
        )
        self.assertEqual(stats["preserved_last_good"], 1)
        self.assertEqual(updated["entries"][canonical]["inspection"], good)
        self.assertEqual(updated["entries"][canonical]["last_success_at"], "2026-09-01T00:00:00Z")
        self.assertTrue(updated["entries"][canonical]["last_error"])

    def test_unavailable_result_is_cached(self):
        job = workday_job("one")
        canonical = mod.workday_identity(job)["canonical_url"]
        updated, _ = mod.refresh_cache(
            {"jobs": [job]}, mod.empty_cache(), now=lambda: NOW,
            inspector=lambda url: inspection(url, status="unavailable"),
        )
        self.assertEqual(updated["entries"][canonical]["inspection"]["status"], "unavailable")
        self.assertIsNotNone(updated["entries"][canonical]["last_success_at"])

    def test_write_if_changed_avoids_timestamp_only_churn(self):
        original = mod.empty_cache()
        updated = copy.deepcopy(original)
        tmp = ROOT / "tests" / ".tmp-workday-inspections.json"
        try:
            changed = mod.write_if_changed(tmp, original, updated, NOW)
            self.assertFalse(changed)
            self.assertFalse(tmp.exists())

            updated["listing_index"]["x"] = "https://tenant.wd5.myworkdayjobs.com/Careers/job/CT/X"
            changed = mod.write_if_changed(tmp, original, updated, NOW)
            self.assertTrue(changed)
            saved = json.loads(tmp.read_text(encoding="utf-8"))
            self.assertEqual(saved["updated_at"], "2026-09-16T17:30:00Z")
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
