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

        fast_commit = text.index("- name: Commit fast-path opportunity feed")
        slow_commit = text.index("- name: Commit slow-path enrichments and audits")

        fast_tail = text[fast_commit:slow_commit]
        slow_tail = text[slow_commit:]

        self.assertIn(
            'GENERATED_PATHS="data/listings.json"',
            fast_tail,
        )
        self.assertIn(
            'GENERATED_PATHS="data/workday-inspections.json README.md"',
            slow_tail,
        )
        self.assertNotIn(
            'employer_universe.json"',
            fast_tail,
        )
        self.assertNotIn(
            'employer_universe.json"',
            slow_tail,
        )
        self.assertNotIn("yartchives-generated-employer-universe", fast_tail)
        self.assertNotIn("yartchives-generated-employer-universe", slow_tail)


    def test_final_generated_commit_shell_is_syntax_valid(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        for commit_name in ["- name: Commit fast-path opportunity feed", "- name: Commit slow-path enrichments and audits"]:
            final_commit = text.index(commit_name)

            # Find the end of this step. Either the next step, or the end of the file.
            next_step_idx = text.find("- name:", final_commit + 10)
            if next_step_idx == -1:
                step = text[final_commit:]
            else:
                step = text[final_commit:next_step_idx]

            run_marker = "        run: |\n"
            script_start = step.index(run_marker) + len(run_marker)
            script_lines = []
            for line in step[script_start:].splitlines():
                if line and not line.startswith("          ") and not line.strip() == "":
                    break
                script_lines.append(line[10:] if line.startswith("          ") else line)
            script = "\n".join(script_lines) + "\n"

            result = subprocess.run(
                ["bash", "-n"],
                input=script,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{commit_name} syntax error:\n{result.stderr}\nScript was:\n{script}")

    def test_final_main_advance_guard_only_invalidates_feed_input_changes(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for commit_name in ["- name: Commit fast-path opportunity feed", "- name: Commit slow-path enrichments and audits"]:
            final_commit = text.index(commit_name)
            # Find the end of this run block. We can just take the slice up to the next step, or to the end of the file
            next_step_idx = text.find("- name: ", final_commit + 10)
            if next_step_idx == -1:
                tail = text[final_commit:]
            else:
                tail = text[final_commit:next_step_idx]

            self.assertIn('FEED_INPUT_CHANGES="$(echo "$CHANGED" | grep -E ', tail)
            self.assertIn("scripts/", tail)
            self.assertIn("direct_sources\\.json$", tail)
            self.assertIn("Feed-producing inputs changed on main; leaving this generated result unpublished.", tail)
            self.assertIn("Only unrelated or generated files changed; publishing this completed feed onto current main.", tail)
            self.assertEqual(tail.count("git reset --hard origin/main"), 1)



if __name__ == "__main__":
    unittest.main()
