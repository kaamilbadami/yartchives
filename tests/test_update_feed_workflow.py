from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "update-feed.yml"


class UpdateFeedWorkflowTests(unittest.TestCase):
    def test_employer_universe_is_persisted_immediately_after_resolution(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        resolver = text.index("- name: Refresh bounded employer careers resolutions")
        persist = text.index("- name: Persist employer universe before long feed build")
        snapshot = text.index("- name: Snapshot existing final feed")

        self.assertLess(resolver, persist)
        self.assertLess(persist, snapshot)
        self.assertIn('git add employer_universe.json', text[persist:snapshot])
        self.assertIn('git push origin HEAD:main', text[persist:snapshot])

    def test_final_generated_commit_does_not_rebundle_employer_universe(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        final_commit = text.index("- name: Commit updated feed and inspections")
        tail = text[final_commit:]

        self.assertIn(
            'GENERATED_PATHS="data/listings.json data/workday-inspections.json"',
            tail,
        )
        self.assertNotIn(
            'GENERATED_PATHS="data/listings.json data/workday-inspections.json employer_universe.json"',
            tail,
        )
        self.assertNotIn("yartchives-generated-employer-universe", tail)


    def test_final_generated_commit_shell_is_syntax_valid(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        final_commit = text.index("- name: Commit updated feed and inspections")
        step = text[final_commit:]
        run_marker = "        run: |\n"
        script_start = step.index(run_marker) + len(run_marker)
        script_lines = []
        for line in step[script_start:].splitlines():
            if line and not line.startswith("          "):
                break
            script_lines.append(line[10:] if line.startswith("          ") else "")
        script = "\n".join(script_lines) + "\n"

        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_final_main_advance_guard_only_allows_generated_files(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        final_commit = text.index("- name: Commit updated feed and inspections")
        tail = text[final_commit:]

        self.assertIn(
            "grep -Ev '^data/(listings|workday-inspections)\\.json$' || true",
            tail,
        )
        self.assertEqual(tail.count("git reset --hard origin/main"), 1)



if __name__ == "__main__":
    unittest.main()
