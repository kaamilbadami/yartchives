from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import query_job_cache as query_cache


class QueryJobCacheTests(unittest.TestCase):
    def sample_feed(self):
        return [
            {
                "id": "feed-1",
                "company": "WEX",
                "title": "Software Engineering Intern",
                "location": "Portland, ME",
                "url": "https://wexinc.wd5.myworkdayjobs.com/WEXInc/job/Portland-ME/Software-Engineering-Intern_R22593",
                "source_keys": ["simplify"],
            },
            {
                "id": "feed-2",
                "company": "Example Co",
                "title": "Data Intern",
                "url": "https://example.test/jobs/123",
            },
        ]

    def sample_cache(self):
        key = "https://wexinc.wd5.myworkdayjobs.com/WEXInc/job/Portland-ME/Software-Engineering-Intern_R22593"
        return {
            "entries": {
                key: {
                    "provider": "workday",
                    "requirements_extractor_version": 4,
                    "last_success_at": "2026-09-17T02:20:00Z",
                    "inspection": {
                        "status": "inspected",
                        "retrieval_confidence": "high",
                        "posting": {
                            "title": "Software Engineering Intern",
                            "description": "A deliberately large authoritative posting body.",
                            "requisition_id": "R22593",
                            "application_status": "available",
                            "locations": {"status": "authoritative", "values": ["Portland, ME"]},
                        },
                        "requirements": {
                            "skills": {
                                "classification": "required",
                                "required": [{"statement": "Experience with Python"}],
                            }
                        },
                        "provenance": {
                            "canonical_job_url": key,
                            "source_url": key,
                        },
                    },
                }
            }
        }

    def test_requisition_finds_listing_and_cache_entry(self):
        result = query_cache.query_records(self.sample_feed(), self.sample_cache(), "R22593")

        self.assertEqual(result["counts"], {"listings": 1, "cache_entries": 1})
        self.assertEqual(result["listings"][0]["company"], "WEX")
        self.assertEqual(
            result["cache_entries"][0]["inspection"]["posting"]["requisition_id"],
            "R22593",
        )

    def test_compact_output_excludes_description_but_keeps_requirements(self):
        result = query_cache.query_records(self.sample_feed(), self.sample_cache(), "WEX")
        inspection = result["cache_entries"][0]["inspection"]

        self.assertNotIn("description", inspection["posting"])
        self.assertEqual(
            inspection["requirements"]["skills"]["required"][0]["statement"],
            "Experience with Python",
        )

    def test_full_output_preserves_complete_cache_entry(self):
        result = query_cache.query_records(
            self.sample_feed(), self.sample_cache(), "R22593", full=True
        )

        entry = result["cache_entries"][0]["entry"]
        self.assertIn("description", entry["inspection"]["posting"])

    def test_query_does_not_match_description_only(self):
        result = query_cache.query_records(
            self.sample_feed(), self.sample_cache(), "deliberately large"
        )

        self.assertEqual(result["counts"], {"listings": 0, "cache_entries": 0})

    def test_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            query_cache.query_records([], {}, "R22593", limit=0)


if __name__ == "__main__":
    unittest.main()
