import json
import unittest

from scripts.build_apply_next_inspections import build_frontend_artifact


class ApplyNextInspectionArtifactTests(unittest.TestCase):
    def test_projects_only_frontend_ranking_and_presentation_contract(self):
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
                        "provider": "ignored-inspection-provider",
                        "retrieval_confidence": 0.99,
                        "error": None,
                        "provenance": {"large": "ignored"},
                        "queue": {"ignored": True},
                        "posting": {
                            "posted_at": "2026-09-20",
                            "application_status": "available",
                            "title": "Software Intern",
                            "requisition_id": "REQ-1",
                            "locations": {"status": "authoritative", "values": ["College Park, MD"]},
                            "description": "x" * 100000,
                            "description_html": "<p>heavy</p>",
                            "raw_description": "heavy",
                            "internal_job_id": "unused",
                            "employment_type": "unused",
                        },
                        "schedule": {
                            "terms": ["Summer 2027"],
                            "duration_evidence": ["12 weeks"],
                            "date_range_evidence": ["May-August 2027"],
                            "ignored": "value",
                        },
                        "requirements": {
                            "skills": {
                                "classification": "explicit",
                                "required": [
                                    {
                                        "statement": "Python required",
                                        "technologies": ["python"],
                                        "source": "ignored",
                                    }
                                ],
                                "preferred": [{"statement": "SQL preferred", "confidence": 0.9}],
                                "not_required": [],
                                "unspecified": [{"statement": "unused"}],
                            },
                            "work_authorization": {
                                "required": [{"statement": "No sponsorship"}],
                            },
                            "citizenship": {
                                "not_required": [{"statement": "Citizenship not required"}],
                            },
                            "graduation": {
                                "preferred": [{"statement": "Graduating in 2027"}],
                            },
                            "education": {
                                "required": [{"statement": "Bachelor's student"}],
                            },
                            "student_status": {
                                "required": [{"statement": "Currently enrolled"}],
                            },
                            "major_fields": {
                                "preferred": [{"statement": "Computer Science"}],
                            },
                            "other_eligibility": {
                                "required": [{"statement": "unused"}],
                            },
                        },
                    },
                }
            },
        }

        artifact = build_frontend_artifact(cache)
        entry = artifact["entries"]["https://example.test/job-1"]
        inspection = entry["inspection"]

        self.assertEqual(artifact["listing_index"], cache["listing_index"])
        self.assertEqual(entry["provider"], "workday")
        self.assertNotIn("last_attempted_at", entry)

        self.assertEqual(inspection["status"], "inspected")
        self.assertNotIn("provider", inspection)
        self.assertNotIn("retrieval_confidence", inspection)
        self.assertNotIn("provenance", inspection)
        self.assertNotIn("queue", inspection)
        self.assertNotIn("error", inspection)

        posting = inspection["posting"]
        self.assertEqual(
            set(posting),
            {"posted_at", "application_status", "title", "requisition_id", "locations"},
        )
        self.assertEqual(posting["posted_at"], "2026-09-20")
        self.assertEqual(posting["locations"]["values"], ["College Park, MD"])

        self.assertEqual(
            inspection["schedule"],
            {
                "terms": ["Summer 2027"],
                "duration_evidence": ["12 weeks"],
                "date_range_evidence": ["May-August 2027"],
            },
        )

        requirements = inspection["requirements"]
        self.assertNotIn("other_eligibility", requirements)
        self.assertEqual(
            requirements["skills"],
            {
                "required": [{"statement": "Python required", "technologies": ["python"]}],
                "preferred": [{"statement": "SQL preferred"}],
            },
        )
        self.assertEqual(
            requirements["citizenship"],
            {"not_required": [{"statement": "Citizenship not required"}]},
        )
        self.assertNotIn("classification", requirements["skills"])
        self.assertNotIn("unspecified", requirements["skills"])

    def test_projection_materially_shrinks_non_description_inspection_metadata(self):
        cache = {
            "entries": {
                f"url-{i}": {
                    "provider": "workday",
                    "inspection": {
                        "status": "inspected",
                        "provenance": {"responses": ["x" * 2000] * 5},
                        "retrieval_confidence": 0.95,
                        "posting": {
                            "posted_at": "2026-09-20",
                            "application_status": "available",
                            "title": "Intern",
                            "requisition_id": f"REQ-{i}",
                            "locations": {"status": "authoritative", "values": ["College Park, MD"]},
                            "internal_job_id": "x" * 500,
                        },
                        "requirements": {
                            "skills": {
                                "classification": "explicit",
                                "required": [
                                    {
                                        "statement": "Python required",
                                        "technologies": ["python"],
                                        "evidence": "x" * 1000,
                                    }
                                ],
                                "unspecified": [{"statement": "x" * 1000}],
                            }
                        },
                    },
                }
                for i in range(20)
            },
            "listing_index": {},
        }
        source_bytes = len(json.dumps(cache, separators=(",", ":")))
        compact_bytes = len(json.dumps(build_frontend_artifact(cache), separators=(",", ":")))
        self.assertLess(compact_bytes, source_bytes * 0.15)


if __name__ == "__main__":
    unittest.main()
