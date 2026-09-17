from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import query_job_cache


class WexR22593Diagnostic(unittest.TestCase):
    def test_emit_targeted_record(self):
        feed = query_job_cache.load_json(ROOT / "data" / "listings.json")
        cache = query_job_cache.load_json(ROOT / "data" / "workday-inspections.json")
        result = query_job_cache.query_records(feed, cache, "R22593", limit=10, full=False)
        self.fail("WEX_R22593_DIAGNOSTIC=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
