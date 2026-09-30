import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Tests(unittest.TestCase):
    def test_contract(self):
        workflow = (ROOT / ".github/workflows/repository-housekeeping.yml").read_text()
        self.assertIn("pull_request:", workflow)
        self.assertIn("- closed", workflow)
        self.assertIn("github.event.pull_request.merged == true", workflow)
        self.assertIn("issues: write", workflow)

        reference = re.compile(r"(?im)\b(?:updates?|refs?|references?|related\s+to)\s+#(\d+)\b")
        complete = re.compile(r"(?im)^\s*Completes acceptance criteria for #(\d+)\s*$")
        self.assertEqual(reference.findall("Updates #449"), ["449"])
        self.assertEqual(complete.findall("Updates #449"), [])
        self.assertEqual(
            complete.findall("Completes acceptance criteria for #449"),
            ["449"],
        )


if __name__ == "__main__":
    unittest.main()
