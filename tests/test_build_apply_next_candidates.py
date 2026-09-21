import json
import unittest

from scripts.build_apply_next_candidates import JOB_FIELDS, build_candidate_artifact


class ApplyNextCandidateArtifactTests(unittest.TestCase):
    def test_projects_only_fields_needed_by_apply_next(self):
        feed = {
            "generated_at": "2026-09-21T15:00:00Z",
            "content_hash": "abc",
            "jobs": [{
                "id": "job-1",
                "company": "Example",
                "title": "Software Intern",
                "location": "College Park, MD",
                "url": "https://example.test/job-1",
                "posted_at": "2026-09-21",
                "term": "Summer 2027",
                "profiles": ["cs"],
                "states": ["MD"],
                "opportunity_type": "internship",
                "education_level": "undergrad",
                "link_kind": "direct",
                "direct_employer": True,
                "function_primary": "software",
                "section": "engineering",
                "posted_date_observations": [{"huge": "x" * 10000}],
                "source_urls": ["https://example.test/source"],
                "link_checked_at": "2026-09-21T15:00:00Z",
            }],
            "sources": {"huge": {"payload": "x" * 10000}},
        }

        artifact = build_candidate_artifact(feed)
        self.assertEqual(artifact["generated_at"], feed["generated_at"])
        self.assertEqual(artifact["content_hash"], "abc")
        self.assertEqual(len(artifact["jobs"]), 1)
        job = artifact["jobs"][0]
        self.assertEqual(job["id"], "job-1")
        self.assertEqual(set(job), set(JOB_FIELDS))
        self.assertNotIn("posted_date_observations", job)
        self.assertNotIn("source_urls", job)
        self.assertNotIn("link_checked_at", job)

    def test_projection_is_materially_smaller_than_source_heavy_feed(self):
        feed = {
            "jobs": [{
                "id": f"job-{i}",
                "company": "Example",
                "title": "Intern",
                "location": "MD",
                "url": f"https://example.test/{i}",
                "profiles": ["cs"],
                "states": ["MD"],
                "posted_date_observations": [{"blob": "x" * 5000}],
                "source_names": ["source"] * 30,
                "source_urls": ["https://example.test/source"] * 30,
            } for i in range(100)],
            "sources": {f"source-{i}": {"blob": "x" * 5000} for i in range(100)},
        }
        source_bytes = len(json.dumps(feed))
        compact_bytes = len(json.dumps(build_candidate_artifact(feed)))
        self.assertLess(compact_bytes, source_bytes * 0.2)


if __name__ == "__main__":
    unittest.main()
