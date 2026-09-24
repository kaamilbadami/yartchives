import json
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.queue_coverage_gap import create_issue, find_all_gaps, get_active_and_coverage_issues, issue_already_queued, resources_conflict_with_active_work

class TestQueueCoverageGap(unittest.TestCase):
    def test_find_all_gaps_no_hint(self):
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
        gaps = find_all_gaps(universe)
        self.assertTrue(len(gaps) > 0)
        gap = gaps[0]
        self.assertEqual(gap[0], "Discovery gap (No domain hint)")
        self.assertEqual(gap[1], 2)
        self.assertEqual(gap[3], "discovery")

    def test_find_all_gaps_uses_root_domain_hints(self):
        universe = {
            "employers": [
                {
                    "name": "Employer 1",
                    "seed_sets": ["cs-benchmark"],
                    "provider": {"status": "unresolved"},
                    "domain_hints": ["jobs.smartrecruiters.com"],
                    "seed_metadata": {},
                }
            ]
        }
        with patch("scripts.queue_coverage_gap.fingerprint_provider", return_value={"family": "smartrecruiters"}):
            gaps = find_all_gaps(universe)

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0][0], "ATS Family integration (smartrecruiters)")
        self.assertEqual(gaps[0][3], "ats-smartrecruiters")

    def test_find_all_gaps_ats_family(self):
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
            gaps = find_all_gaps(universe)

        self.assertTrue(len(gaps) > 0)
        gap = gaps[0]
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
        gaps = find_all_gaps(universe)
        self.assertEqual(len(gaps), 0)

    def test_issue_already_queued(self):
        issues = [
            {"body": "<!-- coverage-gap: ats-workday -->\nSome content"}
        ]
        self.assertTrue(issue_already_queued(issues, "ats-workday"))
        self.assertFalse(issue_already_queued(issues, "ats-greenhouse"))

    def test_duplicate_detection_does_not_depend_on_classification_label(self):
        issues = [
            {
                "number": 10,
                "body": "<!-- coverage-gap: discovery -->\npriority: P2\narea: coverage-automation\nresources: automation, coverage-analysis\nautonomous: true",
                "labels": [{"name": "agent-ready"}, {"name": "autonomous-backlog"}],
            }
        ]
        with patch("scripts.queue_coverage_gap._gh_json", return_value=issues):
            _, queued = get_active_and_coverage_issues("kaamilbadami/yartchives")

        self.assertTrue(issue_already_queued(queued, "discovery"))

    def test_create_issue_uses_only_canonical_autonomous_labels(self):
        calls = []
        employers = [{"name": "Employer 1"}]

        with patch("scripts.queue_coverage_gap._gh_run", side_effect=lambda *args: calls.append(args)):
            create_issue(
                "kaamilbadami/yartchives",
                "Discovery gap (No domain hint)",
                1,
                "discovery",
                employers,
            )

        args = calls[0]
        labels = [args[i + 1] for i, value in enumerate(args[:-1]) if value == "--label"]
        self.assertEqual(labels, ["autonomous-backlog", "agent-ready"])
        self.assertNotIn("coverage-automation", labels)
        self.assertNotIn("jules", labels)

    def test_resources_conflict_with_active_work(self):
        from scripts.dispatch_autonomous_issues import Task

        # Non-conflicting task
        active_task_1 = Task(1, "Test", "", "P1", "link-quality", frozenset(), frozenset(), frozenset())
        self.assertFalse(resources_conflict_with_active_work([active_task_1]))

        # Conflicting feed-core task
        active_task_2 = Task(1, "Test", "", "P1", "feed", frozenset(), frozenset(), frozenset())
        self.assertTrue(resources_conflict_with_active_work([active_task_2]))

        # Conflicting coverage task shares the explicit scheduling resources used
        # by generated coverage-automation issues.
        active_task_3 = Task(
            1,
            "Test",
            "",
            "P1",
            "coverage-automation",
            frozenset(),
            frozenset({"automation", "coverage-analysis"}),
            frozenset(),
        )
        self.assertTrue(resources_conflict_with_active_work([active_task_3]))


    @patch("scripts.queue_coverage_gap._gh_json")
    @patch("scripts.queue_coverage_gap.issue_already_queued")
    @patch("scripts.queue_coverage_gap.get_active_and_coverage_issues")
    @patch("scripts.queue_coverage_gap.resources_conflict_with_active_work")
    @patch("scripts.queue_coverage_gap.create_issue")
    def test_select_next_unqueued_gap(self, mock_create, mock_conflict, mock_get_issues, mock_already_queued, mock_gh_json):
        mock_conflict.return_value = False
        mock_get_issues.return_value = ([], [])

        # Simulate that the first gap is already queued, but not the second
        def side_effect_queued(issues, gap_id):
            return gap_id == "discovery"
        mock_already_queued.side_effect = side_effect_queued

        import sys
        from scripts.queue_coverage_gap import main

        with patch('scripts.queue_coverage_gap.find_all_gaps') as mock_find_gaps,              patch('sys.argv', ['scripts/queue_coverage_gap.py', '--repo', 'test/repo']):

            mock_find_gaps.return_value = [
                ("Discovery gap (No domain hint)", 10, [], "discovery"),
                ("ATS Family integration (workday)", 5, [], "ats-workday")
            ]

            main()

            # The second gap should be queued because the first one was already queued
            mock_create.assert_called_once_with(
                'test/repo', 'ATS Family integration (workday)', 5, 'ats-workday', []
            )

    @patch("scripts.queue_coverage_gap._gh_json")
    @patch("scripts.queue_coverage_gap.issue_already_queued")
    @patch("scripts.queue_coverage_gap.get_active_and_coverage_issues")
    @patch("scripts.queue_coverage_gap.resources_conflict_with_active_work")
    @patch("scripts.queue_coverage_gap.create_issue")
    def test_stop_condition_threshold(self, mock_create, mock_conflict, mock_get_issues, mock_already_queued, mock_gh_json):
        mock_conflict.return_value = False
        mock_get_issues.return_value = ([], [])
        mock_already_queued.return_value = False

        import sys
        from scripts.queue_coverage_gap import main

        with patch('scripts.queue_coverage_gap.find_all_gaps') as mock_find_gaps,              patch('sys.argv', ['scripts/queue_coverage_gap.py', '--repo', 'test/repo']):

            # Only 1 employer, which is below the threshold of 2
            mock_find_gaps.return_value = [
                ("ATS Family integration (workday)", 1, [], "ats-workday")
            ]

            main()

            # create_issue should not be called because count is < 2
            mock_create.assert_not_called()

if __name__ == '__main__':
    unittest.main()
