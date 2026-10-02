import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("direct_successfactors", SCRIPT_DIR / "direct_successfactors.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DirectSuccessFactorsTests(unittest.TestCase):
    def test_enrich_invalidates_resolution_on_structural_error(self):
        employer = {
            "id": "capgemini",
            "name": "Capgemini",
            "careers_url": "https://careers.capgemini.com",
            "provider": {"family": "successfactors", "status": "resolved"},
            "careers_resolution": {"status": "resolved", "resolved_at": "2026-09-17T19:00:00Z"},
        }
        universe = {"employers": [employer]}

        doc = {}
        old_doc = {}

        def fetch_mock(*args, **kwargs):
            raise mod.StructuralSourceError("mock error", [406])

        with mock.patch.object(mod, "fetch_source", side_effect=fetch_mock):
            with mock.patch.object(mod, "invalidate_resolution") as invalidate_mock:
                doc = mod.enrich(doc, old_doc, universe, mock.Mock(), datetime(2026, 9, 17, tzinfo=timezone.utc))

        invalidate_mock.assert_called_once_with(
            employer, "StructuralSourceError: mock error"
        )
        self.assertEqual(doc["sources"]["auto-successfactors-capgemini"]["status"], "quarantined")


    def test_enrich_invalidates_resolution_on_endpoint_retired(self):
        employer = {
            "id": "capgemini",
            "name": "Capgemini",
            "careers_url": "https://careers.capgemini.com",
            "provider": {"family": "successfactors", "status": "resolved"},
            "careers_resolution": {"status": "resolved", "resolved_at": "2026-09-17T19:00:00Z"},
        }
        universe = {"employers": [employer]}

        doc = {}
        old_doc = {}

        def fetch_mock(*args, **kwargs):
            raise mod.EndpointRetiredError("mock retired error")

        with mock.patch.object(mod, "fetch_source", side_effect=fetch_mock):
            with mock.patch.object(mod, "invalidate_resolution") as invalidate_mock:
                doc = mod.enrich(doc, old_doc, universe, mock.Mock(), datetime(2026, 9, 17, tzinfo=timezone.utc))

        invalidate_mock.assert_called_once_with(
            employer, "EndpointRetiredError: mock retired error"
        )
        self.assertEqual(doc["sources"]["auto-successfactors-capgemini"]["status"], "retired")

    def test_discover_sources_skips_retired_provider_override(self):
        universe = {
            "employers": [{
                "id": "american-airlines-group",
                "name": "American Airlines Group",
                "careers_url": "https://jobs.aa.com",
                "provider": {"family": "successfactors", "status": "resolved"},
                "careers_resolution": {"status": "resolved"},
                "seed_metadata": {
                    "provider-lifecycle-overrides": {
                        "provider_lifecycle": {
                            "family": "successfactors",
                            "status": "retired",
                        }
                    }
                },
            }]
        }
        self.assertEqual(mod.discover_sources(universe), [])

    def test_fetch_source_raises_endpoint_retired_on_404(self):
        import requests
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.RequestException(response=mock_response)

        mock_client = mock.Mock()
        mock_client.get.return_value = mock_response

        with self.assertRaises(mod.EndpointRetiredError):
            mod.fetch_source(mock_client, {"sitemap_url": "mock://url"}, mock.Mock())

    def test_fetch_source_raises_structural_error_on_403(self):
        import requests
        mock_response = mock.Mock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = requests.RequestException(response=mock_response)

        mock_client = mock.Mock()
        mock_client.get.return_value = mock_response

        with self.assertRaises(mod.StructuralSourceError) as context:
            mod.fetch_source(mock_client, {"sitemap_url": "mock://url"}, mock.Mock())

        self.assertEqual(context.exception.status_codes, (403,))

if __name__ == "__main__":
    unittest.main()
