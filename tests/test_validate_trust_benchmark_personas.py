import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_trust_benchmark_personas.py"
FIXTURE_PATH = ROOT / "audit" / "personas" / "trust-benchmark-personas.json"

spec = importlib.util.spec_from_file_location("validate_trust_benchmark_personas", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class TrustBenchmarkPersonaValidationTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_checked_in_fixture_is_valid(self):
        self.assertEqual(mod.validate_document(self.document), [])

    def test_requires_eight_real_derived_personas(self):
        document = copy.deepcopy(self.document)
        document["personas"] = [
            row for row in document["personas"]
            if row["id"] not in {"AL", "GW"}
        ]
        errors = mod.validate_document(document)
        self.assertTrue(any("at least 8 real-derived" in error for error in errors))

    def test_requires_cs_engineering_and_finance_coverage(self):
        document = copy.deepcopy(self.document)
        document["personas"] = [
            row for row in document["personas"]
            if row["primary_area"] != "finance"
        ]
        errors = mod.validate_document(document)
        self.assertIn("benchmark coverage missing primary area: finance", errors)

    def test_rejects_duplicate_ids(self):
        document = copy.deepcopy(self.document)
        document["personas"][1]["id"] = document["personas"][0]["id"]
        errors = mod.validate_document(document)
        self.assertTrue(any("duplicate persona ids" in error for error in errors))

    def test_rejects_contact_like_data(self):
        document = copy.deepcopy(self.document)
        document["personas"][0]["evidence"].append("student@example.com")
        errors = mod.validate_document(document)
        self.assertTrue(any("email-like" in error for error in errors))

    def test_rejects_forbidden_identifying_fields(self):
        document = copy.deepcopy(self.document)
        document["personas"][0]["full_name"] = "Example Person"
        errors = mod.validate_document(document)
        self.assertTrue(any("full_name is forbidden" in error for error in errors))

    def test_rejects_invalid_graduation_format(self):
        document = copy.deepcopy(self.document)
        document["personas"][0]["graduation_options"] = ["2028"]
        errors = mod.validate_document(document)
        self.assertTrue(any("invalid value" in error for error in errors))

    def test_bm_remains_may_2029_only(self):
        document = copy.deepcopy(self.document)
        bm = next(row for row in document["personas"] if row["id"] == "BM")
        bm["graduation_options"] = ["May 2028", "May 2029"]
        errors = mod.validate_document(document)
        self.assertIn("BM graduation_options must remain ['May 2029']", errors)


if __name__ == "__main__":
    unittest.main()
