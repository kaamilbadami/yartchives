import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.import_external_discoveries import import_discoveries
from scripts.external_discovery_benchmark import REQUIRED_DRAFT_FIELDS


class TestImportExternalDiscoveries(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.draft_csv = self.dir_path / "draft.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_imports_valid_json_list(self):
        input_file = self.dir_path / "input.json"
        input_data = [
            {
                "persona_id": "KB",
                "company": "Acme Corp",
                "title": "Software Intern",
                "url": "https://careers.acme.com/job/123",
                "source": "Independent Search",
                "discovery_url": "https://chatgpt.com/share/xyz",
                "discovery_query": "summer 2027 internship",
                "expected_state": "open",
                "extra_field": "should be ignored"
            }
        ]
        input_file.write_text(json.dumps(input_data))

        result = import_discoveries(input_file, self.draft_csv)
        self.assertEqual(result, 0)

        with self.draft_csv.open("r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 1)
            row = reader[0]
            self.assertEqual(row["company"], "Acme Corp")
            self.assertNotIn("extra_field", row)
            self.assertEqual(list(row.keys()), REQUIRED_DRAFT_FIELDS)

    def test_rejects_missing_required_identifiers(self):
        input_file = self.dir_path / "input.json"
        input_data = [
            {
                "persona_id": "KB",
                "company": "Acme Corp",
                "title": "Software Intern",
                # missing url
            }
        ]
        input_file.write_text(json.dumps(input_data))

        result = import_discoveries(input_file, self.draft_csv)
        self.assertEqual(result, 0) # script completes but skips row

        self.assertFalse(self.draft_csv.exists()) # nothing imported

    def test_deduplicates_repeat_imports(self):
        # Create existing CSV
        with self.draft_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=REQUIRED_DRAFT_FIELDS)
            writer.writeheader()
            writer.writerow({
                "persona_id": "KB",
                "company": "Acme Corp",
                "title": "Software Intern",
                "url": "https://careers.acme.com/job/123",
            })

        input_file = self.dir_path / "input.json"
        input_data = [
            {
                "persona_id": "KB",
                "company": "Acme Corp",
                "title": "Software Intern",
                "url": "https://careers.acme.com/job/123", # Duplicate
            },
            {
                "persona_id": "KB",
                "company": "Acme Corp",
                "title": "Data Intern",
                "url": "https://careers.acme.com/job/456", # New URL
            }
        ]
        input_file.write_text(json.dumps(input_data))

        result = import_discoveries(input_file, self.draft_csv)
        self.assertEqual(result, 0)

        with self.draft_csv.open("r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 2)
            urls = [r["url"] for r in reader]
            self.assertIn("https://careers.acme.com/job/123", urls)
            self.assertIn("https://careers.acme.com/job/456", urls)

    def test_allows_multiple_reqs_at_same_company(self):
        input_file = self.dir_path / "input.json"
        input_data = [
            {
                "persona_id": "KB",
                "company": "Acme Corp",
                "title": "Backend Intern",
                "url": "https://careers.acme.com/job/1",
            },
            {
                "persona_id": "KB",
                "company": "Acme Corp",
                "title": "Frontend Intern",
                "url": "https://careers.acme.com/job/2",
            }
        ]
        input_file.write_text(json.dumps(input_data))

        result = import_discoveries(input_file, self.draft_csv)
        self.assertEqual(result, 0)

        with self.draft_csv.open("r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 2)

if __name__ == "__main__":
    unittest.main()
