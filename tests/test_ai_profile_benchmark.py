import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ai_profile_benchmark.py"
spec = importlib.util.spec_from_file_location("ai_profile_benchmark", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class AiProfileBenchmarkTests(unittest.TestCase):
    def test_validate_classification_accepts_allowed_labels(self):
        result = mod.validate_classification({
            "labels": ["finance-econ", "cs", "cs"],
            "confidence": 0.97,
            "evidence": ["quantitative developer", "software"],
        })
        self.assertEqual(result.labels, ("cs", "finance-econ"))
        self.assertEqual(result.confidence, 0.97)
        self.assertEqual(result.evidence, ("quantitative developer", "software"))

    def test_validate_classification_rejects_general_plus_specialized(self):
        with self.assertRaises(ValueError):
            mod.validate_classification({
                "labels": ["general", "cs"],
                "confidence": 0.8,
                "evidence": [],
            })

    def test_compact_job_evidence_excludes_private_or_irrelevant_fields(self):
        job = {
            "company": "Example",
            "title": "Software Intern",
            "location": "Remote",
            "profiles": ["general"],
            "resume": "private",
            "user_profile": {"zip": "00000"},
            "requirements": {
                "skills": {
                    "required": [{"statement": "Python required"}],
                    "preferred": [{"statement": "SQL preferred"}],
                    "unspecified": [],
                    "not_required": [],
                }
            },
        }
        payload = mod.compact_job_evidence(job)
        self.assertEqual(payload["company"], "Example")
        self.assertEqual(payload["requirements"]["skills"], ["Python required", "SQL preferred"])
        self.assertNotIn("profiles", payload)
        self.assertNotIn("resume", payload)
        self.assertNotIn("user_profile", payload)

    def test_stable_general_sample_only_selects_general_jobs(self):
        jobs = [
            {"id": "a", "profiles": ["general"], "title": "A"},
            {"id": "b", "profiles": ["cs"], "title": "B"},
            {"id": "c", "profiles": ["general"], "title": "C"},
        ]
        sample1 = mod.stable_general_sample(jobs, 10)
        sample2 = mod.stable_general_sample(list(reversed(jobs)), 10)
        self.assertEqual([job["id"] for job in sample1], [job["id"] for job in sample2])
        self.assertEqual({job["id"] for job in sample1}, {"a", "c"})

    def test_score_gold_reports_exact_and_micro_metrics(self):
        score = mod.score_gold(
            [{"cs"}, {"finance-econ", "cs"}],
            [{"cs"}, {"finance-econ"}],
        )
        self.assertEqual(score["cases"], 2)
        self.assertEqual(score["exact_set_accuracy"], 0.5)
        self.assertEqual(score["micro_precision"], 1.0)
        self.assertAlmostEqual(score["micro_recall"], 2 / 3)

    @mock.patch.object(mod.requests, "post")
    def test_gemini_provider_requests_structured_json(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "labels": ["cs"],
                            "confidence": 0.96,
                            "evidence": ["software development"],
                        })
                    }]
                }
            }]
        }
        post.return_value = response

        provider = mod.GeminiProfileClassifier("secret", model="gemini-test", timeout=1)
        result = provider.classify({"company": "Example", "title": "Software Development Intern"})

        self.assertEqual(result.labels, ("cs",))
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "secret")
        self.assertEqual(
            kwargs["json"]["generationConfig"]["responseMimeType"],
            "application/json",
        )
        self.assertEqual(
            kwargs["json"]["generationConfig"]["responseSchema"],
            mod.RESPONSE_SCHEMA,
        )
        self.assertNotIn("profiles", kwargs["json"]["contents"][0]["parts"][0]["text"])


if __name__ == "__main__":
    unittest.main()
