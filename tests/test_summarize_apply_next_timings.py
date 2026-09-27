import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_apply_next_timings import (
    extract_timings,
    percentile,
    render_text,
    summarize,
)


class ApplyNextTimingSummaryTests(unittest.TestCase):
    def sample_payload(self, totals=(1000, 2000, 3000, 4000)):
        timings = []
        for index, total in enumerate(totals):
            timings.append(
                {
                    "total_ms": total,
                    "status": "success" if index < len(totals) - 1 else "error",
                    "stages_ms": {
                        "candidate_artifact": total * 0.25,
                        "preliminary_ranking": total * 0.5,
                        "ranking": total * 0.1,
                    },
                    "profile": {"should": "not matter"},
                }
            )
        return {
            "schema": "yartchives-usage-v2",
            "visitorId": "visitor-test",
            "timings": timings,
        }

    def test_extracts_nested_analytics_payloads(self):
        wrapper = {"submissions": [{"data": self.sample_payload()}]}
        timings = extract_timings([wrapper])
        self.assertEqual(len(timings), 4)
        self.assertEqual(timings[0]["total_ms"], 1000)

    def test_ignores_other_schemas_and_invalid_timings(self):
        values = [
            {"schema": "other", "timings": [{"total_ms": 1}]},
            {
                "schema": "yartchives-usage-v2",
                "timings": [
                    {"total_ms": -1},
                    {"total_ms": "bad"},
                    {"total_ms": 1500, "status": "success"},
                ],
            },
        ]
        timings = extract_timings(values)
        self.assertEqual([item["total_ms"] for item in timings], [1500])

    def test_percentile_interpolates(self):
        self.assertEqual(percentile([1000, 2000, 3000, 4000], 0.5), 2500)
        self.assertEqual(percentile([1000], 0.95), 1000)
        self.assertIsNone(percentile([], 0.95))

    def test_summary_reports_latency_success_and_stage_stats(self):
        summary = summarize(extract_timings([self.sample_payload()]))
        self.assertEqual(summary["sample_count"], 4)
        self.assertEqual(summary["success_count"], 3)
        self.assertEqual(summary["success_rate"], 0.75)
        self.assertEqual(summary["total"]["median_ms"], 2500.0)
        self.assertEqual(summary["total"]["p90_ms"], 3700.0)
        self.assertEqual(summary["total"]["p95_ms"], 3850.0)
        self.assertEqual(summary["stages"]["preliminary_ranking"]["median_ms"], 1250.0)

    def test_text_output_surfaces_actionable_percentiles(self):
        text = render_text(summarize(extract_timings([self.sample_payload()])))
        self.assertIn("median 2500.0 ms", text)
        self.assertIn("p90 3700.0 ms", text)
        self.assertIn("p95 3850.0 ms", text)
        self.assertIn("Success rate: 75.0%", text)
        self.assertIn("preliminary_ranking", text)


if __name__ == "__main__":
    unittest.main()
