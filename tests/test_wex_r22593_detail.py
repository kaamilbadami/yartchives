from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import query_job_cache
from posting_requirements import normalize_description, extract_requirements


class WexR22593Detail(unittest.TestCase):
    def test_emit_targeted_description(self):
        cache = query_job_cache.load_json(ROOT / "data" / "workday-inspections.json")
        result = query_job_cache.query_records({}, cache, "R22593", limit=10, full=True)
        entry = result["cache_entries"][0]["entry"]
        description = entry["inspection"]["posting"]["description"]
        normalized, lines = normalize_description(description)
        payload = {"description": normalized, "line_count": len(lines), "reextracted": extract_requirements(lines)}
        self.fail("WEX_R22593_DETAIL=" + json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
