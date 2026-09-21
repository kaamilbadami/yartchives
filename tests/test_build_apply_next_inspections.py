import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_apply_next_inspections import build_frontend_artifact


class ApplyNextInspectionArtifactTests(unittest.TestCase):
    def test_strips_heavy_posting_bodies_but_preserves_ranking_evidence(self):
        cache = {
            "version": 6,
            "updated_at": "2026-09-20T20:00:00Z",
            "priority_term": "Summer 2027",
            "listing_index": {"job-1": "https://example.test/job-1"},
            "entries": {
                "https://example.test/job-1": {
                    "provider": "workday",
                    "last_attempted_at": "ignored",
                    "inspection": {
                        "status": "inspected",
                        "posting": {
                            "posted_at": "2026-09-20",
                            "application_status": "available",
                            "description": "x" * 100000,
                            "description_html": "<p>heavy</p>",
                            "raw_description": "heavy",
                        },
                        "schedule": {"terms": ["summer 2027"]},
                        "requirements": {
                            "skills": {"required": [{"statement": "Python"}]}
                        },
                    },
                }
            },
        }

        artifact = build_frontend_artifact(cache)
        entry = artifact["entries"]["https://example.test/job-1"]

        self.assertEqual(artifact["listing_index"], cache["listing_index"])
        self.assertEqual(entry["provider"], "workday")
        self.assertNotIn("last_attempted_at", entry)
        posting = entry["inspection"]["posting"]
        self.assertNotIn("description", posting)
        self.assertNotIn("description_html", posting)
        self.assertNotIn("raw_description", posting)
        self.assertEqual(posting["posted_at"], "2026-09-20")
        self.assertEqual(posting["application_status"], "available")
        self.assertEqual(
            entry["inspection"]["requirements"]["skills"]["required"][0]["statement"],
            "Python",
        )

    def test_projection_is_materially_smaller_when_descriptions_dominate(self):
        cache = {
            "entries": {
                f"url-{i}": {
                    "inspection": {
                        "status": "inspected",
                        "posting": {"description": "x" * 10000, "posted_at": "2026-09-20"},
                        "requirements": {},
                    }
                }
                for i in range(20)
            },
            "listing_index": {},
        }
        source_bytes = len(json.dumps(cache))
        compact_bytes = len(json.dumps(build_frontend_artifact(cache)))
        self.assertLess(compact_bytes, source_bytes * 0.1)


if __name__ == "__main__":
    unittest.main()
