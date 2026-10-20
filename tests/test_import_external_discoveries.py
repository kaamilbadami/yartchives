import unittest
import json
import tempfile
import subprocess
from pathlib import Path

class TestImportExternalDiscoveries(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.input_json = self.temp_path / "input.json"
        self.input_csv = self.temp_path / "input.csv"
        self.output_csv = self.temp_path / "output.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_valid_json(self):
        data = {
            "run_id": "run-12345",
            "collected_at": "2024-01-01T00:00:00Z",
            "discoveries": [
                {
                    "company": "Acme",
                    "title": "Software Intern",
                    "authoritative_url": "https://jobs.acme.example/1",
                    "persona_id": "KB",
                    "expected_state": "CT",
                    "source": "ChatGPT",
                    "discovery_url": "https://chatgpt.com/share/123",
                    "discovery_query": "Find software engineering internships in Connecticut"
                }
            ]
        }
        self.input_json.write_text(json.dumps(data))

        res = subprocess.run([
            "python3", "scripts/import_external_discoveries.py",
            str(self.input_json), str(self.output_csv)
        ], capture_output=True, text=True)

        self.assertEqual(res.returncode, 0)
        self.assertTrue(self.output_csv.exists())
        content = self.output_csv.read_text()
        self.assertIn("KB,Acme,Software Intern,,https://jobs.acme.example/1,ChatGPT,https://chatgpt.com/share/123,Find software engineering internships in Connecticut,CT,2024-01-01T00:00:00Z,run-12345", content)

    def test_skips_malformed(self):
        data = [
            {
                "company": "Missing URL",
                "title": "Software Intern",
                "persona_id": "KB",
                "expected_state": "CT"
            },
            {
                "company": "Valid Company",
                "title": "Data Intern",
                "url": "https://valid.example.com",
                "persona_id": "BM",
                "expected_state": "NY"
            }
        ]
        self.input_json.write_text(json.dumps(data))

        res = subprocess.run([
            "python3", "scripts/import_external_discoveries.py",
            str(self.input_json), str(self.output_csv)
        ], capture_output=True, text=True)

        self.assertEqual(res.returncode, 0)
        content = self.output_csv.read_text()
        self.assertNotIn("Missing URL", content)
        self.assertIn("Valid Company", content)

    def test_deduplicates(self):
        data = [
            {
                "company": "Acme",
                "title": "Software Intern",
                "url": "https://jobs.acme.example/1",
                "persona_id": "KB",
                "expected_state": "CT"
            },
            {
                "company": "Acme",
                "title": "Software Intern Duplicate",
                "url": "https://jobs.acme.example/1",
                "persona_id": "KB",
                "expected_state": "CT"
            },
            {
                "company": "Acme",
                "title": "Another Role",
                "url": "https://jobs.acme.example/2",
                "persona_id": "KB",
                "expected_state": "CT"
            }
        ]
        self.input_json.write_text(json.dumps(data))

        res = subprocess.run([
            "python3", "scripts/import_external_discoveries.py",
            str(self.input_json), str(self.output_csv)
        ], capture_output=True, text=True)

        self.assertEqual(res.returncode, 0)
        content = self.output_csv.read_text()
        self.assertEqual(content.count("Acme"), 2) # Header doesn't have it, valid output rows do
        self.assertIn("Another Role", content)
        self.assertNotIn("Duplicate", content)

    def test_import_from_csv(self):
        self.input_csv.write_text(
            "company,title,url,persona_id,expected_state,run_id,collected_at\n"
            "Beta,Data Intern,https://jobs.beta.example/1,BM,NY,run-555,2024-02-01T00:00:00Z\n"
        )

        res = subprocess.run([
            "python3", "scripts/import_external_discoveries.py",
            str(self.input_csv), str(self.output_csv)
        ], capture_output=True, text=True)

        self.assertEqual(res.returncode, 0)
        content = self.output_csv.read_text()
        self.assertIn("Beta,Data Intern", content)
        self.assertIn("run-555", content)

if __name__ == "__main__":
    unittest.main()
