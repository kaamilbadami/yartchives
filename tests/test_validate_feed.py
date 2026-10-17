import json
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
import scripts.validate_feed as vf

class ValidateFeedTests(unittest.TestCase):
    def _create_feed(self, jobs, sources=None):
        if sources is None:
            sources = {"source1": {"status": "healthy"}}
        return {
            "jobs": jobs,
            "sources": sources
        }

    def _valid_job(self, override=None):
        job = {
            "id": "job1",
            "company": "Company A",
            "title": "Software Intern",
            "location": "NY",
            "source_names": ["source1"],
            "profiles": ["cs"],
            "education_level": "undergrad",
            "opportunity_type": "internship",
            "link_kind": "direct",
            "url": "https://example.com/apply"
        }
        if override:
            job.update(override)
        return job

    def test_successful_validation(self):
        feed = self._create_feed([self._valid_job()])
        with NamedTemporaryFile("w+", suffix=".json") as f:
            json.dump(feed, f)
            f.flush()
            errors = vf.validate(Path(f.name), minimum_jobs=1, minimum_healthy_sources=1, strict_sources=False)
            self.assertEqual(errors, [])

    def test_legacy_source_health_is_accepted_during_status_migration(self):
        feed = self._create_feed(
            [self._valid_job()],
            sources={
                "legacy-healthy": {"ok": True, "configured": True},
                "legacy-disabled": {"ok": False, "configured": False},
            },
        )
        with NamedTemporaryFile("w+", suffix=".json") as f:
            json.dump(feed, f)
            f.flush()
            errors = vf.validate(
                Path(f.name),
                minimum_jobs=1,
                minimum_healthy_sources=1,
                strict_sources=True,
            )
            self.assertEqual(errors, [])

    def test_record_level_quarantine_missing_title(self):
        bad_job = self._valid_job({"id": "job2", "title": ""})
        feed = self._create_feed([self._valid_job(), bad_job])
        with NamedTemporaryFile("w+", suffix=".json") as f:
            json.dump(feed, f)
            f.flush()
            errors = vf.validate(Path(f.name), minimum_jobs=1, minimum_healthy_sources=1, strict_sources=False)
            self.assertEqual(errors, [])

            f.seek(0)
            doc = json.load(f)
            self.assertEqual(len(doc["jobs"]), 1)
            self.assertEqual(doc["jobs"][0]["id"], "job1")

    def test_record_level_downgrade_bad_link(self):
        bad_link_job = self._valid_job({"id": "job2", "url": "not-a-url"})
        feed = self._create_feed([self._valid_job(), bad_link_job])
        with NamedTemporaryFile("w+", suffix=".json") as f:
            json.dump(feed, f)
            f.flush()
            errors = vf.validate(Path(f.name), minimum_jobs=1, minimum_healthy_sources=1, strict_sources=False)
            self.assertEqual(errors, [])

            f.seek(0)
            doc = json.load(f)
            self.assertEqual(len(doc["jobs"]), 2)

            job2 = next(j for j in doc["jobs"] if j["id"] == "job2")
            self.assertEqual(job2["link_kind"], "source")
            self.assertNotIn("url", job2)

    def test_record_level_downgrade_workday_contract(self):
        workday_job = self._valid_job({
            "id": "job2",
            "url": "https://example.wd1.myworkdayjobs.com/Careers/job/Remote/role"
        })
        feed = self._create_feed([self._valid_job(), workday_job])
        with NamedTemporaryFile("w+", suffix=".json") as f:
            json.dump(feed, f)
            f.flush()
            errors = vf.validate(
                Path(f.name),
                minimum_jobs=1,
                minimum_healthy_sources=1,
                strict_sources=False,
                enforce_link_contract=True
            )
            self.assertEqual(errors, [])

            f.seek(0)
            doc = json.load(f)
            job2 = next(j for j in doc["jobs"] if j["id"] == "job2")
            self.assertEqual(job2["link_kind"], "source")
            self.assertNotIn("url", job2)

    def test_fatal_condition_duplicate_ids(self):
        feed = self._create_feed([self._valid_job(), self._valid_job()])
        with NamedTemporaryFile("w+", suffix=".json") as f:
            json.dump(feed, f)
            f.flush()
            errors = vf.validate(Path(f.name), minimum_jobs=1, minimum_healthy_sources=1, strict_sources=False)
            self.assertTrue(any("duplicate job id job1" in e for e in errors))

    def test_fatal_condition_count_collapse(self):
        bad_job = self._valid_job({"id": "job2", "title": ""})
        feed = self._create_feed([self._valid_job(), bad_job])
        with NamedTemporaryFile("w+", suffix=".json") as f:
            json.dump(feed, f)
            f.flush()
            # Feed has 2 jobs, but 1 will be quarantined. Minimum is 2.
            errors = vf.validate(Path(f.name), minimum_jobs=2, minimum_healthy_sources=1, strict_sources=False)
            self.assertTrue(any("job count 1 is below minimum 2" in e for e in errors))

if __name__ == '__main__':
    unittest.main()
