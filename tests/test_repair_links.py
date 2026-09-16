import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repair_links.py"
spec = importlib.util.spec_from_file_location("repair_links", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class RepairLinksTests(unittest.TestCase):
    def test_applyguy_original_listing_becomes_direct(self):
        doc = {
            "jobs": [{
                "id": "1",
                "company": "Analog Devices",
                "title": "Embedded Software Engineer Intern",
                "source_keys": ["applyguy"],
                "url": "",
            }]
        }
        payload = {
            "jobs": [{
                "company": "Analogdevices",
                "title": "Embedded Software Engineer Intern",
                "listingUrl": "https://analogdevices.wd1.myworkdayjobs.com/external/job/x/R266132",
            }]
        }
        stats = mod.repair_document(doc, payload)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "direct")
        self.assertIn("myworkdayjobs.com", job["url"])
        self.assertEqual(stats["applyguy_repaired"], 1)

    def test_zapply_redirect_is_not_labeled_direct_apply(self):
        doc = {
            "jobs": [{
                "id": "2",
                "company": "CACI",
                "title": "Embedded Software Engineering Co-op",
                "source_keys": ["zapply"],
                "url": "https://zapply.jobs/l/d/workday-caci-external-331393",
            }]
        }
        mod.repair_document(doc)
        job = doc["jobs"][0]
        self.assertEqual(job["url"], "")
        self.assertEqual(job["link_kind"], "listing")
        self.assertEqual(job["listing_url"], "https://zapply.jobs/l/d/workday-caci-external-331393")

    def test_direct_employer_url_stays_direct(self):
        doc = {
            "jobs": [{
                "id": "3",
                "company": "Example",
                "title": "Software Engineering Intern",
                "source_keys": ["dreamwork-tech"],
                "url": "https://example.com/careers/jobs/123",
            }]
        }
        mod.repair_document(doc)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "direct")
        self.assertEqual(job["url"], "https://example.com/careers/jobs/123")

    def test_github_source_is_source_only(self):
        doc = {
            "jobs": [{
                "id": "4",
                "company": "Example",
                "title": "Software Engineering Intern",
                "source_keys": ["applyguy"],
                "url": "https://github.com/ApplyGuy/2027-Internships",
            }]
        }
        mod.repair_document(doc)
        job = doc["jobs"][0]
        self.assertEqual(job["link_kind"], "source")
        self.assertEqual(job["url"], "")
        self.assertNotIn("listing_url", job)


if __name__ == "__main__":
    unittest.main()