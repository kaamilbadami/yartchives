import importlib.util
import pathlib
import unittest


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
            return [issue.copy() for issue in self.issues if issue["state"] == "open"]
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
        self.assertEqual(labels, {"workflow-failure", "agent-ready", "jules"})
        self.assertIn("Quality checks::tests::Python tests", gh.issues[0]["body"])

    def test_success_closes_failure_cycle_and_next_failure_dispatches_fresh_jules_issue(self):
        gh = FakeGh()
        gh.jobs_by_run["1"] = failed_jobs()
        gh.jobs_by_run["3"] = failed_jobs()

        mod.triage(ctx(run_id="1", conclusion="failure"), gh.json, gh.run)
        first_issue = gh.issues[0]
        self.assertIn("jules", {label["name"] for label in first_issue["labels"]})

        mod.triage(ctx(run_id="2", conclusion="success"), gh.json, gh.run)
        self.assertEqual(first_issue["state"], "closed")
        first_labels = {label["name"] for label in first_issue["labels"]}
        self.assertNotIn("jules", first_labels)
        self.assertNotIn("agent-ready", first_labels)

        mod.triage(ctx(run_id="3", conclusion="failure"), gh.json, gh.run)
        open_issues = [issue for issue in gh.issues if issue["state"] == "open"]
        self.assertEqual(len(open_issues), 1)
        self.assertNotEqual(open_issues[0]["number"], first_issue["number"])
        self.assertIn("jules", {label["name"] for label in open_issues[0]["labels"]})

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


if __name__ == "__main__":
    unittest.main()
