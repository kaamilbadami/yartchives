import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_feed.py"
spec = importlib.util.spec_from_file_location("build_feed", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BuildFeedTests(unittest.TestCase):
    def test_state_extraction_is_exact(self):
        self.assertEqual(mod.extract_states("Acton, Massachusetts"), ["MA"])
        self.assertIn("CT", mod.extract_states("Danbury, CT, US"))
        self.assertNotIn("CT", mod.extract_states("Acton, Massachusetts"))

    def test_relative_minutes(self):
        ref = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
        parsed = mod.parse_relative_date("12m", ref)
        self.assertEqual(parsed, datetime(2026, 9, 16, 11, 48, tzinfo=timezone.utc))

    def test_canonical_url_removes_tracking(self):
        url = "https://example.com/jobs/123?utm_source=x&foo=bar&ref=abc"
        self.assertEqual(mod.canonical_url(url), "https://example.com/jobs/123?foo=bar")


if __name__ == "__main__":
    unittest.main()
