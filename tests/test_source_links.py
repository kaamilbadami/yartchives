import importlib.util
from pathlib import Path
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "source_links.py"
spec = importlib.util.spec_from_file_location("source_links", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SourceLinksTests(unittest.TestCase):
    def test_source_title_location_recovers_when_company_differs(self):
        rows = [{
            "source_key": "speedyapply",
            "company": "Raytheon",
            "title": "Software Engineering Co-op - Summer/Fall 2027",
            "location": "Wilsonville, OR",
            "url": "https://globalhr.wd5.myworkdayjobs.com/example/job/x/req",
        }]
        indexes = mod.build_indexes(rows)
        job = {
            "source_keys": ["speedyapply"],
            "company": "RTX / Raytheon",
            "title": "Software Engineering Co-op - Summer/Fall 2027",
            "location": "Wilsonville, OR",
        }
        self.assertIn("myworkdayjobs.com", mod.choose_direct(job, indexes))

    def test_source_scope_prevents_cross_source_match(self):
        rows = [{
            "source_key": "speedyapply",
            "company": "Example",
            "title": "Software Engineering Intern",
            "location": "Boston, MA",
            "url": "https://example.com/jobs/1",
        }]
        indexes = mod.build_indexes(rows)
        job = {
            "source_keys": ["vansh-cscareers"],
            "company": "Example",
            "title": "Software Engineering Intern",
            "location": "Boston, MA",
        }
        self.assertIsNone(mod.choose_direct(job, indexes))

    def test_ambiguous_title_only_is_not_used(self):
        rows = [
            {
                "source_key": "speedyapply", "company": "A", "title": "Software Intern",
                "location": "Boston, MA", "url": "https://a.example.com/jobs/1",
            },
            {
                "source_key": "speedyapply", "company": "B", "title": "Software Intern",
                "location": "Austin, TX", "url": "https://b.example.com/jobs/2",
            },
        ]
        indexes = mod.build_indexes(rows)
        job = {
            "source_keys": ["speedyapply"], "company": "Other", "title": "Software Intern",
            "location": "Other",
        }
        self.assertIsNone(mod.choose_direct(job, indexes))

    def test_duplicate_visible_rows_are_preserved_as_candidates(self):
        rows = [
            {
                "source_key": "speedyapply", "company": "Raytheon",
                "title": "Software Engineering Co-op - Summer/Fall 2027",
                "location": "Wilsonville, OR", "url": "https://example.com/jobs/1",
            },
            {
                "source_key": "speedyapply", "company": "Raytheon",
                "title": "Software Engineering Co-op - Summer/Fall 2027",
                "location": "Wilsonville, OR", "url": "https://example.com/jobs/2",
            },
        ]
        indexes = mod.build_candidate_indexes(rows)
        job = {
            "source_keys": ["speedyapply"], "company": "RTX",
            "title": "Software Engineering Co-op - Summer/Fall 2027",
            "location": "Wilsonville, OR",
        }
        self.assertEqual(mod.candidate_urls(job, indexes), {
            "https://example.com/jobs/1", "https://example.com/jobs/2"
        })

    def test_workday_source_candidate_uses_authoritative_validator(self):
        candidate = (
            "https://example.wd1.myworkdayjobs.com/Careers/job/Remote/"
            "Software-Engineering-Intern_R-123/apply"
        )
        with mock.patch.object(mod.links, "validate_workday_url", return_value=("ok", candidate)) as probe, \
             mock.patch.object(mod.links, "validate_direct_url", return_value=("ok", candidate)) as validate:
            self.assertEqual(mod.validate_source_candidate(candidate), ("ok", candidate))

        probe.assert_called_once_with(candidate)
        validate.assert_called_once_with(candidate)

    def test_unique_live_candidate_survives_dead_duplicate(self):
        candidates = {"https://example.com/jobs/1", "https://example.com/jobs/2"}
        validation = {
            "https://example.com/jobs/1": ("dead", "https://example.com/jobs/1"),
            "https://example.com/jobs/2": ("ok", "https://example.com/jobs/2"),
        }
        self.assertEqual(
            mod.select_unique_viable(candidates, validation),
            ("https://example.com/jobs/2", "ok"),
        )

    def test_two_live_duplicate_requisitions_remain_ambiguous(self):
        candidates = {"https://example.com/jobs/1", "https://example.com/jobs/2"}
        validation = {
            "https://example.com/jobs/1": ("ok", "https://example.com/jobs/1"),
            "https://example.com/jobs/2": ("ok", "https://example.com/jobs/2"),
        }
        self.assertIsNone(mod.select_unique_viable(candidates, validation))


if __name__ == "__main__":
    unittest.main()
