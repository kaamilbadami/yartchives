import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "ashby_inspector.py"
spec = importlib.util.spec_from_file_location("ashby_inspector_board_names", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

POSTING_ID = "5f1f25ee-709d-4ae0-ada4-d1f243bde89c"


class AshbyBoardNameTests(unittest.TestCase):
    def test_encoded_space_board_name_is_supported(self):
        url = (
            "https://jobs.ashbyhq.com/Superhuman%20Platform%20Inc/"
            f"{POSTING_ID}/application?embed=true&utm_source=Simplify"
        )
        derived = mod.derive_ashby_endpoint(url)
        self.assertEqual(derived["board_name"], "Superhuman Platform Inc")
        self.assertEqual(
            derived["canonical_job_url"],
            f"https://jobs.ashbyhq.com/Superhuman%20Platform%20Inc/{POSTING_ID}",
        )
        self.assertEqual(
            derived["endpoint_url"],
            "https://api.ashbyhq.com/posting-api/job-board/Superhuman%20Platform%20Inc",
        )

    def test_board_name_can_contain_legitimate_punctuation(self):
        url = f"https://jobs.ashbyhq.com/O%27Reilly%20%26%20Co/{POSTING_ID}"
        derived = mod.derive_ashby_endpoint(url)
        self.assertEqual(derived["board_name"], "O'Reilly & Co")
        self.assertIn("O%27Reilly%20%26%20Co", derived["endpoint_url"])

    def test_encoded_path_delimiter_is_rejected(self):
        url = f"https://jobs.ashbyhq.com/bad%2Fboard/{POSTING_ID}"
        with self.assertRaises(mod.UnsupportedAshbyUrl):
            mod.derive_ashby_endpoint(url)


if __name__ == "__main__":
    unittest.main()
