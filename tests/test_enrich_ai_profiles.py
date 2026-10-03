import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "enrich_ai_profiles.py"
spec = importlib.util.spec_from_file_location("enrich_ai_profiles", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class FakeProvider:
    name = "fake"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def classify_many(self, jobs):
        self.calls.append([job.get("id") for job in jobs])
        count = len(jobs)
        selected = self.outcomes[:count]
        self.outcomes = self.outcomes[count:]
        return selected


def outcome(labels, confidence, evidence=("role evidence",)):
    return mod.ai.ClassificationOutcome(
        classification=mod.ai.Classification(tuple(labels), confidence, tuple(evidence))
    )


class EnrichAiProfilesTests(unittest.TestCase):
    def test_only_general_jobs_are_eligible(self):
        doc = {
            "jobs": [
                {"id": "general", "title": "Analog Design Intern", "profiles": ["general"]},
                {"id": "cs", "title": "Software Intern", "profiles": ["cs"]},
            ]
        }
        provider = FakeProvider([outcome(("engineering",), 0.99)])
        stats = mod.apply_ai_fallback(doc, provider, model="test")

        self.assertEqual(doc["jobs"][0]["profiles"], ["engineering"])
        self.assertEqual(doc["jobs"][1]["profiles"], ["cs"])
        self.assertEqual(provider.calls, [["general"]])
        self.assertEqual(stats["accepted"], 1)

    def test_low_confidence_prediction_keeps_general(self):
        doc = {"jobs": [{"id": "a", "title": "Technology Intern", "profiles": ["general"]}]}
        provider = FakeProvider([outcome(("cs",), 0.94)])
        stats = mod.apply_ai_fallback(doc, provider, model="test", threshold=0.95)

        self.assertEqual(doc["jobs"][0]["profiles"], ["general"])
        self.assertNotIn(mod.CLASSIFICATION_FIELD, doc["jobs"][0])
        self.assertEqual(stats["accepted"], 0)
        self.assertEqual(stats["kept_general"], 1)

    def test_general_prediction_keeps_general_even_at_high_confidence(self):
        doc = {"jobs": [{"id": "a", "title": "Marketing Intern", "profiles": ["general"]}]}
        provider = FakeProvider([outcome(("general",), 0.99)])
        mod.apply_ai_fallback(doc, provider, model="test")

        self.assertEqual(doc["jobs"][0]["profiles"], ["general"])
        self.assertNotIn(mod.CLASSIFICATION_FIELD, doc["jobs"][0])

    def test_accepted_prediction_records_provenance(self):
        job = {"id": "a", "company": "Example", "title": "Analog Design Intern", "profiles": ["general"]}
        doc = {"jobs": [job]}
        provider = FakeProvider([outcome(("engineering",), 0.98, ("Analog Design Intern",))])
        mod.apply_ai_fallback(doc, provider, model="gemini-test")

        metadata = job[mod.CLASSIFICATION_FIELD]
        self.assertEqual(metadata["method"], "ai-fallback")
        self.assertEqual(metadata["provider"], "fake")
        self.assertEqual(metadata["model"], "gemini-test")
        self.assertEqual(metadata["confidence"], 0.98)
        self.assertEqual(metadata["evidence"], ["Analog Design Intern"])
        self.assertEqual(metadata["input_fingerprint"], mod.evidence_fingerprint(job))

    def test_cache_reuse_avoids_model_call_when_evidence_is_unchanged(self):
        current = {
            "id": "a",
            "company": "Example",
            "title": "Analog Design Intern",
            "profiles": ["general"],
        }
        fingerprint = mod.evidence_fingerprint(current)
        cached = {
            "id": "a",
            "company": "Example",
            "title": "Analog Design Intern",
            "profiles": ["engineering"],
            mod.CLASSIFICATION_FIELD: {
                "method": "ai-fallback",
                "provider": "gemini",
                "model": "gemini-test",
                "confidence": 0.98,
                "evidence": ["Analog Design Intern"],
                "input_fingerprint": fingerprint,
            },
        }
        provider = FakeProvider([])
        doc = {"jobs": [current]}
        stats = mod.apply_ai_fallback(
            doc,
            provider,
            model="gemini-test",
            cache_doc={"jobs": [cached]},
        )

        self.assertEqual(current["profiles"], ["engineering"])
        self.assertEqual(provider.calls, [])
        self.assertEqual(stats["cache_reused"], 1)
        self.assertEqual(stats["model_attempted"], 0)

    def test_changed_evidence_invalidates_cache(self):
        old = {
            "id": "a",
            "company": "Example",
            "title": "Analog Design Intern",
            "profiles": ["engineering"],
        }
        old[mod.CLASSIFICATION_FIELD] = {
            "method": "ai-fallback",
            "provider": "gemini",
            "model": "gemini-test",
            "confidence": 0.99,
            "evidence": ["Analog Design Intern"],
            "input_fingerprint": mod.evidence_fingerprint({
                "id": "a",
                "company": "Example",
                "title": "Analog Design Intern",
                "profiles": ["general"],
            }),
        }
        current = {
            "id": "a",
            "company": "Example",
            "title": "Brand Design Intern",
            "profiles": ["general"],
        }
        provider = FakeProvider([outcome(("general",), 0.99)])
        stats = mod.apply_ai_fallback(
            {"jobs": [current]},
            provider,
            model="gemini-test",
            cache_doc={"jobs": [old]},
        )

        self.assertEqual(provider.calls, [["a"]])
        self.assertEqual(current["profiles"], ["general"])
        self.assertEqual(stats["cache_reused"], 0)

    def test_request_budget_defers_remaining_general_jobs(self):
        jobs = [
            {"id": f"job-{index}", "title": "Unknown Intern", "profiles": ["general"]}
            for index in range(25)
        ]
        provider = FakeProvider([
            outcome(("general",), 0.99)
            for _ in range(20)
        ])
        stats = mod.apply_ai_fallback(
            {"jobs": jobs},
            provider,
            model="test",
            request_batch_size=20,
            max_batches=1,
        )

        self.assertEqual(provider.calls, [[f"job-{index}" for index in range(20)]])
        self.assertEqual(stats["model_attempted"], 20)
        self.assertEqual(stats["budget_deferred"], 5)

    def test_failed_batch_is_fail_open(self):
        class FailingProvider:
            name = "fake"
            def classify_many(self, jobs):
                raise RuntimeError("temporary outage")

        doc = {"jobs": [{"id": "a", "title": "Unknown Intern", "profiles": ["general"]}]}
        stats = mod.apply_ai_fallback(doc, FailingProvider(), model="test")

        self.assertEqual(doc["jobs"][0]["profiles"], ["general"])
        self.assertEqual(stats["failed"], 1)

    def test_main_without_api_key_leaves_file_unchanged(self):
        payload = {"jobs": [{"id": "a", "title": "Unknown Intern", "profiles": ["general"]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            original = json.dumps(payload)
            path.write_text(original, encoding="utf-8")
            old_argv = sys.argv
            env_names = (
                "TEST_MISSING_AI_KEY",
                "TEST_MISSING_AZURE_KEY",
                "TEST_MISSING_AZURE_ENDPOINT",
                "TEST_MISSING_AZURE_DEPLOYMENT",
            )
            old_values = {name: mod.os.environ.pop(name, None) for name in env_names}
            try:
                sys.argv = [
                    str(MODULE_PATH),
                    str(path),
                    "--api-key-env",
                    "TEST_MISSING_AI_KEY",
                    "--azure-api-key-env",
                    "TEST_MISSING_AZURE_KEY",
                    "--azure-endpoint-env",
                    "TEST_MISSING_AZURE_ENDPOINT",
                    "--azure-deployment-env",
                    "TEST_MISSING_AZURE_DEPLOYMENT",
                ]
                self.assertEqual(mod.main(), 0)
            finally:
                sys.argv = old_argv
                for name, value in old_values.items():
                    if value is not None:
                        mod.os.environ[name] = value
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
