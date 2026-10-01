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
            raise mod.StructuralSourceError("mock error", [404])

        with mock.patch.object(mod, "fetch_source", side_effect=fetch_mock):
            with mock.patch.object(mod, "invalidate_resolution") as invalidate_mock:
                doc = mod.enrich(doc, old_doc, universe, mock.Mock(), datetime(2026, 9, 17, tzinfo=timezone.utc))

        invalidate_mock.assert_called_once_with(
            employer, "StructuralSourceError: mock error"
        )
        self.assertEqual(doc["sources"]["auto-successfactors-capgemini"]["status"], "quarantined")

if __name__ == "__main__":
    unittest.main()
