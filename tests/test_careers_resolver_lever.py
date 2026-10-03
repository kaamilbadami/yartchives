import unittest
import requests
from unittest import mock
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from careers_resolver import resolve_employer

class TestCareersResolverLever(unittest.TestCase):
    @mock.patch("requests.Session.get")
    def test_lever_slug_discovery(self, mock_get):
        entry = {
            "id": "palantir-technologies",
            "name": "Palantir Technologies",
            "domain_hints": ["jobs.lever.co", "palantir.com"]
        }

        # Mock responses
        def mock_get_side_effect(*args, **kwargs):
            url = args[1] if len(args) > 1 else args[0]
            response_mock = mock.Mock()
            response_mock.url = url
            response_mock.history = []
            if "api.lever.co/v0/postings/palantir?mode=json" in url:
                response_mock.status_code = 200
                response_mock.json.return_value = [{"id": "123", "text": "Software Engineer"}]
            elif "api.lever.co" in url:
                response_mock.status_code = 404
                response_mock.json.return_value = {}
            elif url == "https://jobs.lever.co/palantir":
                response_mock.status_code = 200
                response_mock.text = "<html><body>Lever Job Board for Palantir</body></html>"
                response_mock.headers = {"Content-Type": "text/html"}
            else:
                response_mock.status_code = 404
                response_mock.text = ""
                response_mock.headers = {"Content-Type": "text/html"}
            return response_mock

        mock_get.side_effect = mock_get_side_effect

        res = resolve_employer(entry)
        self.assertEqual(res["url"], "https://jobs.lever.co/palantir")
        self.assertEqual(res["platform"], "lever")
        self.assertEqual(res["provider"]["family"], "lever")

if __name__ == "__main__":
    unittest.main()
