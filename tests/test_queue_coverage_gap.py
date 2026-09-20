import json
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.queue_coverage_gap import find_biggest_gap, issue_already_queued, resources_conflict_with_active_work

class TestQueueCoverageGap(unittest.TestCase):
    def test_find_biggest_gap_no_hint(self):
        universe = {
            "employers": [
                {
                    "name": "Employer 1",
                    "seed_sets": ["fortune-500-2026"],
                    "provider": {"status": "unresolved"},
                    "seed_metadata": {}
                },
                {
                    "name": "Employer 2",
                    "seed_sets": ["fortune-500-2026"],
                    "provider": {"status": "unresolved"},
                    "seed_metadata": {}
                }
            ]
        }
        gap = find_biggest_gap(universe)
        self.assertIsNotNone(gap)
        self.assertEqual(gap[0], "Discovery gap (No domain hint)")
        self.assertEqual(gap[1], 2)
        self.assertEqual(gap[3], "discovery")

    def test_find_biggest_gap_ats_family(self):
        universe = {
            "employers": [
                {
                    "name": "Employer 1",
                    "seed_sets": ["cs-benchmark"],
                    "provider": {"status": "unresolved"},
                    "seed_metadata": {
                        "test": {"domain_hints": ["workday.com"]}
                    }
                }
            ]
        }
        with patch('scripts.queue_coverage_gap.fingerprint_provider', return_value={"family": "workday"}):
            gap = find_biggest_gap(universe)

        self.assertIsNotNone(gap)
        self.assertEqual(gap[0], "ATS Family integration (workday)")
        self.assertEqual(gap[1], 1)
        self.assertEqual(gap[3], "ats-workday")

    def test_stop_condition(self):
        universe = {
            "employers": [
                {
                    "name": "Employer 1",
                    "seed_sets": ["cs-benchmark"],
                    "provider": {"status": "resolved"}
                }
            ]
        }
        gap = find_biggest_gap(universe)
        self.assertIsNone(gap)

    def test_issue_already_queued(self):
        issues = [
            {"body": "<!-- coverage-gap: ats-workday -->\nSome content"}
        ]
        self.assertTrue(issue_already_queued(issues, "ats-workday"))
        self.assertFalse(issue_already_queued(issues, "ats-greenhouse"))

    def test_resources_conflict_with_active_work(self):
        from scripts.dispatch_autonomous_issues import Task

        # Non-conflicting task
        active_task_1 = Task(1, "Test", "", "P1", "link-quality", frozenset(), frozenset(), frozenset())
        self.assertFalse(resources_conflict_with_active_work([active_task_1]))

        # Conflicting feed-core task
        active_task_2 = Task(1, "Test", "", "P1", "feed", frozenset(), frozenset(), frozenset())
        self.assertTrue(resources_conflict_with_active_work([active_task_2]))

        # Conflicting coverage task
        active_task_3 = Task(1, "Test", "", "P1", "coverage-automation", frozenset(), frozenset(), frozenset())
        self.assertTrue(resources_conflict_with_active_work([active_task_3]))

if __name__ == '__main__':
    unittest.main()
