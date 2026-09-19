import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("direct_icims", SCRIPT_DIR / "direct_icims.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DirectIcimsTests(unittest.TestCase):
    def test_discovers_evidenced_cs_icims_sites_nationally(self):
        feed = {
            "jobs": [
                {
                    "company": "General Dynamics Electric Boat",
                    "title": "Information Technology, Software Engineering, & Computer Science - 2027 Summer Internship",
                    "states": ["CT"],
                    "profiles": ["cs"],
                    "url": "https://careers-gdeb.icims.com/jobs/20341/job",
                },
                {
                    "company": "General Dynamics Electric Boat",
                    "title": "Another Software Internship",
                    "states": ["CT"],
                    "profiles": ["cs"],
                    "url": "https://careers-gdeb.icims.com/jobs/20500/another/job?in_iframe=1",
                },
                {
                    "company": "Other",
                    "states": ["NY"],
                    "profiles": ["cs"],
                    "url": "https://careers-other.icims.com/jobs/100/job",
                },
            ]
        }
        sources = mod.discover_sources(feed)
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]["host"], "careers-gdeb.icims.com")
        self.assertEqual(sources[0]["search_url"], "https://careers-gdeb.icims.com/jobs/search")
        self.assertEqual(sources[0]["sitemap_url"], "https://careers-gdeb.icims.com/sitemap.xml")

    def test_extract_job_links_dedupes_ids_and_ignores_non_jobs(self):
        html = """
        <a href="/jobs/20338/cybersecurity---2027-summer-internship/job?mobile=true">Cyber</a>
        <a href="https://careers-gdeb.icims.com/jobs/20338/job">Duplicate</a>
        <a href="/jobs/20341/software/job">Software</a>
        <a href="/jobs/intro">Intro</a>
        """
        links = mod.extract_job_links(html, "https://careers-gdeb.icims.com/jobs/search")
        self.assertEqual(
            links,
            [
                "https://careers-gdeb.icims.com/jobs/20338/job",
                "https://careers-gdeb.icims.com/jobs/20341/job",
            ],
        )

    def test_sitemap_fallback_prefilters_to_student_cs_slugs(self):
        source = {
            "host": "careers-gdeb.icims.com",
            "search_url": "https://careers-gdeb.icims.com/jobs/search",
            "sitemap_url": "https://careers-gdeb.icims.com/sitemap.xml",
        }
        sitemap = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset>
          <url><loc>https://careers-gdeb.icims.com/jobs/20338/cybersecurity---2027-summer-internship/job</loc></url>
          <url><loc>https://careers-gdeb.icims.com/jobs/20341/information-technology-software-engineering-2027-summer-internship/job</loc></url>
          <url><loc>https://careers-gdeb.icims.com/jobs/20500/test-quality-and-certification-program-rep/job</loc></url>
          <url><loc>https://careers-gdeb.icims.com/jobs/20733/2027-human-resources-summer-internship/job</loc></url>
          <url><loc>https://other.icims.com/jobs/99999/software-engineering-intern/job</loc></url>
        </urlset>"""
        links = mod.extract_sitemap_job_links(sitemap, source)
        self.assertEqual(
            links,
            [
                "https://careers-gdeb.icims.com/jobs/20338/job",
                "https://careers-gdeb.icims.com/jobs/20341/job",
            ],
        )

    def test_empty_search_shell_falls_back_to_sitemap(self):
        source = {
            "host": "careers-gdeb.icims.com",
            "search_url": "https://careers-gdeb.icims.com/jobs/search",
            "sitemap_url": "https://careers-gdeb.icims.com/sitemap.xml",
        }

        class Response:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url == source["search_url"]:
                    return Response("<html><body>Search jobs</body></html>")
                if url == source["sitemap_url"]:
                    return Response(
                        "<urlset><url><loc>"
                        "https://careers-gdeb.icims.com/jobs/20338/"
                        "cybersecurity---2027-summer-internship/job"
                        "</loc></url></urlset>"
                    )
                raise AssertionError(url)

        session = Session()
        links = mod.search_site(session, source)
        self.assertEqual(links, ["https://careers-gdeb.icims.com/jobs/20338/job"])
        self.assertEqual(
            [call[0] for call in session.calls],
            [source["search_url"], source["sitemap_url"]],
        )

    def test_authoritative_cybersecurity_intern_becomes_direct_job(self):
        source = {
            "key": "auto-icims-careers-gdeb-icims-com",
            "name": "General Dynamics Electric Boat (auto-discovered iCIMS)",
            "company": "General Dynamics Electric Boat",
            "homepage": "https://careers-gdeb.icims.com/jobs/intro",
        }
        inspection = {
            "status": "inspected",
            "posting": {
                "title": "Cybersecurity - 2027 Summer Internship",
                "date_posted": "2026-09-03",
                "locations": {"status": "authoritative", "values": ["Groton, CT, US"]},
            },
        }
        job = mod.job_from_inspection(
            source,
            "https://careers-gdeb.icims.com/jobs/20338/job",
            inspection,
            datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(job)
        self.assertEqual(job["company"], "General Dynamics Electric Boat")
        self.assertIn("cs", job["profiles"])
        self.assertIn("CT", job["states"])
        self.assertTrue(job["direct_employer"])
        self.assertEqual(job["posted_at"], "2026-09-03T00:00:00Z")

    def test_non_us_student_role_is_rejected(self):
        source = {
            "key": "auto-icims-careers-example-icims-com",
            "name": "Example (auto-discovered iCIMS)",
            "company": "Example",
            "homepage": "https://careers-example.icims.com/jobs/intro",
        }
        inspection = {
            "status": "inspected",
            "posting": {
                "title": "Software Engineering Intern",
                "date_posted": "2026-09-03",
                "locations": {"status": "authoritative", "values": ["Toronto, ON, Canada"]},
            },
        }
        job = mod.job_from_inspection(
            source,
            "https://careers-example.icims.com/jobs/999/job",
            inspection,
            datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        self.assertIsNone(job)

    def test_fetch_sources_concurrently_handles_success_and_failure(self):
        source1 = {"key": "source1", "host": "source1.icims.com"}
        source2 = {"key": "source2", "host": "source2.icims.com"}

        class FakeSession:
            pass

        def fake_fetch_source(client, source, reference):
            if source["key"] == "source1":
                return [{"id": "1", "title": "Software Intern"}]
            raise RuntimeError("network timeout")

        original_fetch_source = mod.fetch_source
        try:
            mod.fetch_source = fake_fetch_source
            results = mod.fetch_sources_concurrently(FakeSession(), [source1, source2], datetime.now(timezone.utc))

            self.assertIn("source1", results)
            self.assertIn("source2", results)
            self.assertEqual(results["source1"][0], [{"id": "1", "title": "Software Intern"}])
            self.assertIsNone(results["source1"][1])

            self.assertIsNone(results["source2"][0])
            self.assertIsInstance(results["source2"][1], RuntimeError)
            self.assertEqual(str(results["source2"][1]), "network timeout")
        finally:
            mod.fetch_source = original_fetch_source

if __name__ == "__main__":
    unittest.main()
