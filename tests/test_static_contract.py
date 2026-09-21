import hashlib
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
            "sourceHealth", "errorBox", "clearFiltersBtn", "jobsViewBtn", "companiesViewBtn",
        }
        missing = sorted(item for item in required if soup.find(id=item) is None)
        self.assertEqual(missing, [])
        mascot = soup.select_one(".brand-mark")
        self.assertIsNotNone(mascot)
        self.assertEqual(mascot.name, "img")
        self.assertEqual(mascot.get("src"), "assets/yartchives-hedgehog.png")
        self.assertLess((ROOT / "assets" / "yartchives-hedgehog.png").stat().st_size, 16_384)
        self.assertEqual(hashlib.sha256((ROOT / "assets" / "yartchives-hedgehog.png").read_bytes()).hexdigest(), "f12cfe7c0625164638410c8e63fad8079ed7df22a64b82f168c6c64c44c16794")
        freshness = soup.find(id="freshnessSelect")
        self.assertEqual(freshness.find("option", selected=True).get("value"), "all")
        self.assertIsNone(soup.find(id="viewedCount"))
        self.assertIsNone(soup.find("option", attrs={"value": "viewed"}))

    def test_feed_refresh_only_invalidates_on_feed_inputs(self):
        workflow = (ROOT / ".github" / "workflows" / "update-feed.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("FEED_INPUT_CHANGES="), 2)
        for fragment in [
            "scripts/",
            "audit/samples/",
            "data/employer-seeds/",
            "sources\\.json$",
            "direct_sources\\.json$",
            "requirements\\.txt$",
            "\\.github/workflows/update-feed\\.yml$",
        ]:
            self.assertGreaterEqual(workflow.count(fragment), 2)
        self.assertIn("Only unrelated files changed; rebasing employer-universe output onto current main.", workflow)
        self.assertIn("Only unrelated or generated files changed; publishing this completed feed onto current main.", workflow)
        self.assertNotIn("grep -Ev '^data/(listings|workday-inspections)", workflow)
        self.assertNotIn("Aborting this stale build; the next run will resolve from the newer main.", workflow)

    def test_geo_index_is_local_and_built_at_deploy_time(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
        self.assertIn('const GEO_DATA_URL = "data/geo-index.json";', app)
        self.assertNotIn("raw.githubusercontent.com/ReadyAPIs-com/curated-us-zips", app)
        self.assertIn("scripts/build_geo_index.py /tmp/us-zips.csv _site/data/geo-index.json", workflow)
        self.assertIn("f9eb7daabdade9b2a9f3cbc80327a5c152fc82d3", workflow)

    def test_branch_preflight_matches_pr_quality_suite(self):
        quality = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
        preflight = (ROOT / ".github" / "workflows" / "branch-preflight.yml").read_text(encoding="utf-8")
        runner = (ROOT / "scripts" / "run_quality_checks.sh").read_text(encoding="utf-8")

        self.assertIn("branches-ignore:", preflight)
        self.assertIn("- main", preflight)
        self.assertIn("gh pr list", preflight)
        self.assertIn("Open PR already exists; pull_request Quality checks own validation now.", preflight)
        self.assertIn("bash scripts/run_quality_checks.sh all", preflight)

        for phase in ["python", "frontend", "feed", "benchmark"]:
            self.assertIn(f"bash scripts/run_quality_checks.sh {phase}", quality)
        for command in [
            'python -m unittest discover -s tests -p "test_*.py" -v',
            "node tests/apply-next-ui.test.cjs",
            "python scripts/validate_feed.py data/listings.json --minimum-jobs 500 --minimum-healthy-sources 8",
            "python scripts/coverage_audit.py audit/samples/northeast-midatlantic-cs-2026-09-17.json",
        ]:
            self.assertIn(command, runner)

    def test_pages_deploy_includes_static_assets(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
        self.assertIn('- "assets/**"', workflow)
        self.assertIn("mkdir -p _site/data _site/assets", workflow)
        self.assertIn("cp -R assets/. _site/assets/", workflow)

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

    def test_feed_updated_time_is_explicitly_eastern(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        ux = (ROOT / "ux.js").read_text(encoding="utf-8")
        self.assertIn('timeZone: "America/New_York"', app)
        self.assertIn('timeZoneName: "short"', app)
        self.assertIn("formatEasternTimestamp(when)", app)
        self.assertIn("formatEasternTimestamp(when)", ux)

    def test_final_ux_contract(self):
        text = (ROOT / "ux.js").read_text(encoding="utf-8")
        self.assertIn('"Career area"', text)
        self.assertIn('"Product / Analytics"', text)
        self.assertIn('"IT / Tech Consulting"', text)
        self.assertIn('`Posted ${relativeAge(job)} ago`', text)
        self.assertIn('`Distance ≈${Math.round(job._distanceMiles)} mi`', text)
        self.assertIn('"Listing hidden on this browser."', text)
        self.assertIn('"Saved, applied, and hidden are stored only in this browser."', text)

    def test_feed_boot_revalidates_cache_and_tracks_readiness(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("let feedReady = false;", app)
        self.assertIn("function isFeedReady()", app)
        self.assertIn('fetch("data/listings.json", { cache: "no-cache" })', app)
        self.assertNotIn("data/listings.json?ts=", app)
        self.assertNotIn('cache: "no-store"', app)
        self.assertIn("feedReady = true;", app)

    def test_removed_share_button_cannot_block_feed_boot(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('id="shareBtn"', html)
        self.assertIn("if (els.shareBtn) {", app)
        self.assertNotIn("\n  els.shareBtn.addEventListener", app)

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
