import unittest
from pathlib import Path


class HeaderActionsTest(unittest.TestCase):
    def test_copy_link_button_is_not_rendered(self):
        html = Path("index.html").read_text(encoding="utf-8")
        self.assertNotIn('id="shareBtn"', html)
        self.assertNotIn(">Copy link</button>", html)


if __name__ == "__main__":
    unittest.main()
