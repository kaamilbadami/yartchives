import json
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
            "sourceHealth", "errorBox", "shareBtn", "clearFiltersBtn", "jobsViewBtn", "companiesViewBtn",
        }
        missing = sorted(item for item in required if soup.find(id=item) is None)
        self.assertEqual(missing, [])
        self.assertEqual(soup.find(id="shareBtn").get_text(strip=True), "Copy link")
        freshness = soup.find(id="freshnessSelect")
        self.assertEqual(freshness.find("option", selected=True).get("value"), "all")

    def test_quick_zip_buttons(self):
        soup = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
        values = {button.get("data-location") for button in soup.select(".quick-locations button")}
        self.assertIn("06897", values)
        self.assertIn("20740", values)

    def test_frontend_script_order(self):
        soup = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
        scripts = [tag.get("src") for tag in soup.find_all("script") if tag.get("src")]
        self.assertLess(scripts.index("frontend-utils.js"), scripts.index("app.js"))
        self.assertLess(scripts.index("app.js"), scripts.index("profile-config.js"))
        self.assertLess(scripts.index("profile-config.js"), scripts.index("enhancements.js"))
        self.assertLess(scripts.index("enhancements.js"), scripts.index("ui.js"))
        self.assertLess(scripts.index("ui.js"), scripts.index("ux.js"))
        self.assertLess(scripts.index("ux.js"), scripts.index("share.js"))
        self.assertLess(scripts.index("share.js"), scripts.index("companies.js"))

    def test_public_profile_configuration(self):
        text = (ROOT / "profile-config.js").read_text(encoding="utf-8")
        self.assertIn('"Business / Product / Analytics"', text)
        self.assertIn('"Mechanical / Manufacturing"', text)
        self.assertIn('"Electrical / Computer Eng."', text)
        self.assertIn("delete PROFILE_LABELS.policy", text)
        self.assertIn("delete PROFILE_LABELS.health", text)

    def test_multiselect_and_manual_applied_behavior_are_wired(self):
        text = (ROOT / "enhancements.js").read_text(encoding="utf-8")
        self.assertIn("profiles: []", text)
        self.assertIn("selectedProfiles.size === 0", text)
        self.assertIn("apply.cloneNode(true)", text)
        self.assertIn("View listing ↗", text)

    def test_final_ux_contract(self):
        text = (ROOT / "ux.js").read_text(encoding="utf-8")
        self.assertIn('"Career area"', text)
        self.assertIn('"Product / Analytics"', text)
        self.assertIn('"IT / Tech Consulting"', text)
        self.assertIn('`Posted ${relativeAge(job)} ago`', text)
        self.assertIn('`Distance ≈${Math.round(job._distanceMiles)} mi`', text)
        self.assertIn('"Listing hidden on this browser."', text)
        self.assertIn('"Saved, applied, and hidden are stored only in this browser."', text)

    def test_share_view_preserves_public_filters_only(self):
        text = (ROOT / "share.js").read_text(encoding="utf-8")
        for parameter in ["q", "loc", "miles", "fresh", "areas", "edu", "type", "sort", "view", "company"]:
            self.assertIn(f'url.searchParams.set("{parameter}"', text)
        self.assertIn("event.stopImmediatePropagation()", text)
        self.assertNotIn('url.searchParams.set("saved"', text)
        self.assertNotIn('url.searchParams.set("hidden"', text)
        self.assertNotIn('url.searchParams.set("applied"', text)

    def test_state_filter_is_present_as_secondary_ui(self):
        text = (ROOT / "enhancements.js").read_text(encoding="utf-8")
        self.assertIn('summary.textContent = "State fallback"', text)
        self.assertIn('radiusField.classList.toggle("hidden", !currentZip())', text)

    def test_ai_source_is_cs_adjacent(self):
        sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
        source = next(row for row in sources if row["key"] == "speedyapply-ai")
        self.assertIn("cs", source.get("profile_hint", []))


if __name__ == "__main__":
    unittest.main()
