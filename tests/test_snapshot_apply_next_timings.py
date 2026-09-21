import unittest

from scripts.snapshot_apply_next_timings import ALLOWED_STAGES, build_snapshot


class ApplyNextTimingSnapshotTests(unittest.TestCase):
    def test_strips_identity_and_summarizes_current_stages(self):
        payload = {
            "submissions": [{
                "_date": "2026-09-21T16:30:00Z",
                "schema": "yartchives-usage-v2",
                "visitorId": "visitor-secret",
                "sessionId": "session-secret",
                "build": "abc123",
                "timings": [{
                    "total_ms": 10400,
                    "stages_ms": {
                        "paint_wait": 10,
                        "candidate_artifact": 9600,
                        "candidate_filter": 40,
                        "inspection_artifact": 200,
                        "inspection_attach": 20,
                        "location_enrichment": 300,
                        "ranking": 100,
                        "render": 130,
                        "evil_stage": 99999,
                    },
                    "counts": {"candidates": 5000, "rankable": 45, "recommendations": 10},
                    "status": "success",
                    "profile": {"zip": "20740"},
                    "jobId": "private-job",
                }],
            }],
        }

        snapshot = build_snapshot(payload)
        self.assertEqual(snapshot["summary"]["samples"], 1)
        self.assertEqual(snapshot["summary"]["median_total_ms"], 10400.0)
        self.assertEqual(snapshot["summary"]["stages"]["candidate_artifact"]["median_ms"], 9600.0)
        encoded = str(snapshot)
        self.assertNotIn("visitor-secret", encoded)
        self.assertNotIn("session-secret", encoded)
        self.assertNotIn("20740", encoded)
        self.assertNotIn("private-job", encoded)
        self.assertNotIn("evil_stage", encoded)
        self.assertEqual(
            set(snapshot["recent"][0]["stages_ms"]),
            set(ALLOWED_STAGES),
        )

    def test_accepts_formspree_json_encoded_timings(self):
        payload = {
            "submissions": [{
                "_date": "2026-09-21T16:31:00Z",
                "schema": "yartchives-usage-v2",
                "build": "def456",
                "timings": '[{"total_ms":123.4,"stages_ms":{"render":12.3},"counts":{"recommendations":10}}]',
            }],
        }
        snapshot = build_snapshot(payload)
        self.assertEqual(snapshot["recent"][0]["total_ms"], 123.4)
        self.assertEqual(snapshot["recent"][0]["stages_ms"], {"render": 12.3})

    def test_ignores_non_usage_submissions(self):
        payload = {
            "submissions": [
                {"schema": "other", "timings": [{"total_ms": 1}]},
                {"message": "feedback"},
            ]
        }
        snapshot = build_snapshot(payload)
        self.assertEqual(snapshot["summary"]["samples"], 0)
        self.assertEqual(snapshot["recent"], [])


if __name__ == "__main__":
    unittest.main()
