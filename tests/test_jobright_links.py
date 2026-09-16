import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "jobright_links.py"
spec = importlib.util.spec_from_file_location("jobright_links", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class JobrightLinksTests(unittest.TestCase):
    def test_jobright_id(self):
        self.assertEqual(
            mod.jobright_id("https://jobright.ai/jobs/info/6aa9c1db09ae03adcacdef24?utm_source=git"),
            "6aa9c1db09ae03adcacdef24",
        )
        self.assertEqual(mod.jobright_id("https://example.com/jobs/info/x"), "")

    def test_clean_title_strips_markdown_bold(self):
        self.assertEqual(mod.clean_title("**Policy Research Intern**"), "Policy Research Intern")

    def test_exact_id_prefers_original_url(self):
        rows = [{
            "jobResult": {
                "jobId": "abc123",
                "originalUrl": "https://example.com/careers/jobs/123",
                "applyLink": "https://other.example.com/jobs/123",
            }
        }]
        self.assertEqual(
            mod.direct_from_exact_id(rows, "abc123"),
            "https://example.com/careers/jobs/123",
        )

    def test_wrong_id_is_rejected(self):
        rows = [{
            "jobResult": {
                "jobId": "other",
                "originalUrl": "https://example.com/careers/jobs/123",
            }
        }]
        self.assertIsNone(mod.direct_from_exact_id(rows, "abc123"))

    def test_duplicate_exact_id_is_rejected(self):
        rows = [
            {"jobResult": {"jobId": "abc123", "originalUrl": "https://one.example.com/jobs/1"}},
            {"jobResult": {"jobId": "abc123", "originalUrl": "https://two.example.com/jobs/2"}},
        ]
        self.assertIsNone(mod.direct_from_exact_id(rows, "abc123"))

    def test_aggregator_url_is_not_promoted(self):
        rows = [{
            "jobResult": {
                "jobId": "abc123",
                "originalUrl": "https://jobright.ai/jobs/info/abc123",
            }
        }]
        self.assertIsNone(mod.direct_from_exact_id(rows, "abc123"))


if __name__ == "__main__":
    unittest.main()
