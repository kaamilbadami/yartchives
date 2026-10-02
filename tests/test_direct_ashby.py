import json
import unittest
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Make scripts module available
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.direct_ashby as ashby
from scripts.direct_ashby import (
    EndpointRetiredError,
    StructuralSourceError,
    discover_sources,
    fetch_source,
    job_from_item,
)

class TestDirectAshby(unittest.TestCase):
    def test_discover_sources_from_provider(self):
        universe = {
            "employers": [
                {
                    "id": "e1",
                    "name": "Employer 1",
                    "provider": {"status": "resolved", "family": "ashby"},
                    "domain_hints": ["jobs.ashbyhq.com/emp1", "other.com"],
                },
                {
                    "id": "e2",
                    "name": "Employer 2",
                    "provider": {"status": "resolved", "family": "greenhouse"},
                    "domain_hints": ["jobs.ashbyhq.com/emp2"],
                },
            ]
        }
        sources = discover_sources(universe)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["ashby_board"], "emp1")
        self.assertEqual(sources[0]["key"], "auto-ashby-emp1")

    def test_discover_sources_from_seed_metadata(self):
        universe = {
            "employers": [
                {
                    "id": "e3",
                    "name": "Employer 3",
                    "provider": {},
                    "seed_metadata": {
                        "some-seed": {
                            "apply_host": "jobs.ashbyhq.com",
                            "upstream_slug": "emp3",
                        }
                    },
                },
            ]
        }
        sources = discover_sources(universe)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["ashby_board"], "emp3")

    def test_job_from_item_valid(self):
        source = {"ashby_board": "emp", "company": "Emp", "key": "k", "name": "n", "homepage": "h"}
        item = {
            "id": "uuid1",
            "title": "Software Engineer Intern",
            "location": "San Francisco, CA",
            "jobUrl": "https://jobs.ashbyhq.com/emp/uuid1",
            "publishedAt": "2024-03-27T17:41:00.000Z",
        }
        job = job_from_item(source, item)
        self.assertIsNotNone(job)
        self.assertEqual(job["title"], "Software Engineer Intern")
        self.assertEqual(job["location"], "San Francisco, CA")
        self.assertEqual(job["ashby_job_id"], "uuid1")
        self.assertTrue(job["direct_employer"])

    def test_job_from_item_not_cs(self):
        source = {"ashby_board": "emp", "company": "Emp", "key": "k", "name": "n", "homepage": "h"}
        item = {
            "id": "uuid1",
            "title": "Sales Intern",
            "location": "San Francisco, CA",
        }
        self.assertIsNone(job_from_item(source, item))

    def test_job_from_item_not_us(self):
        source = {"ashby_board": "emp", "company": "Emp", "key": "k", "name": "n", "homepage": "h"}
        item = {
            "id": "uuid1",
            "title": "Software Engineer Intern",
            "location": "London, UK",
        }
        self.assertIsNone(job_from_item(source, item))

    def test_fetch_source_success(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {
                    "id": "uuid1",
                    "title": "Software Engineer Intern",
                    "location": "Remote US",
                }
            ]
        }
        mock_session.get.return_value = mock_response

        source = {"ashby_board": "emp", "company": "Emp", "key": "k", "name": "n", "homepage": "h", "api_url": "mock://api"}
        jobs = fetch_source(mock_session, source)
        self.assertEqual(len(jobs), 1)

    def test_fetch_source_404_raises_retired(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_session.get.return_value = mock_response

        source = {"api_url": "mock://api"}
        with self.assertRaises(EndpointRetiredError):
            fetch_source(mock_session, source)

    def test_fetch_source_500_raises_structural(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_session.get.return_value = mock_response

        source = {"api_url": "mock://api"}
        with self.assertRaises(StructuralSourceError):
            fetch_source(mock_session, source)

if __name__ == "__main__":
    unittest.main()
