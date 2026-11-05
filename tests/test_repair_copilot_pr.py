"""Behavioral regression tests for trusted CI-to-Copilot repair delivery."""
import unittest
from copy import deepcopy

from scripts import repair_copilot_pr as mod

REPO = "kaamilbadami/yartchives"
HEAD = "a" * 40


def fixture():
    run = {"id": 901, "name": "Quality checks", "event": "pull_request",
           "conclusion": "failure", "head_sha": HEAD, "pull_requests": [{"number": 42}]}
    pr = {"number": 42, "state": "open", "draft": False,
          "user": {"login": "Copilot"}, "body": "Closes #17",
          "head": {"sha": HEAD, "ref": "copilot/task-17",
                   "repo": {"full_name": REPO}}, "base": {"ref": "main"}}
    issue = {"state": "open", "labels": [], "assignees": [{"login": "Copilot"}]}
    files = [{"filename": "tests/test_sample.py", "status": "modified"}]
    jobs = {"jobs": [{"name": "tests", "conclusion": "failure",
                       "steps": [{"name": "Python tests", "conclusion": "failure"}]}]}
    return {"workflow_run": run}, pr, issue, files, jobs


class FakeApi:
    def __init__(self):
        self.event, self.pr, self.issue, self.files, self.jobs = fixture()
        self.comments = []
        self.posts = []

    def __call__(self, path, *, method="GET", body=None, token=None):
        if method == "POST":
            assert path.endswith("/issues/42/comments")
            self.posts.append((body["body"], token))
            self.comments.append({"body": body["body"], "user": {"login": (
                "github-actions[bot]" if token is None else "kaamilbadami")}})
            return {"id": len(self.posts)}
        if path.endswith("/pulls/42"):
            return deepcopy(self.pr)
        if path.endswith("/issues/17"):
            return deepcopy(self.issue)
        if path.endswith("/pulls/42/files?per_page=100"):
            return deepcopy(self.files)
        if path.endswith("/runs/901/jobs?filter=latest&per_page=100"):
            return deepcopy(self.jobs)
        if path.endswith("/issues/42/comments?per_page=100"):
            return deepcopy(self.comments)
        raise AssertionError(path)


class CopilotRepairTests(unittest.TestCase):
    def test_failed_low_risk_copilot_pr_requests_single_repair(self):
        api = FakeApi()
        self.assertIn("requested Copilot repair", mod.dispatch(api.event, REPO, "user-token", api))
        self.assertEqual(len(api.posts), 2)
        self.assertIn(mod.REPAIR_MARKER, api.posts[0][0])
        self.assertIsNone(api.posts[0][1])
        self.assertIn("@copilot", api.posts[1][0])
        self.assertEqual(api.posts[1][1], "user-token")
        self.assertIn("already requested", mod.dispatch(api.event, REPO, "user-token", api))
        self.assertEqual(len(api.posts), 2)

    def test_blocked_gated_or_ambiguous_runs_do_not_write(self):
        for edit in (
            lambda a: a.event["workflow_run"].update(conclusion="action_required"),
            lambda a: a.event["workflow_run"].update(event="workflow_dispatch"),
            lambda a: a.event["workflow_run"].update(pull_requests=[]),
            lambda a: a.event["workflow_run"].update(head_sha="b" * 40),
            lambda a: a.pr.update(state="closed"),
            lambda a: a.pr["user"].update(login="someone-else"),
            lambda a: a.pr["head"]["repo"].update(full_name="fork/project"),
            lambda a: a.issue.update(labels=[{"name": "initiative"}]),
            lambda a: a.issue.update(assignees=[]),
            lambda a: a.files.append({"filename": ".github/workflows/quality.yml"}),
            lambda a: a.jobs["jobs"][0]["steps"][0].update(name="Publish status"),
        ):
            with self.subTest(edit=edit):
                api = FakeApi()
                edit(api)
                self.assertNotIn("requested Copilot repair",
                                 mod.dispatch(api.event, REPO, "user-token", api))
                self.assertEqual(api.posts, [])

    def test_at_most_two_repairs_across_distinct_heads(self):
        api = FakeApi()
        api.comments = [{"user": {"login": mod.BOT},
                         "body": mod.REPAIR_MARKER + "head=" + ("b" * 40) + " run=1 -->"},
                        {"user": {"login": mod.BOT},
                         "body": mod.REPAIR_MARKER + "head=" + ("c" * 40) + " run=2 -->"}]
        self.assertIn("budget exhausted", mod.dispatch(api.event, REPO, "user-token", api))
        self.assertFalse(api.posts)

    def test_marker_precedes_ambiguous_copilot_failure(self):
        api = FakeApi()
        def broken(path, *, method="GET", body=None, token=None):
            if method == "POST" and token:
                raise RuntimeError("ambiguous delivery")
            return api(path, method=method, body=body, token=token)
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            mod.dispatch(api.event, REPO, "user-token", broken)
        self.assertEqual(len(api.posts), 1)
        self.assertIn("already requested", mod.dispatch(api.event, REPO, "user-token", api))

    def test_failure_classifier_rejects_mixed_failure(self):
        self.assertEqual(mod.failed_test_steps([
            {"conclusion": "failure", "steps": [
                {"name": "Python tests", "conclusion": "failure"},
                {"name": "Install dependencies", "conclusion": "failure"}]}]), [])
        self.assertEqual(mod.failed_test_steps([
            {"conclusion": "failure", "steps": [
                {"name": "Python tests", "conclusion": "failure"}]}]), ["Python tests"])


if __name__ == "__main__":
    unittest.main()
