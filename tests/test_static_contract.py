from pathlib import Path
import unittest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


class StaticContractTests(unittest.TestCase):
    def test_required_controls_exist(self):
        soup = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
        required = {
            "profileChips", "searchInput", "locationInput", "radiusInput",
            "educationSelect", "opportunityTypeSelect", "freshnessSelect", "statusSelect",
            "jobs", "jobCardTemplate", "loadMoreBtn", "shownCount", "totalCount",
            "newCount", "savedCount", "resultsTitle", "resultsNote", "feedMeta",
            "sourceHealth", "errorBox", "shareBtn", "clearFiltersBtn",
        }
        missing = sorted(item for item in required if soup.find(id=item) is None)
        self.assertEqual(missing, [])

    def test_quick_zip_buttons(self):
        soup = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
        values = {button.get("data-location") for button in soup.select(".quick-locations button")}
        self.assertIn("CT", values)
        self.assertIn("06897", values)
        self.assertIn("20740", values)

    def test_frontend_utils_load_before_app(self):
        soup = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
        scripts = [tag.get("src") for tag in soup.find_all("script") if tag.get("src")]
        self.assertLess(scripts.index("frontend-utils.js"), scripts.index("app.js"))


if __name__ == "__main__":
    unittest.main()
