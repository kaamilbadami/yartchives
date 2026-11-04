import unittest
from datetime import datetime, timezone
import json
from unittest.mock import patch, MagicMock

import scripts.direct_successfactors as sf

class AutoDiscoveredHealthPruningTests(unittest.TestCase):
    def test_prunes_stale_auto_discovered_sources_from_health(self):
        doc = {
            "jobs": [],
            "sources": {
                "auto-successfactors-stale": {"status": "quarantined", "error": "blabla"},
                "auto-successfactors-active": {"status": "quarantined", "error": "blabla"},
                "other-source": {"status": "healthy"}
            }
        }
        universe = {}
        old_doc = {}
        reference = datetime.now(timezone.utc)
        client = MagicMock()

        with patch('scripts.direct_successfactors.discover_sources') as mock_discover:
            mock_discover.return_value = [{"key": "auto-successfactors-active", "name": "Active"}]
            with patch('scripts.direct_successfactors.fetch_source') as mock_fetch:
                mock_fetch.return_value = []
                sf.enrich(doc, old_doc, universe, client, reference)

        self.assertNotIn("auto-successfactors-stale", doc["sources"])
        self.assertIn("auto-successfactors-active", doc["sources"])
        self.assertIn("other-source", doc["sources"])

if __name__ == '__main__':
    unittest.main()
