import json
import tempfile
import unittest
from pathlib import Path

import scripts.update_readme_status as mod


class UpdateReadmeStatusTests(unittest.TestCase):
    def test_listing_rows_accepts_wrapped_feed(self):
        payload = {"listings": [{"id": "a"}, {"id": "b"}]}
        self.assertEqual(len(mod.listing_rows(payload)), 2)

    def test_render_status_counts_rows_and_distinct_sources(self):
        rows = [
            {"source": "Simplify"},
            {"source": "Simplify"},
            {"source_name": "USAJOBS"},
            {"provenance": {"provider": "Workday"}},
            {},
        ]
        status = mod.render_status(rows)
        self.assertIn("**Published listings:** 5", status)
        self.assertIn("**Distinct source labels:** 3", status)

    def test_replace_status_preserves_product_owned_text(self):
        original = (
            "# Yartchives\n\nProduct intro.\n\n"
            f"{mod.START}\nold\n{mod.END}\n\nFooter.\n"
        )
        updated = mod.replace_status(original, mod.render_status([{"source": "A"}]))
        self.assertTrue(updated.startswith("# Yartchives\n\nProduct intro."))
        self.assertTrue(updated.endswith("\n\nFooter.\n"))
        self.assertNotIn("\nold\n", updated)

    def test_update_readme_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            feed = root / "listings.json"
            readme.write_text(
                f"Before\n{mod.START}\nold\n{mod.END}\nAfter\n",
                encoding="utf-8",
            )
            feed.write_text(
                json.dumps([{"source": "A"}, {"source": "B"}]),
                encoding="utf-8",
            )
            self.assertTrue(mod.update_readme(readme, feed))
            first = readme.read_text(encoding="utf-8")
            self.assertFalse(mod.update_readme(readme, feed))
            self.assertEqual(readme.read_text(encoding="utf-8"), first)


if __name__ == "__main__":
    unittest.main()
