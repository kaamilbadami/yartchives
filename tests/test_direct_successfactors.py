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

    def test_fetch_source_passes_accept_header(self):
        import requests
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.content = b'<?xml version="1.0" encoding="UTF-8"?><urlset><url><loc>https://careers.example.com/job/Risk-&-Compliance/1/</loc></url></urlset>'

        mock_client = mock.Mock()
        mock_client.get.return_value = mock_response

        source = {"key": "test", "name": "test", "company": "test", "employer_id": "test", "homepage": "test", "sitemap_url": "https://example.com/sitemap.xml"}
        mod.fetch_source(mock_client, source, mock.Mock())

        mock_client.get.assert_any_call(
            "https://example.com/sitemap.xml",
            headers={"User-Agent": mock.ANY, "Accept": "*/*"},
            timeout=mock.ANY,
        )

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




    def test_fetch_source_raises_structural_error_on_422(self):
        import requests
        mock_response = mock.Mock()
        mock_response.status_code = 422
        mock_response.raise_for_status.side_effect = requests.RequestException(response=mock_response)

        mock_client = mock.Mock()
        mock_client.get.return_value = mock_response

        with self.assertRaises(mod.StructuralSourceError) as context:
            mod.fetch_source(mock_client, {"sitemap_url": "mock://url"}, mock.Mock())

        self.assertEqual(context.exception.status_codes, (422,))


    def test_successfactors_source_returns_none_when_retired(self):
        employer = {
            "id": "dummy-retired-employer",
            "careers_url": "https://jobs.dummy.com",
            "provider": {"family": "successfactors", "status": "resolved"},
            "careers_resolution": {"status": "resolved"},
            "seed_metadata": {
                "provider-lifecycle-overrides": {
                    "provider_lifecycle": {
                        "family": "successfactors",
                        "status": "retired",
                    }
                }
            }
        }
        self.assertIsNone(mod._successfactors_source(employer))

    def test_successfactors_source_returns_none_when_sso_without_fallback(self):
        employer = {
            "id": "aflac",
            "name": "Aflac",
            "careers_url": "https://career4.successfactors.com/career?company=aflac",
            "provider": {"family": "successfactors", "status": "resolved"},
            "careers_resolution": {
                "status": "resolved",
                "evidence": [
                    {
                        "type": "seed",
                        "seed_key": "state-of-ats-2026-verified-hosts",
                        "domain_hint": "career4.successfactors.com/career?company=aflac",
                        "ats_system": "SuccessFactors",
                        "source_url": "https://withresumeai.com/ats-checker/aflac"
                    }
                ]
            }
        }
        self.assertIsNone(mod._successfactors_source(employer))

    def test_successfactors_source_falls_back_from_sso_domain(self):
        employer = {
            "id": "halliburton",
            "name": "Halliburton",
            "careers_url": "https://career4.successfactors.com/career?company=halliburton",
            "provider": {"family": "successfactors", "status": "resolved"},
            "careers_resolution": {
                "status": "resolved",
                "evidence": [
                    {
                        "type": "http",
                        "status": 200,
                        "final_url": "https://gxo.com/careers/",
                        "score": 14,
                        "signals": ["careers path"]
                    },
                    {
                        "type": "http",
                        "status": 200,
                        "final_url": "https://jobs.halliburton.com/",
                        "score": 9,
                        "signals": ["successfactors provider fingerprint"]
                    }
                ]
            }
        }
        source = mod._successfactors_source(employer)
        self.assertIsNotNone(source)
        self.assertEqual(source["homepage"], "https://jobs.halliburton.com")
        self.assertEqual(source["sitemap_url"], "https://jobs.halliburton.com/sitemap.xml")




    def test_fetch_source_escapes_ampersands_before_parsing(self):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.content = b'<?xml version="1.0" encoding="UTF-8"?><urlset><url><loc>https://careers.example.com/job/Risk-&-Compliance/1/</loc></url></urlset>'

        mock_client = mock.Mock()
        mock_client.get.return_value = mock_response

        # This should not raise a StructuralSourceError from XML parsing
        jobs = mod.fetch_source(mock_client, {"key": "test", "name": "test", "company": "test", "employer_id": "test", "homepage": "test", "sitemap_url": "mock://url"}, mock.Mock())
        self.assertEqual(jobs, [])

    def test_fetch_source_strips_leading_characters_before_xml(self):
        import requests
        mock_response = mock.Mock()
        mock_response.status_code = 200
        # Simulated payload with a leading BOM/invalid byte before the XML root
        mock_response.content = b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/job/1</loc></url></urlset>'

        mock_job_response = mock.Mock()
        mock_job_response.status_code = 200
        mock_job_response.text = '<html></html>'

        mock_client = mock.Mock()
        # Return mock_response for the sitemap and mock_job_response for subsequent requests
        mock_client.get.side_effect = [mock_response, mock_job_response, mock_job_response]

        # Should not raise StructuralSourceError and should return 0 jobs since there's no matches
        jobs = mod.fetch_source(
            mock_client,
            {"key": "test", "name": "test", "company": "test", "employer_id": "test", "homepage": "test", "sitemap_url": "mock://url"},
            mock.Mock()
        )
        self.assertEqual(jobs, [])

    def test_fetch_source_raises_structural_error_on_xml_parse_failure(self):
        import requests
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.content = b'{"error": "not found"}'

        mock_client = mock.Mock()
        mock_client.get.return_value = mock_response

        with self.assertRaises(mod.StructuralSourceError) as context:
            mod.fetch_source(mock_client, {"key": "test", "name": "test", "company": "test", "employer_id": "test", "homepage": "test", "sitemap_url": "mock://url"}, mock.Mock())

        self.assertEqual(context.exception.status_codes, (406,))
        self.assertIn("sitemap XML parse failed", str(context.exception))

if __name__ == "__main__":
    unittest.main()
