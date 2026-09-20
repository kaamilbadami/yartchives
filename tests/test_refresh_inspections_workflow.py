from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "refresh-inspections.yml"


class RefreshInspectionsWorkflowTests(unittest.TestCase):
    def test_generated_commit_shell_is_syntax_valid(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        commit_name = "- name: Commit bounded posting inspections"
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

if __name__ == "__main__":
    unittest.main()
