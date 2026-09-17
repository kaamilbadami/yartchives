import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("workday_inspector", SCRIPTS / "workday_inspector.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_workday_start_date_is_authoritative_posting_date():
    fixture = json.loads((ROOT / "tests" / "fixtures" / "workday" / "software_intern.json").read_text(encoding="utf-8"))
    normalized = mod.normalize_payload(fixture)
    assert normalized["posting"]["posted_at"] == "2026-09-16"
    assert normalized["posting"]["posted_on_text"] == "Posted Today"
