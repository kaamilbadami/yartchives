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


    def test_generates_plan_for_one_selected_persona(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            out_md = temp_path / "plan.md"
            out_csv = temp_path / "plan.csv"

            res = subprocess.run([
                "python3", "scripts/external_discovery_benchmark.py",
                "--generate-plan", str(out_md),
                "--generate-csv", str(out_csv),
                "--personas", "audit/personas/trust-benchmark-personas.json",
                "--persona", "KB",
            ], capture_output=True, text=True)

            self.assertEqual(res.returncode, 0)
            md_content = out_md.read_text(encoding="utf-8")
            self.assertIn("## Persona: KB", md_content)
            self.assertNotIn("## Persona: BM", md_content)

    def test_creates_frozen_benchmark_from_csv(self):
        import unittest.mock as mock
        import sys
        from scripts.external_discovery_benchmark import main
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            draft_csv = temp_path / "draft.csv"
            out_json = temp_path / "benchmark.json"

            draft_csv.write_text(
                "persona_id,company,title,location,url,source,discovery_url,discovery_query,expected_state\n"
                "KB,Acme,Software Intern,Hartford CT,https://jobs.acme.example/1,LinkedIn,https://linkedin.com/foo,foo query,CT\n"
            )

            with mock.patch("scripts.external_discovery_benchmark.inspect_posting_url", return_value={"status": "inspected", "posting": {"title": "Software Intern Summer 2027", "application_status": "available"}, "requirements": {"work_authorization": {"required": []}}}):
                with mock.patch.object(sys, "argv", [
                    "external_discovery_benchmark.py",
                    "--draft-csv", str(draft_csv),
                    "--output-json", str(out_json),
                    "--skip-interactive",
                    "--personas", "audit/personas/trust-benchmark-personas.json"
                ]):
                    exit_code = main()
                    self.assertEqual(exit_code, 0)

                self.assertTrue(out_json.exists())

            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Independent External Discovery Benchmark")
            self.assertTrue(data["sampling_method"]["selection_independent_of_yartchives"])
            self.assertIn("benchmark_fixed_at", data)

            # Persona areas are normalized to feed profile IDs.
            self.assertCountEqual(data["scope"]["profiles"], ["cs"])
            self.assertCountEqual(data["scope"]["states"], ["CT"])

            discoveries = data["discoveries"]
            self.assertEqual(len(discoveries), 1)

            d1 = next(d for d in discoveries if d["persona_id"] == "KB")
            self.assertEqual(d1["url_kind"], "authoritative")
            self.assertEqual(d1["expected_profile"], "cs")

    def test_rubric_evaluates_discoveries_correctly(self):
        from scripts.external_discovery_benchmark import _verify_discovery

        persona = {"student_stage": "Sophomore"}

        # Discovery surface
        dims = _verify_discovery({}, persona, "discovery_surface", {})
        self.assertEqual(dims["active_status"], "unknown")

        # Unavailable posting
        dims = _verify_discovery({}, persona, "authoritative", {"status": "unavailable"})
        self.assertEqual(dims["active_status"], "rejected")

        # Closed posting
        dims = _verify_discovery({}, persona, "authoritative", {"status": "inspected", "posting": {"application_status": "closed"}})
        self.assertEqual(dims["active_status"], "rejected")

        # Unpaid
        dims = _verify_discovery({}, persona, "authoritative", {"status": "inspected", "posting": {"title": "Unpaid Intern", "application_status": "available"}})
        self.assertEqual(dims["paid_status"], "rejected")

        # Graduate mismatch
        dims = _verify_discovery({}, persona, "authoritative", {"status": "inspected", "posting": {"title": "PhD Intern", "application_status": "available"}})
        self.assertEqual(dims["undergraduate_eligibility"], "rejected")

        # Expired season
        dims = _verify_discovery({}, persona, "authoritative", {"status": "inspected", "posting": {"title": "Software Intern Fall 2025", "application_status": "available"}})
        self.assertEqual(dims["internship_term"], "rejected")

        # Graduation mismatch
        inspection = {
            "status": "inspected",
            "posting": {"title": "Software Intern Summer 2027", "application_status": "available"},
            "requirements": {"graduation": {"required": [{"statement": "Must graduate in 2026"}]}}
        }
        dims = _verify_discovery({}, persona, "authoritative", inspection)
        self.assertEqual(dims["graduation_windows"], "rejected")

        # Missing intern keyword
        dims = _verify_discovery({}, persona, "authoritative", {"status": "inspected", "posting": {"title": "Software Engineer", "application_status": "available"}})
        self.assertEqual(dims["internship_term"], "unknown")

        # Ambiguous work auth
        inspection_auth = {
            "status": "inspected",
            "posting": {"title": "Software Intern Summer 2027", "application_status": "available"},
            "requirements": {"work_authorization": {"required": [{"statement": "Will you require sponsorship now or in the future?"}]}}
        }
        dims = _verify_discovery({}, persona, "authoritative", inspection_auth)
        self.assertEqual(dims["work_authorization"], "unknown")

        # Verified
        dims = _verify_discovery({}, persona, "authoritative", {"status": "inspected", "posting": {"title": "Software Intern Summer 2027", "application_status": "available"}})
        self.assertEqual(dims["active_status"], "verified")
        self.assertEqual(dims["paid_status"], "verified")
        self.assertEqual(dims["internship_term"], "verified")
        self.assertEqual(dims["graduation_windows"], "verified")
        self.assertEqual(dims["work_authorization"], "verified")
        self.assertEqual(dims["undergraduate_eligibility"], "verified")

if __name__ == "__main__":
    unittest.main()
