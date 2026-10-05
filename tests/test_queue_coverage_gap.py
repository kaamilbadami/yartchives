import json
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.queue_coverage_gap import (
    coverage_gap_resources,
    create_issue,
    find_all_gaps,
    gap_has_meaningful_generic_impact,
    get_active_and_coverage_issues,
    issue_already_queued,
    resources_conflict_with_active_work,
)

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

    def test_find_all_gaps_unknown_provider_is_actionable(self):
        universe = {
            "employers": [
                {
                    "name": "Employer 1",
                    "seed_sets": ["fortune-500-2026"],
                    "provider": {"status": "unresolved"},
                    "domain_hints": ["careers.example.com"],
                    "seed_metadata": {},
                },
                {
                    "name": "Employer 2",
                    "seed_sets": ["cs-benchmark"],
                    "provider": {"status": "unresolved"},
                    "seed_metadata": {
                        "test": {"domain_hints": ["jobs.example.org"]}
                    },
                },
            ]
        }

        with patch(
            "scripts.queue_coverage_gap.fingerprint_provider",
            return_value={"family": "unknown"},
        ):
            gaps = find_all_gaps(universe)

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0][0], "Unsupported ATS / Unknown provider family")
        self.assertEqual(gaps[0][1], 2)
        self.assertEqual(gaps[0][3], "unknown-provider")

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
        body = args[args.index("--body") + 1]
        self.assertIn("resources: coverage-gap:discovery", body)
        self.assertNotIn("resources: automation, coverage-analysis", body)

    def test_coverage_gap_resources_are_family_specific(self):
        self.assertEqual(
            coverage_gap_resources("ats-workday"),
            frozenset({"coverage-gap:ats-workday"}),
        )
        self.assertNotEqual(
            coverage_gap_resources("ats-workday"),
            coverage_gap_resources("ats-icims"),
        )

    def test_resources_conflict_with_active_work(self):
        from scripts.dispatch_autonomous_issues import Task

        active_link_task = Task(
            1, "Test", "", "P1", "link-quality",
            frozenset(), frozenset(), frozenset(),
        )
        self.assertFalse(
            resources_conflict_with_active_work([active_link_task], "ats-workday")
        )

        active_feed_task = Task(
            2, "Test", "", "P1", "feed",
            frozenset(), frozenset(), frozenset(),
        )
        self.assertTrue(
            resources_conflict_with_active_work([active_feed_task], "ats-workday")
        )

        active_workday_task = Task(
            3,
            "Test",
            "",
            "P1",
            "coverage-automation",
            frozenset(),
            frozenset({"coverage-gap:ats-workday"}),
            frozenset(),
        )
        self.assertTrue(
            resources_conflict_with_active_work([active_workday_task], "ats-workday")
        )
        self.assertFalse(
            resources_conflict_with_active_work([active_workday_task], "ats-icims")
        )


    @patch("scripts.queue_coverage_gap._gh_json")
    @patch("scripts.queue_coverage_gap.issue_already_queued")
    @patch("scripts.queue_coverage_gap.get_active_and_coverage_issues")
    @patch("scripts.queue_coverage_gap.resources_conflict_with_active_work")
    @patch("scripts.queue_coverage_gap.create_issue")
    def test_select_all_unqueued_independent_gaps(self, mock_create, mock_conflict, mock_get_issues, mock_already_queued, mock_gh_json):
        mock_conflict.return_value = False
        mock_get_issues.return_value = ([], [])
        mock_already_queued.return_value = False

        import sys
        from scripts.queue_coverage_gap import main

        with patch("scripts.queue_coverage_gap.find_all_gaps") as mock_find_gaps, \
             patch("scripts.queue_coverage_gap.MAX_ACTIVE", 2), \
             patch("sys.argv", ["scripts/queue_coverage_gap.py", "--repo", "test/repo"]):

            mock_find_gaps.return_value = [
                ("ATS Family integration (workday)", 5, [], "ats-workday"),
                ("ATS Family integration (icims)", 4, [], "ats-icims"),
            ]

            main()

            self.assertEqual(mock_create.call_count, 2)
            mock_create.assert_any_call(
                "test/repo", "ATS Family integration (workday)", 5, "ats-workday", []
            )
            mock_create.assert_any_call(
                "test/repo", "ATS Family integration (icims)", 4, "ats-icims", []
            )
            mock_conflict.assert_any_call([], "ats-workday")
            mock_conflict.assert_any_call([], "ats-icims")

    @patch("scripts.queue_coverage_gap._gh_json")
    @patch("scripts.queue_coverage_gap.issue_already_queued")
    @patch("scripts.queue_coverage_gap.get_active_and_coverage_issues")
    @patch("scripts.queue_coverage_gap.resources_conflict_with_active_work")
    @patch("scripts.queue_coverage_gap.create_issue")
    def test_singleton_ats_gap_remains_generic_and_is_queued(self, mock_create, mock_conflict, mock_get_issues, mock_already_queued, mock_gh_json):
        mock_conflict.return_value = False
        mock_get_issues.return_value = ([], [])
        mock_already_queued.return_value = False

        import sys
        from scripts.queue_coverage_gap import main

        with patch('scripts.queue_coverage_gap.find_all_gaps') as mock_find_gaps,              patch('sys.argv', ['scripts/queue_coverage_gap.py', '--repo', 'test/repo']):

            mock_find_gaps.return_value = [
                ("ATS Family integration (workday)", 1, [], "ats-workday")
            ]

            main()

            mock_create.assert_called_once_with(
                'test/repo', 'ATS Family integration (workday)', 1, 'ats-workday', []
            )
            mock_conflict.assert_called_once_with([], "ats-workday")

    def test_singleton_discovery_gap_is_not_generic_enough(self):
        self.assertFalse(gap_has_meaningful_generic_impact("discovery", 1))
        self.assertTrue(gap_has_meaningful_generic_impact("discovery", 2))
        self.assertTrue(gap_has_meaningful_generic_impact("ats-workday", 1))
        self.assertTrue(gap_has_meaningful_generic_impact("unknown-provider", 2))

if __name__ == '__main__':
    unittest.main()
