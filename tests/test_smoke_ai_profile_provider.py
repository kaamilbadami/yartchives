import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "smoke_ai_profile_provider.py"
spec = importlib.util.spec_from_file_location("smoke_ai_profile_provider", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class SmokeAiProfileProviderTests(unittest.TestCase):
    def test_missing_configuration_fails_before_network(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as exc:
                mod.main()
        self.assertIn("AZURE_OPENAI_API_KEY", str(exc.exception))
        self.assertIn("AZURE_OPENAI_ENDPOINT", str(exc.exception))
        self.assertIn("AZURE_OPENAI_DEPLOYMENT", str(exc.exception))

    @mock.patch.object(mod, "AzureOpenAIProfileClassifier")
    def test_valid_structured_classification_succeeds(self, classifier_cls):
        classifier = mock.Mock()
        classifier.name = "azure-openai"
        classifier.model = "gpt-5-mini"
        classifier.classify_many.return_value = [
            mock.Mock(
                classification=mock.Mock(
                    labels=("cs",),
                    confidence=0.99,
                    evidence=("software engineering",),
                )
            )
        ]
        classifier_cls.return_value = classifier

        env = {
            "AZURE_OPENAI_API_KEY": "secret",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/openai/v1",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-5-mini",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(mod.main(), 0)

        classifier_cls.assert_called_once_with(
            api_key="secret",
            endpoint="https://example.openai.azure.com/openai/v1",
            deployment="gpt-5-mini",
            timeout=45,
            batch_size=1,
        )
        classifier.classify_many.assert_called_once_with([mod.SMOKE_JOB])


if __name__ == "__main__":
    unittest.main()
