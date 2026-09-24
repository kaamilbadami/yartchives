import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "provider_fingerprint.py"
spec = importlib.util.spec_from_file_location("provider_fingerprint", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ProviderFingerprintTests(unittest.TestCase):
    def test_known_provider_hosts_are_classified(self):
        cases = {
            "https://acme.wd5.myworkdayjobs.com/en-US/External": "workday",
            "https://boards.greenhouse.io/acme": "greenhouse",
            "https://careers-acme.icims.com/jobs/search": "icims",
            "https://jobs.ashbyhq.com/acme": "ashby",
            "https://efds.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX": "oracle",
            "https://career5.successfactors.eu/career?company=acme": "successfactors",
            "https://career55.sapsf.eu/career?company=acme": "successfactors",
            "https://career50.sapsf.com/career?company=acme": "successfactors",
            "https://jobs.smartrecruiters.com/Acme": "smartrecruiters",
            "https://jobs.lever.co/acme": "lever",
            "https://acme.eightfold.ai/careers": "eightfold",
            "https://acme.avature.net/careers": "avature",
            "https://sjobs.brassring.com/TGnewUI/Search/Home/Home": "brassring",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                result = mod.fingerprint_provider(url)
                self.assertEqual(result["family"], expected)
                self.assertEqual(result["status"], "resolved")

    def test_branded_company_url_can_be_resolved_from_page_marker(self):
        result = mod.fingerprint_provider(
            "https://careers.example.com/jobs",
            html='<script src="https://jobs.ashbyhq.com/example/embed.js"></script>',
        )
        self.assertEqual(result["family"], "ashby")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["host"], "careers.example.com")

    def test_redirect_target_is_persisted_as_careers_url(self):
        universe = {
            "schema_version": 1,
            "seed_sets": [{"key": "regional", "kind": "benchmark"}],
            "employers": [{"id": "lockheed-martin", "name": "Lockheed Martin", "aliases": [], "seed_sets": ["regional"]}],
        }
        result = mod.apply_observations(
            universe,
            [{
                "employer_id": "lockheed-martin",
                "url": "https://www.example.com/careers",
                "final_url": "https://example.wd5.myworkdayjobs.com/en-US/External",
            }],
        )
        employer = result["employers"][0]
        self.assertEqual(employer["careers_url"], "https://example.wd5.myworkdayjobs.com/en-US/External")
        self.assertEqual(employer["provider"]["family"], "workday")

    def test_unknown_provider_is_explicit_not_guessed(self):
        result = mod.fingerprint_provider("https://careers.example.com/jobs")
        self.assertEqual(result["family"], "custom_unknown")
        self.assertEqual(result["status"], "unresolved")

        result_non_matching = mod.fingerprint_provider("https://example.com/not-sapsf-just-random")
        self.assertEqual(result_non_matching["family"], "custom_unknown")
        self.assertEqual(result_non_matching["status"], "unresolved")

    def test_multiple_provider_markers_are_ambiguous(self):
        result = mod.fingerprint_provider(
            "https://careers.example.com",
            html="jobs.lever.co and boards.greenhouse.io",
        )
        self.assertEqual(result["family"], "unknown")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidates"], ["greenhouse", "lever"])

    def test_rejects_unknown_or_duplicate_employer_observations(self):
        universe = {
            "schema_version": 1,
            "seed_sets": [],
            "employers": [{"id": "acme", "name": "Acme", "aliases": [], "seed_sets": []}],
        }
        with self.assertRaises(ValueError):
            mod.apply_observations(universe, [{"employer_id": "missing", "url": "https://jobs.lever.co/missing"}])
        with self.assertRaises(ValueError):
            mod.apply_observations(universe, [
                {"employer_id": "acme", "url": "https://jobs.lever.co/acme"},
                {"employer_id": "acme", "url": "https://boards.greenhouse.io/acme"},
            ])


if __name__ == "__main__":
    unittest.main()
