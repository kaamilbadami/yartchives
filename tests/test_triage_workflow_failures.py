import importlib.util
import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "triage_workflow_failures.py"
SPEC = importlib.util.spec_from_file_location("triage_workflow_failures", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


class FakeGh:
    def __init__(self):
        self.issues = []
        self.calls = []
        self.jobs_by_run = {}

    def json(self, *args):
        if args[:2] == ("api", "--paginate"):
            if "issues?" in args[2] and not "/comments?" in args[2]:
                return [issue.copy() for issue in self.issues if issue["state"] == "open"]
            if "/comments?" in args[2]:
                number = int(args[2].split("/issues/", 1)[1].split("/comments", 1)[0])
                issue = self._issue(number)
                return issue.get("comments", [])
        if args[0] == "api" and "/jobs?" in args[1]:
            run_id = args[1].split("/runs/", 1)[1].split("/jobs", 1)[0]
            return {"jobs": self.jobs_by_run[run_id]}
        raise AssertionError(f"unexpected gh json call: {args}")

    def run(self, *args):
        self.calls.append(args)
        if args[:2] == ("label", "create"):
            return
        if args[:2] == ("issue", "create"):
            title = args[args.index("--title") + 1]
            body = args[args.index("--body") + 1]
            labels = [
                args[index + 1]
                for index, value in enumerate(args)
                if value == "--label"
            ]
            self.issues.append(
                {
                    "number": len(self.issues) + 1,
                    "state": "open",
                    "title": title,
                    "body": body,
                    "labels": [{"name": label} for label in labels],
                }
            )
            return
        if args[:2] == ("issue", "edit"):
            issue = self._issue(int(args[2]))
            labels = {label["name"] for label in issue["labels"]}
            index = 5
            while index < len(args):
                if args[index] == "--add-label":
                    labels.add(args[index + 1])
                    index += 2
                elif args[index] == "--remove-label":
                    labels.discard(args[index + 1])
                    index += 2
                else:
                    index += 1
            issue["labels"] = [{"name": label} for label in sorted(labels)]
            return
        if args[:2] == ("issue", "comment"):
            issue = self._issue(int(args[2]))
            if "comments" not in issue:
                issue["comments"] = []
            body = args[args.index("--body") + 1]
            issue["comments"].append({"body": body})
            return
        if args[:2] == ("workflow", "run"):
            return
        if args[:2] == ("issue", "close"):
            self._issue(int(args[2]))["state"] = "closed"
            return
        raise AssertionError(f"unexpected gh run call: {args}")

    def _issue(self, number):
        return next(issue for issue in self.issues if issue["number"] == number)


def ctx(*, run_id, conclusion, branch="main", workflow="Quality checks"):
    return mod.Context(
        repo="kaamilbadami/yartchives",
        run_id=run_id,
        run_url=f"https://github.example/runs/{run_id}",
        workflow=workflow,
        head_sha=f"sha-{run_id}",
        conclusion=conclusion,
        head_branch=branch,
        default_branch="main",
    )


def failed_jobs():
    return [
        {
            "name": "tests",
            "conclusion": "failure",
            "steps": [
                {"name": "Python tests", "conclusion": "failure"},
            ],
        }
    ]


class TriageWorkflowFailuresTests(unittest.TestCase):
    def test_new_default_branch_failure_creates_jules_labeled_issue(self):
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()

        mod.triage(ctx(run_id="1", conclusion="failure"), gh.json, gh.run)

        self.assertEqual(len(gh.issues), 1)
        labels = {label["name"] for label in gh.issues[0]["labels"]}
        self.assertEqual(labels, {"workflow-failure", "agent-ready", "autonomous-backlog"})
        self.assertIn("Quality checks::tests::Python tests", gh.issues[0]["body"])

    def test_success_closes_failure_cycle_and_next_failure_dispatches_fresh_jules_issue(self):
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()
        gh.jobs_by_run["3"] = failed_jobs()

        mod.triage(ctx(run_id="1", conclusion="failure"), gh.json, gh.run)
        first_issue = gh.issues[0]
        self.assertIn("autonomous-backlog", {label["name"] for label in first_issue["labels"]})

        mod.triage(ctx(run_id="2", conclusion="success"), gh.json, gh.run)
        self.assertEqual(first_issue["state"], "closed")
        first_labels = {label["name"] for label in first_issue["labels"]}
        self.assertNotIn("autonomous-backlog", first_labels)
        self.assertNotIn("agent-ready", first_labels)
        self.assertNotIn("jules", first_labels)
        self.assertNotIn("jules-session", first_labels)

        mod.triage(ctx(run_id="3", conclusion="failure"), gh.json, gh.run)
        open_issues = [issue for issue in gh.issues if issue["state"] == "open"]
        self.assertEqual(len(open_issues), 1)
        self.assertNotEqual(open_issues[0]["number"], first_issue["number"])
        self.assertIn("autonomous-backlog", {label["name"] for label in open_issues[0]["labels"]})

    def test_pr_failure_does_not_dispatch_jules(self):
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()

        mod.triage(
            ctx(run_id="1", conclusion="failure", branch="feature/pr"),
            gh.json,
            gh.run,
        )

        self.assertEqual(gh.issues, [])
        self.assertFalse(any(call[:2] == ("issue", "create") for call in gh.calls))

    def test_success_only_closes_issues_for_matching_workflow(self):
        gh = FakeGh()
        gh.issues = [
            {
                "number": 1,
                "state": "open",
                "body": "<!-- workflow-failure-signature: Quality checks::tests::Python tests -->",
                "labels": [{"name": "workflow-failure"}, {"name": "agent-ready"}, {"name": "jules"}],
            },
            {
                "number": 2,
                "state": "open",
                "body": "<!-- workflow-failure-signature: Update opportunity feed::build::Validate generated feed -->",
                "labels": [{"name": "workflow-failure"}, {"name": "agent-ready"}, {"name": "jules"}],
            },
        ]

        mod.triage(ctx(run_id="2", conclusion="success"), gh.json, gh.run)

        self.assertEqual(gh.issues[0]["state"], "closed")
        self.assertEqual(gh.issues[1]["state"], "open")



    def test_failure_closes_stale_issues_for_different_steps(self):
        gh = FakeGh()
        gh.issues = [
            {
                "number": 1,
                "state": "open",
                "body": "<!-- workflow-failure-signature: Quality checks::tests::Python tests -->",
                "labels": [{"name": "workflow-failure"}, {"name": "agent-ready"}, {"name": "jules"}],
            },
            {
                "number": 2,
                "state": "open",
                "body": "<!-- workflow-failure-signature: Quality checks::lint::Check formatting -->",
                "labels": [{"name": "workflow-failure"}, {"name": "agent-ready"}, {"name": "jules"}],
            },
            {
                "number": 3,
                "state": "open",
                "body": "<!-- workflow-failure-signature: Update opportunity feed::build::Validate generated feed -->",
                "labels": [{"name": "workflow-failure"}, {"name": "agent-ready"}, {"name": "jules"}],
            },
        ]

        # New run only fails on 'lint' -> 'Check formatting'
        gh.jobs_by_run["2"] = [
            {
                "name": "lint",
                "conclusion": "failure",
                "steps": [
                    {"name": "Check formatting", "conclusion": "failure"},
                ],
            }
        ]

        mod.triage(ctx(run_id="2", conclusion="failure"), gh.json, gh.run)

        # Issue 1 (Python tests) should be closed because it's no longer failing in the new run
        self.assertEqual(gh.issues[0]["state"], "closed")

        # Issue 2 (Check formatting) is still failing, so it stays open
        self.assertEqual(gh.issues[1]["state"], "open")

        # Issue 3 is from a different workflow ("Update opportunity feed"), so it stays open
        self.assertEqual(gh.issues[2]["state"], "open")


    @patch("subprocess.run")
    def test_trusted_jules_pr_failed_check_enters_repair_cycle(self, mock_run):
        mock_run.return_value.stdout = "line1\nline2\nline3\n"
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()
        gh.issues = [
            {
                "number": 123,
                "state": "open",
                "body": "<!-- jules-output: issue=100 session=abc pr=123 head=sha-1 -->",
                "labels": [{"name": "jules-review-ready"}],
                "comments": []
            }
        ]

        mod.triage(
            ctx(run_id="1", conclusion="failure", branch="jules-branch"),
            gh.json,
            gh.run,
        )

        issue = gh._issue(123)
        labels = {label["name"] for label in issue["labels"]}
        self.assertIn("jules-retry-ready", labels)
        self.assertNotIn("jules-review-ready", labels)

        self.assertEqual(len(issue["comments"]), 1)
        self.assertIn("ci-repair-delivered: sha-1::tests::Python tests", issue["comments"][0]["body"])
        self.assertIn("<!-- jules-retry-from: abc -->", issue["comments"][0]["body"])
        self.assertIn("line1", issue["comments"][0]["body"])

    @patch("subprocess.run")
    def test_trusted_jules_pr_successful_rerun_automerges(self, mock_run):
        gh = FakeGh()
        gh.issues = [
            {
                "number": 123,
                "state": "open",
                "body": "<!-- jules-output: issue=100 session=abc pr=123 head=sha-2 -->",
                "labels": [{"name": "jules-retry-ready"}],
                "comments": []
            }
        ]

        mod.triage(
            ctx(run_id="2", conclusion="success", branch="jules-branch"),
            gh.json,
            gh.run,
        )

        issue = gh._issue(123)
        labels = {label["name"] for label in issue["labels"]}
        self.assertIn("jules-review-ready", labels)
        self.assertNotIn("jules-retry-ready", labels)
        self.assertEqual(len(issue["comments"]), 1)
        self.assertIn("CI is green again. Proceeding toward auto-merge.", issue["comments"][0]["body"])
        self.assertTrue(any(call[:2] == ("workflow", "run") for call in gh.calls))

    @patch("subprocess.run")
    def test_duplicate_failure_is_idempotent(self, mock_run):
        mock_run.return_value.stdout = "log"
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()
        gh.issues = [
            {
                "number": 123,
                "state": "open",
                "body": "<!-- jules-output: issue=100 session=abc pr=123 head=sha-1 -->",
                "labels": [{"name": "jules-retry-ready"}],
                "comments": [
                    {"body": "<!-- ci-repair-delivered: sha-1::tests::Python tests -->"}
                ]
            }
        ]

        # Capture old length
        old_calls_len = len(gh.calls)
        mod.triage(
            ctx(run_id="1", conclusion="failure", branch="jules-branch"),
            gh.json,
            gh.run,
        )

        issue = gh._issue(123)
        self.assertEqual(len(issue["comments"]), 1) # No new comment added

    @patch("subprocess.run")
    def test_exhausted_repair_budget_parks_task(self, mock_run):
        mock_run.return_value.stdout = "log"
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()
        gh.issues = [
            {
                "number": 123,
                "state": "open",
                "body": "<!-- jules-output: issue=100 session=abc pr=123 head=sha-1 -->",
                "labels": [{"name": "jules-retry-ready"}],
                "comments": [
                    {"body": "<!-- ci-repair-delivered: other-sha::tests::Python tests -->"},
                    {"body": "<!-- ci-repair-delivered: other-sha-2::tests::Python tests -->"}
                ]
            }
        ]

        mod.triage(
            ctx(run_id="1", conclusion="failure", branch="jules-branch"),
            gh.json,
            gh.run,
        )

        issue = gh._issue(123)
        labels = {label["name"] for label in issue["labels"]}
        self.assertIn("jules-failed", labels)
        self.assertNotIn("jules-retry-ready", labels)

        self.assertEqual(len(issue["comments"]), 3)
        self.assertIn("CI repair budget exhausted", issue["comments"][-1]["body"])

    def test_ordinary_pr_is_ignored(self):
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()
        gh.issues = [
            {
                "number": 123,
                "state": "open",
                "body": "normal pr",
                "labels": [],
                "comments": []
            }
        ]

        mod.triage(
            ctx(run_id="1", conclusion="failure", branch="feature/pr"),
            gh.json,
            gh.run,
        )
        self.assertEqual(len(gh.issues[0]["comments"]), 0)
        self.assertFalse(any(call[:2] == ("issue", "edit") for call in gh.calls))

    def test_untrusted_pr_is_ignored(self):
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()
        gh.issues = [
            {
                "number": 123,
                "state": "open",
                "body": "<!-- jules-output: issue=100 session=abc pr=123 head=sha-2 -->", # head mismatch
                "labels": [{"name": "jules-review-ready"}],
                "comments": []
            }
        ]

        mod.triage(
            ctx(run_id="1", conclusion="failure", branch="feature/pr"),
            gh.json,
            gh.run,
        )
        self.assertEqual(len(gh.issues[0]["comments"]), 0)

    def test_default_branch_behavior_unchanged(self):
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()
        # Head branch is "main" in this helper by default

        mod.triage(ctx(run_id="1", conclusion="failure"), gh.json, gh.run)

        # Should create a new issue for the default branch failure
        self.assertEqual(len(gh.issues), 1)
        labels = {label["name"] for label in gh.issues[0]["labels"]}
        self.assertEqual(labels, {"workflow-failure", "agent-ready", "autonomous-backlog"})

if __name__ == "__main__":
    unittest.main()
