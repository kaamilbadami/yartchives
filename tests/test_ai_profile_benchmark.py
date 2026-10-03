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

    def test_prompt_preserves_yartchives_taxonomy_boundaries(self):
        prompt = mod.SYSTEM_INSTRUCTION
        self.assertIn("Software engineering is cs, not engineering", prompt)
        self.assertIn("Firmware, embedded systems", prompt)
        self.assertIn("Avionics, aerospace, mechanical/manufacturing, and electrical/hardware roles all receive engineering", prompt)
        self.assertIn("Generic \"data\", \"technology\", or \"analytics\" wording alone does not add cs", prompt)
        self.assertIn("Finance/econ roles do not receive cs", prompt)
        self.assertIn("Generic physical-engineering titles", prompt)
        self.assertIn("Mechanical/manufacturing, aerospace, and electrical/hardware distinctions are discipline metadata", prompt)
        self.assertIn("explicitly says medical, clinical, healthcare", prompt)
        self.assertIn("not separate career-area labels", prompt)
        self.assertIn("AI in business strategy", prompt)
        self.assertIn("general is mutually exclusive", prompt)
        self.assertIn("Data analyst", prompt)
        self.assertIn("Prefer coverage over omission", prompt)
        self.assertIn("Extra plausible supported labels are less harmful", prompt)
        self.assertIn("every label still needs visible role evidence", prompt)

    def test_validate_classification_accepts_allowed_labels(self):
        result = mod.validate_classification({
            "labels": ["finance-econ", "cs", "cs"],
            "confidence": 0.97,
            "evidence": ["quantitative developer", "software"],
        })
        self.assertEqual(result.labels, ("cs", "finance-econ"))
        self.assertEqual(result.confidence, 0.97)
        self.assertEqual(result.evidence, ("quantitative developer", "software"))

    def test_legacy_engineering_labels_collapse_to_engineering(self):
        self.assertEqual(
            mod.canonicalize_profile_labels(["mechanical", "electrical", "cs"]),
            {"engineering", "cs"},
        )

    def test_validate_classification_rejects_legacy_engineering_discipline_label(self):
        with self.assertRaises(ValueError):
            mod.validate_classification({
                "labels": ["mechanical"],
                "confidence": 0.9,
                "evidence": ["manufacturing"],
            })

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
        self.assertAlmostEqual(score["micro_f2"], 5 / 7)
        self.assertEqual(score["coverage_accuracy"], 0.5)
        self.assertEqual(score["missed_label_count"], 1)
        self.assertEqual(score["extra_label_count"], 0)
        self.assertEqual(score["underclassified_cases"], 1)
        self.assertEqual(score["overclassified_only_cases"], 0)
        self.assertEqual(score["mixed_error_cases"], 0)

    def test_score_gold_treats_supported_overclassification_as_coverage(self):
        score = mod.score_gold(
            [{"cs"}, {"engineering"}],
            [{"cs", "tech-business"}, {"engineering", "cs"}],
        )
        self.assertEqual(score["exact_set_accuracy"], 0.0)
        self.assertEqual(score["coverage_accuracy"], 1.0)
        self.assertEqual(score["micro_recall"], 1.0)
        self.assertEqual(score["missed_label_count"], 0)
        self.assertEqual(score["extra_label_count"], 2)
        self.assertEqual(score["underclassified_cases"], 0)
        self.assertEqual(score["overclassified_only_cases"], 2)
        self.assertEqual(score["mixed_error_cases"], 0)

    @mock.patch.object(mod.requests, "post")
    def test_gemini_provider_batches_jobs_and_requests_structured_json(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.headers = {}
        response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [
                                {
                                    "key": "0",
                                    "labels": ["cs"],
                                    "confidence": 0.96,
                                    "evidence": ["software development"],
                                },
                                {
                                    "key": "1",
                                    "labels": ["finance-econ"],
                                    "confidence": 0.94,
                                    "evidence": ["quantitative trading"],
                                },
                            ]
                        })
                    }]
                }
            }]
        }
        post.return_value = response

        provider = mod.GeminiProfileClassifier(
            "secret",
            model="gemini-test",
            timeout=1,
            batch_size=20,
        )
        outcomes = provider.classify_many([
            {"company": "Example", "title": "Software Development Intern"},
            {"company": "Example", "title": "Quantitative Trader Intern"},
        ])

        self.assertEqual(
            [outcome.classification.labels for outcome in outcomes],
            [("cs",), ("finance-econ",)],
        )
        self.assertEqual(post.call_count, 1)
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "secret")
        self.assertEqual(
            kwargs["json"]["generationConfig"]["responseMimeType"],
            "application/json",
        )
        self.assertEqual(
            kwargs["json"]["generationConfig"]["responseJsonSchema"],
            mod.BATCH_RESPONSE_SCHEMA,
        )
        self.assertNotIn("responseSchema", kwargs["json"]["generationConfig"])
        prompt = kwargs["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn('"key": "0"', prompt)
        self.assertIn('"key": "1"', prompt)
        self.assertNotIn("profiles", prompt)

    @mock.patch.object(mod.requests, "post")
    def test_classify_many_splits_on_batch_size(self, post):
        def response_for(keys):
            response = mock.Mock()
            response.status_code = 200
            response.headers = {}
            response.json.return_value = {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                "results": [
                                    {
                                        "key": str(i),
                                        "labels": ["general"],
                                        "confidence": 0.8,
                                        "evidence": [],
                                    }
                                    for i in keys
                                ]
                            })
                        }]
                    }
                }]
            }
            return response

        post.side_effect = [response_for(range(2)), response_for(range(1))]
        provider = mod.GeminiProfileClassifier("secret", batch_size=2)
        outcomes = provider.classify_many([
            {"title": "A"},
            {"title": "B"},
            {"title": "C"},
        ])
        self.assertEqual(len(outcomes), 3)
        self.assertEqual(post.call_count, 2)


    @mock.patch.object(mod.requests, "post")
    def test_invalid_item_is_reported_without_aborting_batch(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.headers = {}
        response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [
                                {
                                    "key": "0",
                                    "labels": ["general", "cs"],
                                    "confidence": 0.91,
                                    "evidence": ["ambiguous"],
                                },
                                {
                                    "key": "1",
                                    "labels": ["finance-econ"],
                                    "confidence": 0.97,
                                    "evidence": ["quantitative trading"],
                                },
                            ]
                        })
                    }]
                }
            }]
        }
        post.return_value = response

        provider = mod.GeminiProfileClassifier("secret", batch_size=20)
        outcomes = provider.classify_many([
            {"title": "AI Strategy Intern"},
            {"title": "Quantitative Trader Intern"},
        ])

        self.assertIsNone(outcomes[0].classification)
        self.assertIn("general cannot be combined", outcomes[0].error)
        self.assertEqual(outcomes[0].raw_labels, ("general", "cs"))
        self.assertEqual(outcomes[1].classification.labels, ("finance-econ",))

    def test_gold_summary_counts_validation_errors_separately(self):
        class FakeProvider:
            name = "fake"
            def classify_many(self, jobs):
                return [
                    mod.ClassificationOutcome(
                        classification=mod.Classification(("cs",), 0.9, ("software",))
                    ),
                    mod.ClassificationOutcome(
                        classification=None,
                        error="general cannot be combined with specialized labels",
                        raw_labels=("general", "cs"),
                    ),
                ]

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold.json"
            path.write_text(json.dumps([
                {"title": "Software Intern", "expected_labels": ["cs"]},
                {"title": "AI Strategy Intern", "expected_labels": ["tech-business"]},
            ]), encoding="utf-8")
            summary, rows = mod.run_gold(FakeProvider(), path)

        self.assertEqual(summary["attempted_cases"], 2)
        self.assertEqual(summary["valid_cases"], 1)
        self.assertEqual(summary["validation_errors"], 1)
        self.assertEqual(summary["exact_set_accuracy"], 1.0)
        self.assertFalse(rows[1]["exact"])
        self.assertIn("error", rows[1])


    def test_rule_reference_excludes_source_key_only_classification(self):
        source_only = {
            "id": "source-only",
            "title": "Marketing Intern",
            "company": "Example",
            "profiles": ["cs"],
            "source_keys": ["ct-example"],
        }
        visible_rule = {
            "id": "visible",
            "title": "Software Engineering Intern",
            "company": "Example",
            "profiles": ["cs"],
            "source_keys": ["anything"],
        }
        candidates = mod.rule_backed_reference_candidates([source_only, visible_rule])
        self.assertEqual([job["id"] for job in candidates], ["visible"])

    def test_rule_reference_excludes_generic_engineering_fallback_only_roles(self):
        generic = {
            "id": "generic-eng",
            "title": "Systems Engineering Intern",
            "company": "Example",
            "profiles": ["engineering"],
            "source_keys": [],
        }
        discipline_backed = {
            "id": "electrical-eng",
            "title": "Electrical Engineering Intern",
            "company": "Example",
            "profiles": ["engineering"],
            "source_keys": [],
        }
        candidates = mod.rule_backed_reference_candidates([generic, discipline_backed])
        self.assertEqual([job["id"] for job in candidates], ["electrical-eng"])

    def test_rule_reference_requires_fresh_recomputation_to_match_stored_labels(self):
        stale = {
            "id": "stale",
            "title": "Software Engineering Intern",
            "company": "Example",
            "profiles": ["finance-econ"],
            "source_keys": [],
        }
        matching = {
            "id": "matching",
            "title": "Financial Analyst Intern",
            "company": "Example",
            "profiles": ["finance-econ"],
            "source_keys": [],
        }
        candidates = mod.rule_backed_reference_candidates([stale, matching])
        self.assertEqual([job["id"] for job in candidates], ["matching"])

    def test_rule_reference_sample_is_deterministic_and_stratified(self):
        jobs = [
            {"id": "cs1", "title": "Software Intern", "profiles": ["cs"], "source_keys": []},
            {"id": "cs2", "title": "Software Developer Intern", "profiles": ["cs"], "source_keys": []},
            {"id": "fin1", "title": "Finance Intern", "profiles": ["finance-econ"], "source_keys": []},
            {"id": "ee1", "title": "Electrical Engineering Intern", "profiles": ["electrical", "engineering"], "source_keys": []},
        ]
        first = mod.stable_rule_reference_sample(jobs, 3)
        second = mod.stable_rule_reference_sample(list(reversed(jobs)), 3)
        self.assertEqual([job["id"] for job in first], [job["id"] for job in second])
        labels = set().union(*(mod.canonicalize_profile_labels(job["profiles"]) for job in first))
        self.assertIn("cs", labels)
        self.assertIn("finance-econ", labels)
        self.assertIn("engineering", labels)
        self.assertNotIn("electrical", labels)

    def test_per_label_metrics_reports_support_precision_and_recall(self):
        metrics = mod.per_label_metrics(
            [{"cs"}, {"finance-econ"}, {"cs", "finance-econ"}],
            [{"cs"}, {"cs"}, {"cs", "finance-econ"}],
        )
        self.assertEqual(metrics["cs"]["support"], 2)
        self.assertAlmostEqual(metrics["cs"]["precision"], 2 / 3)
        self.assertEqual(metrics["cs"]["recall"], 1.0)
        self.assertAlmostEqual(metrics["cs"]["f2"], 10 / 11)
        self.assertEqual(metrics["finance-econ"]["support"], 2)
        self.assertEqual(metrics["finance-econ"]["precision"], 1.0)
        self.assertEqual(metrics["finance-econ"]["recall"], 0.5)

    def test_rule_reference_summary_counts_disagreements_and_invalid_results(self):
        class FakeProvider:
            name = "fake"
            def classify_many(self, jobs):
                return [
                    mod.ClassificationOutcome(
                        classification=mod.Classification(("cs",), 0.95, ("software",))
                    ),
                    mod.ClassificationOutcome(
                        classification=mod.Classification(("tech-business",), 0.9, ("analytics",))
                    ),
                    mod.ClassificationOutcome(
                        classification=None,
                        error="general cannot be combined with specialized labels",
                        raw_labels=("general", "finance-econ"),
                    ),
                ]

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            path.write_text(json.dumps({
                "jobs": [
                    {"id": "a", "company": "A", "title": "Software Intern", "profiles": ["cs"], "source_keys": []},
                    {"id": "b", "company": "B", "title": "Finance Intern", "profiles": ["finance-econ"], "source_keys": []},
                    {"id": "c", "company": "C", "title": "Financial Analyst Intern", "profiles": ["finance-econ"], "source_keys": []},
                ]
            }), encoding="utf-8")
            summary, rows = mod.run_rule_reference(FakeProvider(), path, 3)

        self.assertEqual(summary["sample_size"], 3)
        self.assertEqual(summary["valid_results"], 2)
        self.assertEqual(summary["validation_errors"], 1)
        self.assertEqual(summary["disagreements"], 2)
        self.assertAlmostEqual(summary["agreement_rate_including_invalid"], 1 / 3)
        self.assertEqual(len(rows), 3)

    @mock.patch.object(mod.time, "sleep")
    @mock.patch.object(mod.requests, "post")
    def test_gemini_long_quota_retry_fails_fast_without_sleeping(self, post, sleep):
        response = mock.Mock()
        response.status_code = 429
        response.headers = {}
        response.text = (
            "Quota exceeded for generate_content_free_tier_requests. "
            "Please retry in 9272.0s."
        )
        post.return_value = response

        provider = mod.GeminiProfileClassifier("secret", batch_size=20)
        with self.assertRaises(RuntimeError) as ctx:
            provider.classify_many([{"title": "Unknown Intern"}])

        self.assertIn("quota unavailable", str(ctx.exception))
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_retry_delay_uses_gemini_retry_hint(self):
        response = mock.Mock()
        response.headers = {}
        response.text = "Quota exceeded. Please retry in 25.966648046s."
        self.assertAlmostEqual(mod._retry_delay_seconds(response, 0), 26.966648046)


if __name__ == "__main__":
    unittest.main()
