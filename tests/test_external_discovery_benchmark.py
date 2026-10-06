import unittest
import json
import tempfile
import subprocess
from pathlib import Path

class TestExternalDiscoveryBenchmark(unittest.TestCase):
    def test_generates_plan_and_template(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            out_md = temp_path / "plan.md"
            out_csv = temp_path / "plan.csv"

            res = subprocess.run([
                "python3", "scripts/external_discovery_benchmark.py",
                "--generate-plan", str(out_md),
                "--generate-csv", str(out_csv),
                "--personas", "audit/personas/trust-benchmark-personas.json"
            ], capture_output=True, text=True)

            self.assertEqual(res.returncode, 0)
            self.assertTrue(out_md.exists())
            self.assertTrue(out_csv.exists())

            md_content = out_md.read_text(encoding="utf-8")
            self.assertIn("## Persona: KB", md_content)
            self.assertIn("## Persona: BM", md_content)

            csv_content = out_csv.read_text(encoding="utf-8")
            self.assertTrue(csv_content.startswith("persona_id,company,title,location,url,source,discovery_url,discovery_query,expected_state"))

    def test_creates_frozen_benchmark_from_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            draft_csv = temp_path / "draft.csv"
            out_json = temp_path / "benchmark.json"

            draft_csv.write_text(
                "persona_id,company,title,location,url,source,discovery_url,discovery_query,expected_state\n"
                "KB,Acme,Software Intern,Hartford CT,https://jobs.acme.example/1,LinkedIn,https://linkedin.com/foo,foo query,CT\n"
                "BM,Beta,Business Intern,Boston MA,https://linkedin.com/jobs/view/123,LinkedIn,https://linkedin.com/jobs/view/123,bar query,MA\n"
            )

            res = subprocess.run([
                "python3", "scripts/external_discovery_benchmark.py",
                "--draft-csv", str(draft_csv),
                "--output-json", str(out_json),
                "--skip-interactive",
                "--personas", "audit/personas/trust-benchmark-personas.json"
            ], capture_output=True, text=True)

            self.assertEqual(res.returncode, 0)
            self.assertTrue(out_json.exists())

            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Independent External Discovery Benchmark")
            self.assertTrue(data["sampling_method"]["selection_independent_of_yartchives"])
            self.assertIn("benchmark_fixed_at", data)

            # Persona areas are normalized to feed profile IDs.
            self.assertCountEqual(data["scope"]["profiles"], ["cs", "tech-business"])
            self.assertCountEqual(data["scope"]["states"], ["CT", "MA"])

            discoveries = data["discoveries"]
            self.assertEqual(len(discoveries), 2)

            d1 = next(d for d in discoveries if d["persona_id"] == "KB")
            self.assertEqual(d1["url_kind"], "authoritative")
            self.assertEqual(d1["expected_profile"], "cs")

            d2 = next(d for d in discoveries if d["persona_id"] == "BM")
            self.assertEqual(d2["url_kind"], "discovery_surface")
            self.assertEqual(d2["expected_profile"], "tech-business")

if __name__ == "__main__":
    unittest.main()
