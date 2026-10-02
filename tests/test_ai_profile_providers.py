import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "ai_profile_providers.py"
spec = importlib.util.spec_from_file_location("ai_profile_providers", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class AiProfileProviderTests(unittest.TestCase):
    @mock.patch.object(mod.requests, "post")
    def test_azure_provider_uses_v1_structured_outputs(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.headers = {}
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "results": [{
                            "key": "0",
                            "labels": ["cs"],
                            "confidence": 0.98,
                            "evidence": ["software engineering"],
                        }]
                    })
                }
            }]
        }
        post.return_value = response

        provider = mod.AzureOpenAIProfileClassifier(
            api_key="secret",
            endpoint="https://example-resource.openai.azure.com",
            deployment="gpt-5-mini",
            timeout=1,
        )
        outcomes = provider.classify_many([
            {"company": "Example", "title": "Software Engineering Intern"}
        ])

        self.assertEqual(outcomes[0].classification.labels, ("cs",))
        _, kwargs = post.call_args
        self.assertEqual(
            post.call_args.args[0],
            "https://example-resource.openai.azure.com/openai/v1/chat/completions",
        )
        self.assertEqual(kwargs["headers"]["api-key"], "secret")
        self.assertEqual(kwargs["json"]["model"], "gpt-5-mini")
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_schema")
        self.assertTrue(kwargs["json"]["response_format"]["json_schema"]["strict"])

    def test_failover_uses_next_provider_after_primary_error(self):
        class Broken:
            name = "broken"
            model = "broken-model"
            def classify_many(self, jobs):
                raise RuntimeError("quota exhausted")

        class Healthy:
            name = "healthy"
            model = "healthy-model"
            def classify_many(self, jobs):
                return [
                    mod.ai.ClassificationOutcome(
                        classification=mod.ai.Classification(("engineering",), 0.99, ("hardware",))
                    )
                    for _ in jobs
                ]

        provider = mod.FailoverProfileClassifier([Broken(), Healthy()])
        outcomes = provider.classify_many([{"title": "Hardware Intern"}])

        self.assertEqual(outcomes[0].classification.labels, ("engineering",))
        self.assertEqual(provider.last_provider_name, "healthy")
        self.assertEqual(provider.last_model, "healthy-model")
        self.assertEqual(provider.cache_models, {"broken-model", "healthy-model"})


if __name__ == "__main__":
    unittest.main()
