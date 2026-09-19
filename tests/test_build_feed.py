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

    def test_base_job_records_posting_date_provenance(self):
        ref = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        source = {
            "key": "direct-example",
            "name": "Example",
            "url": "https://example.com/jobs",
            "posted_date_provenance": "authoritative_employer",
        }
        job = mod.base_job(
            company="Example",
            title="Software Intern",
            location="Remote",
            url="https://example.com/jobs/1",
            posted_raw="2026-09-17",
            posted_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
            source=source,
        )
        self.assertEqual(job["posted_date_source_key"], "direct-example")
        self.assertEqual(job["posted_date_provenance"], "authoritative_employer")
        self.assertEqual(job["posted_date_observations"][0]["posted_at"], "2026-09-17T00:00:00Z")

    def test_merge_preserves_authoritative_date_over_newer_aggregator_date(self):
        target = {
            "source_keys": ["direct-example"],
            "source_names": ["Example"],
            "source_urls": ["https://example.com"],
            "profiles": ["cs"],
            "states": ["CT"],
            "posted_at": "2026-09-01T00:00:00Z",
            "posted_raw": "2026-09-01",
            "posted_date_source_key": "direct-example",
            "posted_date_source_name": "Example",
            "posted_date_provenance": "authoritative_employer",
            "posted_date_observations": [{
                "source_key": "direct-example",
                "source_name": "Example",
                "posted_raw": "2026-09-01",
                "posted_at": "2026-09-01T00:00:00Z",
                "provenance": "authoritative_employer",
            }],
        }
        incoming = {
            "source_key": "aggregator",
            "source_name": "Aggregator",
            "source_url": "https://aggregator.example",
            "profiles": ["cs"],
            "states": ["CT"],
            "posted_at": "2026-09-17T00:00:00Z",
            "posted_raw": "1d",
            "posted_date_source_key": "aggregator",
            "posted_date_source_name": "Aggregator",
            "posted_date_provenance": "aggregator",
            "posted_date_observations": [{
                "source_key": "aggregator",
                "source_name": "Aggregator",
                "posted_raw": "1d",
                "posted_at": "2026-09-17T00:00:00Z",
                "provenance": "aggregator",
            }],
        }
        mod.merge_job(target, incoming)
        # Authoritative employer date is preserved over newer aggregator date
        self.assertEqual(target["posted_at"], "2026-09-01T00:00:00Z")
        self.assertEqual(target["posted_date_source_key"], "direct-example")
        self.assertEqual(target["posted_date_provenance"], "authoritative_employer")
        self.assertEqual(len(target["posted_date_observations"]), 2)

    def test_merge_upgrades_aggregator_date_to_authoritative_date(self):
        target = {
            "source_keys": ["aggregator"],
            "source_names": ["Aggregator"],
            "source_urls": ["https://aggregator.example"],
            "profiles": ["cs"],
            "states": ["CT"],
            "posted_at": "2026-09-17T00:00:00Z",
            "posted_raw": "1d",
            "posted_date_source_key": "aggregator",
            "posted_date_source_name": "Aggregator",
            "posted_date_provenance": "aggregator",
            "posted_date_observations": [{
                "source_key": "aggregator",
                "source_name": "Aggregator",
                "posted_raw": "1d",
                "posted_at": "2026-09-17T00:00:00Z",
                "provenance": "aggregator",
            }],
        }
        incoming = {
            "source_key": "direct-example",
            "source_name": "Example",
            "source_url": "https://example.com",
            "profiles": ["cs"],
            "states": ["CT"],
            "posted_at": "2026-09-01T00:00:00Z",
            "posted_raw": "2026-09-01",
            "posted_date_source_key": "direct-example",
            "posted_date_source_name": "Example",
            "posted_date_provenance": "authoritative_employer",
            "posted_date_observations": [{
                "source_key": "direct-example",
                "source_name": "Example",
                "posted_raw": "2026-09-01",
                "posted_at": "2026-09-01T00:00:00Z",
                "provenance": "authoritative_employer",
            }],
        }
        mod.merge_job(target, incoming)
        # Incoming authoritative employer date upgrades target even if older than aggregator timestamp
        self.assertEqual(target["posted_at"], "2026-09-01T00:00:00Z")
        self.assertEqual(target["posted_date_source_key"], "direct-example")
        self.assertEqual(target["posted_date_provenance"], "authoritative_employer")
        self.assertEqual(len(target["posted_date_observations"]), 2)


    def test_main_does_not_carry_forward_confirmed_dead_listings_during_failure(self):
        # Write mock sources.json and listings.json
        import json
        from unittest.mock import patch
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sources_path = tmp_path / "sources.json"
            output_path = tmp_path / "listings.json"

            sources_path.write_text(json.dumps([
                {
                    "key": "failing_source",
                    "name": "Failing Source",
                    "kind": "markdown",
                    "url": "http://invalid.local"
                }
            ]))

            output_path.write_text(json.dumps({
            "jobs": [
                {
                    "id": "1",
                    "company": "Valid Company",
                    "title": "Software Engineer",
                    "location": "Remote",
                    "url": "https://example.com/valid",
                    "source_keys": ["failing_source"],
                    "link_status": "ok"
                },
                {
                    "id": "2",
                    "company": "Dead Company",
                    "title": "Software Engineer",
                    "location": "Remote",
                    "url": "https://example.com/dead",
                    "source_keys": ["failing_source"],
                    "link_status": "dead"
                }
                ]
            }))

            with patch.object(mod, 'SOURCES_PATH', sources_path), \
                 patch.object(mod, 'OUTPUT_PATH', output_path):
                # Setting USAJOBS_API_KEY to empty to fail or skip gracefully
                os.environ["USAJOBS_API_KEY"] = ""
                os.environ["USAJOBS_EMAIL"] = ""
                mod.main()

                result = json.loads(output_path.read_text())
                jobs = result.get("jobs", [])

                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0]["company"], "Valid Company")

if __name__ == "__main__":
    unittest.main()
